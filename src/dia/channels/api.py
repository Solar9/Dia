"""HTTP + WebSocket API, and the web UI it serves (desktop app, KDE widget, phone).

It listens on 127.0.0.1. Every API call needs a token, sent as
``Authorization: Bearer <token>`` or, for the WebSocket, ``?token=``:

- on this computer, the owner token kept in ``<data_dir>/api-token`` (mode 600);
- from anywhere else, only with ``[ui] remote = true``, the token of a paired
  device (``dia mobile pair``). Devices cannot read or change the
  configuration, use this computer's microphone or manage devices.

Requests whose Host header is neither this machine nor one of ``[ui] hosts``
are refused, so a web page in your browser can't reach Dia through DNS tricks.

Started by ``dia serve`` unless ``[ui] enabled = false``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import tomllib
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import WSMsgType, web

from dia import __version__, processes
from dia.agents import Mode
from dia.assistant import Assistant
from dia.attention import Attention
from dia.audit import ACTOR
from dia.channels import Channel
from dia.config import ConfigError, parse_config, read_settings, save_settings
from dia.devices import Device, Devices, public_url
from dia.missions import Missions
from dia.orchestrator import Event, TaskActionError, TaskReport
from dia.push import Push
from dia.push import available as push_available
from dia.schedule import Scheduler, Schedules
from dia.skills import enabled_skills
from dia.store import TaskRecord

# The paired device making a request (None: the owner). aiohttp < 3.12 has no
# typed request keys; a plain string works there.
DEVICE = web.RequestKey("device", object) if hasattr(web, "RequestKey") else "device"

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.api")

STATIC = Path(__file__).resolve().parent.parent / "ui" / "static"
DEFAULT_PORT = 8765
LOOPBACK = ("127.0.0.1", "localhost", "[::1]")
# What a paired device may not do: only the owner, at this computer, may.
OWNER_ONLY = (
    "/api/cli-sessions",
    "/api/cli-captured",
    "/api/config",
    "/api/voice/",
    "/api/devices",
    "/api/settings",
    "/api/secrets",
    "/api/preferences",
    "/api/profile",
    "/api/work",
    "/api/tidy",
    "/api/tools",
    "/api/desktop",
)
# What even a device with full access may not do: secrets and pairing stay at the computer.
NEVER_REMOTE = ("/api/devices", "/api/secrets", "/api/desktop")
# Dia's CLI commands the app runs for the owner, showing their output: what has
# no button of its own still works from the app (Status → Tools).
TOOLS = (
    "doctor", "agents", "sandbox", "brains", "limits", "issues", "check", "bench", "launch",
    "lab", "redteam", "changelog", "security", "usage", "howto", "learned", "decisions",
    "schedule", "suggestions", "work", "goal", "why", "impact", "debt",
)  # fmt: skip
# Sections whose changes need a restart (they are read when channels start).
RESTART_SECTIONS = ("channels", "ui", "watch", "issues")


def api_token(data_dir: Path) -> str:
    """The API token, created on first use (file mode 600)."""
    path = data_dir / "api-token"
    if path.exists():
        return path.read_text().strip()
    data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token + "\n")
    path.chmod(0o600)
    return token


def user_themes_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "dia" / "themes"


def task_json(task: TaskRecord) -> dict[str, Any]:
    return asdict(task)


def device_json(device: Device) -> dict[str, Any]:
    return {k: v for k, v in asdict(device).items() if k != "token_hash"}


def pairing(device: Device, token: str, public_url: str | None) -> dict[str, Any]:
    """What the owner needs to set up a device: its token, the link with the token,
    and that link as a QR code (SVG, when the optional ``qrcode`` package is there)."""
    url = f"{public_url}#token={token}" if public_url else None
    result: dict[str, Any] = {"device": device_json(device), "token": token, "url": url}
    if url:
        result["qr_svg"] = qr_svg(url)
    return result


def qr_svg(text: str) -> str | None:
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return None
    image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    return image.to_string(encoding="unicode")


def _models_of(kind: str) -> tuple[str, ...]:
    from dia import plugins

    try:
        return getattr(plugins.load("dia.agents", kind), "models", ())
    except Exception:
        return ()


def _sandbox_state(config: Any) -> str:
    """ "on", "off" (switched off) or "unavailable" (no working bubblewrap)."""
    from dia import sandbox

    try:
        return (
            "on" if sandbox.enabled(config) else ("off" if sandbox.bwrap_works() else "unavailable")
        )
    except RuntimeError:
        return "unavailable"


class ApiChannel(Channel):
    kind = "api"

    def __init__(self, name: str, options: dict[str, Any], dia: Orchestrator) -> None:
        super().__init__(name, options, dia)
        self.port = int(options.get("port", DEFAULT_PORT))
        self.token = api_token(dia.config.data_dir)
        self.assistant = Assistant(dia)
        self._sockets: set[web.WebSocketResponse] = set()
        self._background: set[asyncio.Task] = set()
        self.voice_state = "idle"
        self._tool_lock = asyncio.Lock()
        self.local_hosts = {f"{h}:{self.port}" for h in LOOPBACK}
        self.devices = Devices(dia.config.data_dir)
        self.push = Push(dia)
        self.remote = bool(options.get("remote", False))
        self.listen = [a for a in options.get("listen", []) if a not in ("127.0.0.1", "localhost")]
        self.remote_hosts: set[str] = set()
        if self.remote:
            for host in [*options.get("hosts", []), *self.listen]:
                self.remote_hosts |= {host, f"{host}:{self.port}"}
        self.allowed_hosts = self.local_hosts | self.remote_hosts

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def public_url(self) -> str | None:
        return public_url(self.options, self.port)

    # -------------------------------------------------------------- server ---

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self._guard])
        r = app.router
        r.add_get("/", self.index)
        r.add_get("/api/status", self.status)
        r.add_get("/api/cli-sessions", self.cli_sessions)
        r.add_get("/api/cli-sessions/{pid}/transcript", self.cli_transcript)
        r.add_post("/api/cli-sessions/{pid}/capture", self.cli_capture)
        r.add_get("/api/cli-captured", self.cli_captured)
        r.add_get("/api/cli-captured/{id}/transcript", self.cli_captured_transcript)
        r.add_post("/api/cli-captured/{id}/send", self.cli_captured_send)
        r.add_delete("/api/cli-captured/{id}", self.cli_release)
        r.add_get("/api/tasks", self.tasks)
        r.add_post("/api/tasks", self.create_task)
        r.add_get("/api/tasks/{id}", self.task)
        r.add_get("/api/tasks/{id}/diff", self.diff)
        r.add_get("/api/tasks/{id}/tests", self.tests)
        r.add_post("/api/tasks/{id}/{action}", self.task_action)
        r.add_post("/api/plans", self.create_plan)
        r.add_post("/api/chat", self.chat)
        r.add_get("/api/chat/providers", self.chat_providers)
        r.add_get("/api/sessions", self.list_sessions)
        r.add_post("/api/sessions", self.create_session)
        r.add_get("/api/sessions/{id}", self.get_session)
        r.add_patch("/api/sessions/{id}", self.rename_session)
        r.add_delete("/api/sessions/{id}", self.delete_session)
        r.add_post("/api/voice/{action}", self.voice)
        r.add_get("/api/config", self.get_config)
        r.add_put("/api/config", self.put_config)
        r.add_get("/api/themes", self.themes)
        r.add_get("/themes/{name}.css", self.theme_css)
        r.add_get("/api/devices", self.list_devices)
        r.add_post("/api/devices", self.pair_device)
        r.add_delete("/api/devices/{id}", self.revoke_device)
        r.add_patch("/api/devices/{id}", self.update_device)
        r.add_get("/api/usage", self.usage)
        r.add_get("/api/scorecard", self.get_scorecard)
        r.add_post("/api/settings/apply-suggestion", self.apply_suggestion)
        r.add_post("/api/stop", self.stop)
        r.add_post("/api/builds", self.create_build)
        r.add_post("/api/council", self.create_council)
        r.add_post("/api/scenarios", self.create_scenario)
        r.add_post("/api/research", self.create_research)
        r.add_post("/api/experiments", self.create_experiment)
        r.add_post("/api/debug", self.create_debug)
        r.add_get("/api/security", self.security_report)
        r.add_get("/api/projects/{name}/changelog", self.project_changelog)
        r.add_get("/api/projects/{name}/analysis", self.project_analysis)
        r.add_get("/api/projects/{name}/balance", self.project_balance)
        r.add_get("/api/projects/{name}/benchmarks", self.project_benchmarks)
        r.add_post("/api/projects/{name}/contradictions", self.check_contradictions)
        r.add_get("/api/projects/{name}/impact", self.project_impact)
        r.add_get("/api/projects/{name}/debt", self.project_debt)
        r.add_post("/api/projects/{name}/debt/{n}/fix", self.fix_debt)
        r.add_get("/api/system", self.system_info)
        r.add_get("/api/health", self.health)
        r.add_get("/api/memory", self.memory_overview)
        r.add_get("/api/memory/note", self.memory_note)
        r.add_put("/api/memory/note", self.memory_write)
        r.add_get("/api/memory/search", self.memory_search)
        r.add_post("/api/quiet", self.quiet)
        r.add_post("/api/screen", self.screen)
        r.add_post("/api/camera", self.camera)
        r.add_get("/api/notifications", self.held_notifications)
        r.add_get("/api/tidy", self.tidy_plan)
        r.add_post("/api/tidy/{id}/{action}", self.tidy_action)
        r.add_get("/api/preferences", self.list_preferences)
        r.add_post("/api/preferences", self.add_preference)
        r.add_post("/api/preferences/{index}/{action}", self.decide_preference)
        r.add_get("/api/suggestions", self.list_suggestions)
        r.add_post("/api/suggestions/{key}/{action}", self.suggestion_action)
        r.add_get("/api/work", self.work_profiles)
        r.add_post("/api/work/{action}", self.work_action)
        r.add_get("/api/goals", self.list_goals)
        r.add_post("/api/goals", self.create_goal)
        r.add_post("/api/goals/{id}/{action}", self.goal_action)
        r.add_get("/api/missions", self.list_missions)
        r.add_post("/api/missions", self.create_mission)
        r.add_post("/api/missions/{id}/cancel", self.cancel_mission)
        r.add_post("/api/resume", self.resume)
        r.add_get("/api/audit", self.audit_log)
        r.add_get("/api/decisions", self.list_decisions)
        r.add_get("/api/profile", self.get_profile)
        r.add_put("/api/profile", self.put_profile)
        r.add_post("/api/profile/{action}", self.profile_action)
        r.add_get("/api/why", self.ask_why)
        r.add_get("/api/settings", self.get_settings)
        r.add_put("/api/settings", self.put_settings)
        r.add_get("/api/secrets", self.list_secrets)
        r.add_put("/api/secrets/{name}", self.set_secret)
        r.add_delete("/api/secrets/{name}", self.remove_secret)
        r.add_get("/api/schedules", self.list_schedules)
        r.add_post("/api/schedules", self.add_schedule)
        r.add_patch("/api/schedules/{id}", self.update_schedule)
        r.add_delete("/api/schedules/{id}", self.remove_schedule)
        r.add_post("/api/schedules/{id}/run", self.run_schedule)
        r.add_get("/api/skills", self.list_skills)
        r.add_post("/api/skills/{name}", self.run_skill)
        r.add_post("/api/tools", self.run_tool)
        r.add_get("/api/desktop", self.desktop_state)
        r.add_post("/api/desktop/{action}", self.desktop_action)
        r.add_get("/api/push", self.push_info)
        r.add_post("/api/push/subscribe", self.push_subscribe)
        r.add_post("/api/push/unsubscribe", self.push_unsubscribe)
        r.add_post("/api/push/test", self.push_test)
        r.add_get("/ws", self.websocket)
        r.add_get("/manifest.webmanifest", self.manifest)
        r.add_get("/sw.js", self.service_worker)
        r.add_static("/static/", STATIC)
        return app

    async def run(self) -> None:
        self.dia.store.listeners.append(self._on_task_saved)
        self.dia.store.audit_listeners.append(self._on_audit)
        self.dia.listeners.append(self._on_event)
        runner = web.AppRunner(self.app(), access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", self.port).start()
        log.info("UI and API on %s", self.url)
        if self.remote:
            for address in self.listen:
                await web.TCPSite(runner, address, self.port).start()
                log.warning(
                    "UI and API also on %s:%s for paired devices (plain HTTP: use it only "
                    "on a private network such as Tailscale)",
                    address,
                    self.port,
                )
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()

    def is_local(self, request: web.Request) -> bool:
        """Addressed to and coming from this computer (not through a proxy for others)."""
        return request.host in self.local_hosts and request.remote in ("127.0.0.1", "::1")

    @web.middleware
    async def _guard(self, request: web.Request, handler: Any) -> web.StreamResponse:
        if request.host not in self.allowed_hosts:
            raise web.HTTPForbidden(text="Dia only answers requests addressed to this computer")
        request[DEVICE] = None
        ACTOR.set("ui")
        if request.path.startswith(("/api/", "/ws")):
            header = request.headers.get("Authorization", "")
            given = header.removeprefix("Bearer ").strip() or request.query.get("token", "")
            local = self.is_local(request)
            if local and secrets.compare_digest(given, self.token):
                pass
            elif device := self.devices.authenticate(given):
                request[DEVICE] = device
                ACTOR.set(f"device:{device.name}")
                if request.path.startswith(NEVER_REMOTE if device.full else OWNER_ONLY):
                    raise web.HTTPForbidden(text="only on the computer running Dia")
            else:
                if not local:
                    await asyncio.sleep(1)  # slow down guessing
                raise web.HTTPUnauthorized(text="missing or wrong token")
        try:
            return await handler(request)
        except (TaskActionError, ConfigError, LookupError, ValueError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    def _spawn(self, coro: Any) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    async def _start(self, run: Any) -> TaskRecord:
        """Start a task in the background; return its record as soon as it exists."""
        started: asyncio.Future[TaskRecord] = asyncio.get_running_loop().create_future()

        async def on_start(task: TaskRecord) -> None:
            if not started.done():
                started.set_result(task)

        job = self._spawn(run(on_start))

        def failed(done: asyncio.Task) -> None:
            if not started.done():
                exc = done.exception() if not done.cancelled() else None
                started.set_exception(exc or RuntimeError("the task did not start"))

        job.add_done_callback(failed)
        return await started

    # --------------------------------------------------------------- pages ---

    async def index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC / "index.html")

    # -------------------------------------------------------------- status ---

    async def status(self, request: web.Request) -> web.Response:
        config = self.dia.config
        agents = []
        limited = self.dia.limit_status()
        for name, opts in config.agents.items():
            try:
                problem = await config.agent(name).check()
            except Exception as exc:
                problem = str(exc)
            agents.append(
                {
                    "name": name,
                    "type": opts.get("type", name),
                    "role": opts.get("role"),
                    "model": opts.get("model") or None,
                    "models": list(_models_of(opts.get("type", name))),
                    "ok": not problem,
                    "problem": problem,
                    "limited_until": limited.get(name),
                }
            )
        projects = []
        for project in config.projects.values():
            toolchain = self.dia.toolchain_for(project)
            projects.append(
                {
                    "name": project.name,
                    "path": str(project.path),
                    "ok": (project.path / ".git").exists(),
                    "toolchain": toolchain.describe() if toolchain else None,
                    "presets": toolchain.presets(project.path) if toolchain else [],
                    "benchmark": bool(project.options.get("benchmark")),
                }
            )
        active = [
            t.id for t in self.dia.store.recent(50) if t.status in ("queued", "running", "waiting")
        ]
        return web.json_response(
            {
                "agents": agents,
                "projects": projects,
                "memory": self.dia.memory.describe() if self.dia.memory else None,
                "brains": [b.name for b in config.brain_chain()],
                "channels": list(config.channels),
                "language": config.language,
                "version": __version__,
                "default_agent": config.default_agent,
                "pipelines": list(config.pipelines),
                "active": active,
                "halted": self.dia.halted,
                "quiet": self.dia.quiet,
                "screen": self.dia.screen_enabled,
                "camera": self.dia.camera_enabled,
                "sandbox": _sandbox_state(self.dia.config),
                "quiet_hours": Attention(self.dia).quiet_hours(),
                "processes": len(processes.running()),
                "pending_plan": self.assistant.pending_plan,
                "voice": self.voice_state,
                "device": request[DEVICE].name if request[DEVICE] else None,
                "device_full": bool(request[DEVICE] and request[DEVICE].full),
                "remote": self.remote,
            }
        )

    # ------------------------------------------------------------- devices ---

    async def list_devices(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "remote": self.remote,
                "public_url": self.public_url(),
                "devices": [device_json(d) for d in self.devices.list()],
            }
        )

    async def pair_device(self, request: web.Request) -> web.Response:
        name = str((await request.json()).get("name") or "phone")[:60]
        device, token = self.devices.pair(name)
        self.dia.audit("device.pair", device.id, device.name)
        return web.json_response(pairing(device, token, self.public_url()), status=201)

    async def update_device(self, request: web.Request) -> web.Response:
        """Full access for the owner's own phone: settings and tools, not secrets or pairing."""
        full = bool((await request.json()).get("full"))
        device = self.devices.set_full(request.match_info["id"], full)
        if not device:
            raise web.HTTPNotFound(text="no such device")
        self.dia.audit("device.full" if full else "device.limited", device.id, device.name)
        return web.json_response(device_json(device))

    async def revoke_device(self, request: web.Request) -> web.Response:
        device = self.devices.revoke(request.match_info["id"])
        if not device:
            raise web.HTTPNotFound(text="no such device")
        self.push.forget_device(device.name)
        self.dia.audit("device.revoke", device.id, device.name)
        return web.json_response({"message": "revoked"})

    # ------------------------------------------------------------ settings ---

    async def get_settings(self, request: web.Request) -> web.Response:
        from dia import plugins
        from dia.persona import PRESETS

        config = self.dia.config
        return web.json_response(
            {
                "values": config.raw,
                "settings_path": str(config.settings_path) if config.settings_path else None,
                "personalities": list(PRESETS),
                "agents": list(config.agents),
                "skills": sorted(plugins.available("dia.skills")),
                "tts": sorted(plugins.available("dia.tts")),
                "agent_types": sorted(plugins.available("dia.agents")),
                "agent_models": sorted(
                    {m for kind in plugins.available("dia.agents") for m in _models_of(kind)}
                ),
                # what the forms set (removable there), apart from the config file
                "overlay": read_settings(config.source) if config.source else {},
            }
        )

    async def apply_suggestion(self, request: web.Request) -> web.Response:
        """Make the proposed agent a project's default (the only thing a proposal changes)."""
        from dia.benchmark import agent_stats, suggestions

        body = await request.json()
        allowed = suggestions(self.dia.config, agent_stats(self.dia.store, 90))
        match = next(
            (s for s in allowed if (s["project"], s["agent"]) == (body["project"], body["agent"])),
            None,
        )
        if not match:
            raise ValueError("no such proposal")
        new = save_settings(
            self.dia.config, {"projects": {match["project"]: {"default_agent": match["agent"]}}}
        )
        self.dia.apply_config(new)
        self.dia.audit(
            "agents.default", match["project"], f"{match['current']} -> {match['agent']}"
        )
        return web.json_response({"message": f"{match['project']}: {match['agent']}"})

    async def put_settings(self, request: web.Request) -> web.Response:
        """Save form changes to settings.json and use them at once where possible."""
        changes = (await request.json()).get("changes", {})
        if not isinstance(changes, dict):
            raise ValueError("changes must be an object")
        new = save_settings(self.dia.config, changes)
        self.dia.apply_config(new)
        self.dia.audit("settings.change", None, ", ".join(sorted(changes)))
        restart = sorted(k for k in changes if k in RESTART_SECTIONS)
        return web.json_response({"saved": True, "restart_required": restart})

    async def list_secrets(self, request: web.Request) -> web.Response:
        from dia import secrets as secret_store

        return web.json_response(secret_store.status())

    async def set_secret(self, request: web.Request) -> web.Response:
        from dia import secrets as secret_store

        value = (await request.json()).get("value", "")
        secret_store.set_secret(request.match_info["name"], value)
        self.dia.audit("secret.set", request.match_info["name"])
        return web.json_response({"message": "saved"})

    async def remove_secret(self, request: web.Request) -> web.Response:
        from dia import secrets as secret_store

        secret_store.remove_secret(request.match_info["name"])
        self.dia.audit("secret.remove", request.match_info["name"])
        return web.json_response({"message": "removed"})

    # ----------------------------------------------------------- schedules ---

    def _schedules(self) -> Schedules:
        return Schedules(self.dia)

    async def list_schedules(self, request: web.Request) -> web.Response:
        schedules = self._schedules()
        upcoming = schedules.next_runs()
        return web.json_response(
            [{**asdict(job), "next": upcoming.get(job.id)} for job in schedules.list()]
        )

    async def add_schedule(self, request: web.Request) -> web.Response:
        job = self._schedules().add(await request.json())
        return web.json_response(asdict(job), status=201)

    async def update_schedule(self, request: web.Request) -> web.Response:
        job = self._schedules().update(request.match_info["id"], await request.json())
        return web.json_response(asdict(job))

    async def remove_schedule(self, request: web.Request) -> web.Response:
        if not self._schedules().remove(request.match_info["id"]):
            raise web.HTTPNotFound(text="no such schedule (config jobs: edit the file)")
        return web.json_response({"message": "removed"})

    async def run_schedule(self, request: web.Request) -> web.Response:
        job = next((j for j in self._schedules().list() if j.id == request.match_info["id"]), None)
        if not job:
            raise web.HTTPNotFound(text="no such schedule")
        self._spawn(Scheduler(self.dia, self.assistant).execute(job))
        return web.json_response({"message": "started"}, status=202)

    async def list_skills(self, request: web.Request) -> web.Response:
        skills = enabled_skills(self.dia)
        return web.json_response(
            [{"name": n, "description": s.description, "args": s.args} for n, s in skills.items()]
        )

    async def run_skill(self, request: web.Request) -> web.Response:
        """A skill's answer; one that needs a yes first answers with its question."""
        from dia.skills import NeedsConfirmation

        skill = enabled_skills(self.dia).get(request.match_info["name"])
        if not skill:
            raise web.HTTPNotFound(text="no such skill")
        body = await request.json() if request.can_read_body else {}
        args = {k: v for k, v in (body.get("args") or {}).items() if k in skill.args and v != ""}
        try:
            return web.json_response({"text": await skill.run(args)})
        except NeedsConfirmation as ask:
            if not body.get("confirm"):
                return web.json_response({"question": ask.question})
            self.dia.audit("skill.confirmed", skill.kind, ask.question)
            return web.json_response({"text": await ask.action()})

    async def run_tool(self, request: web.Request) -> web.Response:
        """One of Dia's CLI commands, ``{"command": "doctor", "args": ["--fix"]}``, with
        what it printed: the app reaches what has no button of its own."""
        import contextlib
        import io

        from dia.cli import build_parser

        body = await request.json()
        command = str(body.get("command", ""))
        if command not in TOOLS:
            raise web.HTTPNotFound(text=f"not available from the app: {command}")
        argv = [command, *(str(a) for a in body.get("args") or [])]
        out = io.StringIO()
        async with self._tool_lock:  # output is captured process-wide: one at a time
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    args = build_parser().parse_args(argv)
                except SystemExit:
                    return web.json_response({"code": 2, "output": out.getvalue()}, status=400)
                self.dia.audit("tool", command, " ".join(argv[1:]))
                try:
                    code = await args.fn(self.dia.config, args)
                except EOFError:  # it wanted to ask on the terminal
                    code = 1
                except Exception as exc:
                    print(f"error: {exc}")
                    code = 1
        return web.json_response({"code": code, "output": out.getvalue()})

    async def desktop_state(self, request: web.Request) -> web.Response:
        from dia import desktop, runtime, service
        from dia.ui import plasmoid_install

        return web.json_response({
            "runtime": await asyncio.to_thread(runtime.status),
            "shortcuts": desktop.state(),
            "service": service.status() if service.installed() else None,
            "service_available": service.check() is None,
            "widget": await asyncio.to_thread(plasmoid_install.installed),
        })  # fmt: skip

    async def desktop_action(self, request: web.Request) -> web.Response:
        """Shortcuts, start at login, the systemd service, the KDE widget."""
        action = request.match_info["action"]
        body = await request.json() if request.can_read_body else {}
        source = self.dia.config.source
        try:
            done = await self._desktop(action, body, source)
        except RuntimeError as exc:  # no systemd, no KDE Plasma 6...
            return web.json_response({"error": str(exc)}, status=409)
        self.dia.audit(f"desktop.{action}", None, "; ".join(done))
        return web.json_response({"message": "\n".join(done) or "-"})

    async def _desktop(self, action: str, body: dict[str, Any], source: Path | None) -> list[str]:
        from dia import desktop, runtime, service
        from dia.ui import plasmoid_install

        if action == "startup":
            await asyncio.to_thread(
                runtime.configure,
                source,
                **{key: body.get(key) for key in ("autostart", "ollama", "warmup")},
            )
            return ["Saved / Zapisano"]
        if action == "runtime":
            component, verb = body.get("component"), body.get("verb")
            if verb in ("stop", "restart") and not body.get("confirmed"):
                raise ValueError("Confirm stopping active work before continuing")
            await asyncio.to_thread(runtime.enqueue, component, verb, source)
            return ["Scheduled / Zaplanowano"]
        if action == "logs":
            return [await asyncio.to_thread(runtime.logs, body.get("component", "dia"))]
        if action == "shortcuts":
            done = desktop.install(source, bool(body.get("desktop", True)),
                                   bool(body.get("autostart", False)))  # fmt: skip
        elif action == "remove-shortcuts":
            done = desktop.uninstall()
        elif action == "service":
            done = service.install(source, start=False)  # this very process keeps serving
        elif action == "remove-service":
            done = service.uninstall()
        elif action == "widget":
            done = [await asyncio.to_thread(plasmoid_install.install)]
        else:
            raise web.HTTPNotFound(text=f"unknown action {action}")
        return done

    async def cli_sessions(self, request: web.Request) -> web.Response:
        """Agent CLIs running on this machine, whether or not Dia started them."""
        from dia.sessions import find_sessions

        found = await asyncio.to_thread(find_sessions)
        return web.json_response(
            [{**s.__dict__, "cwd": str(s.cwd) if s.cwd else None} for s in found]
        )

    async def cli_transcript(self, request: web.Request) -> web.Response:
        """The conversation of one running agent CLI (only sessions found on this machine)."""
        from dia.sessions import find_sessions, parse_transcript, transcript_file

        pid = int(request.match_info["pid"])
        found = await asyncio.to_thread(find_sessions)
        session = next((s for s in found if s.pid == pid), None)
        if session is None:
            raise LookupError("that agent session is not running")
        path = await asyncio.to_thread(transcript_file, session)
        messages = await asyncio.to_thread(parse_transcript, path) if path else []
        return web.json_response({"messages": messages, "available": path is not None})

    def _captured(self) -> Any:
        from dia.sessions import CapturedStore

        return CapturedStore(self.dia.config.data_dir / "captured_sessions.json")

    async def cli_capture(self, request: web.Request) -> web.Response:
        """Take a terminal session over: end its process, keep its conversation in the app."""
        from dia.sessions import (
            Captured,
            end_process,
            find_sessions,
            session_id_of,
            transcript_file,
        )

        pid = int(request.match_info["pid"])
        session = next((s for s in await asyncio.to_thread(find_sessions) if s.pid == pid), None)
        if session is None:
            raise LookupError("that agent session is not running")
        path = await asyncio.to_thread(transcript_file, session)
        session_id = session_id_of(session.kind, path) if path else None
        if not session_id or session.cwd is None:
            raise ValueError(
                "this session's conversation file was not found, so it cannot be taken over"
            )
        if not await asyncio.to_thread(end_process, pid):
            raise ValueError("the session did not quit; close it in its terminal")
        item = Captured(
            id=session_id,
            kind=session.kind,
            cwd=str(session.cwd),
            model=session.model,
            taken_at=datetime.now().isoformat(timespec="seconds"),
        )
        self._captured().add(item)
        self.dia.audit("cli.capture", session_id, f"{session.kind} in {session.cwd}")
        return web.json_response({**item.__dict__, "resume": item.resume})

    async def cli_captured(self, request: web.Request) -> web.Response:
        return web.json_response(
            [{**c.__dict__, "resume": c.resume} for c in self._captured().all()]
        )

    def _held(self, request: web.Request) -> Any:
        item = self._captured().get(request.match_info["id"])
        if item is None:
            raise LookupError("that conversation is not taken over")
        return item

    async def cli_captured_transcript(self, request: web.Request) -> web.Response:
        from dia.sessions import file_of, parse_transcript

        item = self._held(request)
        path = await asyncio.to_thread(file_of, item.kind, item.id)
        messages = await asyncio.to_thread(parse_transcript, path) if path else []
        return web.json_response({"messages": messages, "available": path is not None})

    async def cli_captured_send(self, request: web.Request) -> web.Response:
        """Continue a taken-over conversation: the CLI resumes it headless, in its folder."""
        from dia import plugins
        from dia.agents import AgentRequest, Mode

        item = self._held(request)
        text = str((await request.json()).get("text", "")).strip()
        if not text:
            raise ValueError("write something first")
        name = next(
            (n for n, o in self.dia.config.agents.items() if o.get("type", n) == item.kind), None
        )
        agent = (
            self.dia.config.agent(name)
            if name
            else plugins.load("dia.agents", item.kind)(item.kind, {})
        )
        used, result = await self.dia.call_agent(
            agent,
            AgentRequest(
                prompt=text,
                cwd=Path(item.cwd),
                mode=Mode.EDIT,
                session_id=item.id,
                model=item.model,
            ),
            purpose="cli-session",
        )
        if not result.success:
            raise ValueError(f"{used.name}: {result.error or 'no answer'}")
        if result.session_id and result.session_id != item.id:  # the CLI continued under a new id
            self._captured().replace_id(item.id, result.session_id)
        return web.json_response({"reply": result.summary, "id": result.session_id or item.id})

    async def cli_release(self, request: web.Request) -> web.Response:
        """Give the conversation back: it is no longer kept in the app (resume it in a terminal)."""
        item = self._held(request)
        self._captured().remove(item.id)
        return web.json_response({"message": "released", "resume": item.resume})

    async def health(self, request: web.Request) -> web.Response:
        """What runs supervised in `dia serve`, and what is restarting (dia.health)."""
        from dia.health import state

        return web.json_response(state(self.dia))

    async def list_suggestions(self, request: web.Request) -> web.Response:
        from dia.suggestions import Suggestions

        return web.json_response(Suggestions(self.dia).open())

    async def suggestion_action(self, request: web.Request) -> web.Response:
        from dia.suggestions import Suggestions

        key, action = request.match_info["key"], request.match_info["action"]
        suggestions = Suggestions(self.dia)
        if action == "dismiss":
            suggestions.dismiss(key)
            return web.json_response({"message": "dismissed"})
        if action != "accept":
            raise web.HTTPNotFound(text=f"unknown action {action}")
        if not any(s["key"] == key for s in suggestions.open()):
            raise ValueError(f"no open suggestion {key}")

        async def run(on_start: Any) -> Any:
            report = await suggestions.accept(key, on_start)
            if report is None:  # nothing to run: it was a reminder
                raise RuntimeError("nothing to run")
            return report

        action_of = next(s for s in suggestions.open() if s["key"] == key).get("action")
        if not action_of:
            suggestions._take(key, "accepted")
            return web.json_response({"message": "noted"})
        task = await self._start(run)
        return web.json_response(task_json(task), status=202)

    async def work_profiles(self, request: web.Request) -> web.Response:
        from dia import work

        state = work._state(self.dia)
        return web.json_response(
            {"profiles": work.profiles(self.dia), "current": state.get("current")}
        )

    async def work_action(self, request: web.Request) -> web.Response:
        from dia import work

        body = await request.json() if request.can_read_body else {}
        action = request.match_info["action"]
        if action == "start":
            text = await work.start(self.dia, body.get("name", ""), not body.get("no_apps"))
        elif action == "stop":
            text = await work.stop(self.dia, body.get("name") or None, body.get("note", ""))
        else:
            raise web.HTTPNotFound(text=f"unknown action {action}")
        return web.json_response({"text": text})

    async def list_goals(self, request: web.Request) -> web.Response:
        from dia import goals

        found = goals.goals(self.dia, active=False)
        return web.json_response(
            [{**task_json(g), "blockers": goals.blockers(self.dia, g)} for g in found]
        )

    async def create_goal(self, request: web.Request) -> web.Response:
        from dia import goals

        body = await request.json()
        weeks = int(body["weeks"]) if body.get("weeks") else None
        goal = await goals.create(self.dia, body["project"], body["goal"], weeks)
        return web.json_response(task_json(goal), status=201)

    async def goal_action(self, request: web.Request) -> web.Response:
        from dia import goals

        goal_id, action = request.match_info["id"], request.match_info["action"]
        if action == "review":
            return web.json_response(await goals.review(self.dia, goal_id))
        if action == "approve":
            mission = await goals.approve(self.dia, goal_id)
            return web.json_response({"mission": task_json(mission) if mission else None})
        if action == "close":
            goals.close(self.dia, goal_id)
            return web.json_response({"message": "closed"})
        raise web.HTTPNotFound(text=f"unknown action {action}")

    async def list_missions(self, request: web.Request) -> web.Response:
        missions = Missions(self.dia)
        return web.json_response(
            [
                {**task_json(t), "budget": missions.budget(t)}
                for t in self.dia.store.recent(200)
                if t.mode == "mission"
            ]
        )

    async def create_mission(self, request: web.Request) -> web.Response:
        body = await request.json()
        budget = {k: float(body[k]) for k in ("calls", "minutes") if body.get(k)}
        mission = await Missions(self.dia).create(
            body["project"], body["goal"], budget=budget, priority=body.get("priority", "normal")
        )
        return web.json_response(task_json(mission), status=201)

    async def cancel_mission(self, request: web.Request) -> web.Response:
        Missions(self.dia).cancel(request.match_info["id"])
        return web.json_response({"message": "no further steps will start"})

    # -------------------------------------------------------------- memory ---

    def _memory(self) -> Any:
        if not self.dia.memory:
            raise ValueError("memory is off: add [memory] to the config (docs/ASSISTANT.md)")
        return self.dia.memory

    async def memory_overview(self, request: web.Request) -> web.Response:
        memory = self.dia.memory
        pending = [
            {
                "task_id": t.id,
                "project": t.project,
                "prompt": t.prompt[:120],
                "facts": t.details.get("learn", []),
            }
            for t in self.dia.pending_facts()
        ]
        return web.json_response(
            {
                "enabled": bool(memory),
                "describe": memory.describe() if memory else None,
                "folder": getattr(memory, "folder", None),
                "notes": memory.notes() if memory else [],
                "howtos": memory.howtos() if memory else [],
                "pending": pending,
            }
        )

    async def memory_note(self, request: web.Request) -> web.Response:
        path = request.query["path"]
        return web.json_response({"path": path, "text": self._memory().read_note(path)})

    async def memory_write(self, request: web.Request) -> web.Response:
        body = await request.json()
        self._memory().write_note(body["path"], body["text"])
        self.dia.audit("memory.edit", body["path"])
        return web.json_response({"message": "saved"})

    async def memory_search(self, request: web.Request) -> web.Response:
        hits = await asyncio.to_thread(self._memory().search, request.query.get("q", ""), 10)
        return web.json_response(
            [
                {
                    "path": h.path.as_posix(),
                    "link": h.link,
                    "score": round(h.score, 2),
                    "snippet": h.snippet,
                }
                for h in hits
            ]
        )

    async def system_info(self, request: web.Request) -> web.Response:
        from dia import system

        snap, top = await asyncio.gather(system.snapshot(), system.processes(8))
        return web.json_response(
            {**snap.to_dict(), "cpu_temp": snap.cpu_temp, "top": [asdict(p) for p in top]}
        )

    async def security_report(self, request: web.Request) -> web.Response:
        from dia import security

        rep = await security.report(self.dia, projects=request.query.get("projects") != "0")
        return web.json_response(
            {**rep.to_dict(), "text": security.describe(rep, self.dia.config.language)}
        )

    async def create_council(self, request: web.Request) -> web.Response:
        from dia.council import convene

        body = await request.json()
        self._spawn(
            self._report_errors(
                "council",
                convene(
                    self.dia,
                    body["question"],
                    body.get("project") or None,
                    body.get("members") or None,
                ),
            )
        )
        return web.json_response({"message": "the council is meeting"}, status=202)

    async def create_research(self, request: web.Request) -> web.Response:
        """A web research report on a topic (minutes): the task appears at once."""
        from dia.research import research

        body = await request.json()
        task = await self._start(
            lambda on_start: research(
                self.dia, body["topic"], body.get("project") or None, body.get("agent"), on_start
            )
        )
        return web.json_response(task_json(task), status=202)

    async def create_experiment(self, request: web.Request) -> web.Response:
        """The same change several ways (agents or approaches), each measured."""
        from dia.experiments import plan_variants, run_experiment

        body = await request.json()
        agents = body.get("agents") or None
        approaches = body.get("approaches") or None
        plan_variants(self.dia, agents, approaches)  # a bad request fails here, not later
        task = await self._start(
            lambda on_start: run_experiment(
                self.dia, body["project"], body["question"], agents, approaches, on_start
            )
        )
        return web.json_response(task_json(task), status=202)

    async def create_debug(self, request: web.Request) -> web.Response:
        """A bug for the debugging swarm: hypotheses, each checked by a test."""
        from dia.swarm import debug

        body = await request.json()
        project = self.dia.config.project(body["project"]).name
        task = await self._start(
            lambda on_start: debug(
                self.dia, project, body["bug"], body.get("agents") or None, on_start
            )
        )
        return web.json_response(task_json(task), status=202)

    async def create_scenario(self, request: web.Request) -> web.Response:
        """ "Does parry work?": an agent writes a test for it, Dia runs it."""
        from dia.scenario import check_scenario

        body = await request.json()
        task = await self._start(
            lambda on_start: check_scenario(
                self.dia, body["project"], body["scenario"], body.get("agent"), on_start
            )
        )
        return web.json_response(task_json(task), status=202)

    async def create_build(self, request: web.Request) -> web.Response:
        from dia.release import Releases

        body = await request.json()
        presets = body.get("presets") or None
        self._spawn(
            self._report_errors(
                "build",
                Releases(self.dia).build(
                    body["project"],
                    presets,
                    body.get("ref"),
                    body.get("version"),
                    write_changelog=bool(body.get("write_changelog")),
                ),
            )
        )
        return web.json_response({"message": "build started"}, status=202)

    async def project_changelog(self, request: web.Request) -> web.Response:
        from dia.release import Releases

        text = await Releases(self.dia).changelog(
            request.match_info["name"],
            since=request.query.get("since") or None,
            write=request.query.get("write") == "1",
        )
        return web.json_response({"changelog": text})

    async def stop(self, request: web.Request) -> web.Response:
        """Emergency stop; allowed from paired devices too (it only ever stops things)."""
        stopped = await self.dia.stop_all()
        return web.json_response({"stopped": stopped, "message": f"stopped {len(stopped)}"})

    async def quiet(self, request: web.Request) -> web.Response:
        if "on" in request.query:
            on = request.query["on"] not in ("0", "false", "off")
        else:
            on = bool((await request.json()).get("on", True))
        self.dia.set_quiet(on)
        return web.json_response({"quiet": on})

    async def screen(self, request: web.Request) -> web.Response:
        """Switch screen access; turning it ON is only possible at this computer."""
        on = bool((await request.json()).get("on", False))
        if on and request[DEVICE]:
            raise web.HTTPForbidden(text="screen access can only be switched on at the computer")
        self.dia.set_screen(on)
        return web.json_response({"screen": on})

    async def project_benchmarks(self, request: web.Request) -> web.Response:
        project = self.dia.config.project(request.match_info["name"])
        return web.json_response(
            {
                "command": project.options.get("benchmark"),
                "results": self.dia.store.benchmarks(project.name, limit=50),
            }
        )

    async def project_impact(self, request: web.Request) -> web.Response:
        from dia.impact import impact

        result, text = await impact(
            self.dia, request.match_info["name"], request.query.get("q", ""), False
        )
        return web.json_response({**result.to_dict(), "text": text})

    async def project_debt(self, request: web.Request) -> web.Response:
        from dia import debt

        project = self.dia.config.project(request.match_info["name"]).name
        if request.query.get("refresh") or not debt.saved(self.dia, project):
            items = await debt.register(self.dia, project, bool(request.query.get("deps")))
        else:
            items = debt.saved(self.dia, project)
        return web.json_response({"items": items, "text": debt.describe(items)})

    async def fix_debt(self, request: web.Request) -> web.Response:
        from dia import debt

        project = self.dia.config.project(request.match_info["name"]).name
        number = int(request.match_info["n"])
        if not any(i.get("n") == number for i in debt.saved(self.dia, project)):
            raise ValueError(f"no debt item {number}")
        task = await self._start(lambda on_start: debt.fix(self.dia, project, number, on_start))
        return web.json_response(task_json(task), status=202)

    async def check_contradictions(self, request: web.Request) -> web.Response:
        """An agent compares the project's notes and docs with its code (minutes)."""
        from dia.contradictions import check

        project = self.dia.config.project(request.match_info["name"]).name
        task = await self._start(lambda on_start: check(self.dia, project, on_start=on_start))
        return web.json_response(task_json(task), status=202)

    async def project_balance(self, request: web.Request) -> web.Response:
        from dia.balance import analyze, data_folder, describe, read_events

        project = self.dia.config.project(request.match_info["name"])
        folder = data_folder(project.options)
        events, files = (
            await asyncio.to_thread(read_events, folder) if folder and folder.is_dir() else ([], 0)
        )
        result = analyze(events, project.options.get("balance") or {})
        result.sessions = files
        text = describe(result, self.dia.config.language)
        return web.json_response({**result.to_dict(), "text": text})

    async def project_analysis(self, request: web.Request) -> web.Response:
        from dia.godot_analysis import analyze, describe

        project = self.dia.config.project(request.match_info["name"])
        result = await asyncio.to_thread(
            analyze, project.path, self.dia.config.section("godot_analysis")
        )
        text = describe(result, self.dia.config.language)
        return web.json_response({**result.to_dict(), "text": text})

    async def tidy_plan(self, request: web.Request) -> web.Response:
        """A preview of tidying a folder; nothing moves until .../apply."""
        from dia.tidy import Tidy, summary

        plan = Tidy(self.dia).plan(request.query.get("folder"))
        return web.json_response({**plan, "text": summary(plan, self.dia.config.language)})

    async def tidy_action(self, request: web.Request) -> web.Response:
        from dia.tidy import Tidy

        tidy, plan_id = Tidy(self.dia), request.match_info["id"]
        action = request.match_info["action"]
        if action == "apply":
            return web.json_response(tidy.apply(plan_id))
        if action == "undo":
            return web.json_response(tidy.undo(plan_id))
        raise web.HTTPNotFound(text=f"unknown action {action}")

    async def held_notifications(self, request: web.Request) -> web.Response:
        attention = Attention(self.dia)
        return web.json_response(
            {
                "quiet_hours": attention.quiet_hours(),
                "window": attention.options.get("quiet_hours", ""),
                "budget": attention.options.get("budget", 0),
                "held": attention.held(),
            }
        )

    async def camera(self, request: web.Request) -> web.Response:
        """Switch the camera; turning it ON is only possible at this computer."""
        on = bool((await request.json()).get("on", False))
        if on and request[DEVICE]:
            raise web.HTTPForbidden(text="the camera can only be switched on at the computer")
        self.dia.set_camera(on)
        return web.json_response({"camera": on})

    async def list_preferences(self, request: web.Request) -> web.Response:
        from dia.preferences import Preferences

        return web.json_response(Preferences(self.dia.config).snapshot())

    async def add_preference(self, request: web.Request) -> web.Response:
        from dia.persona import add_preference

        text = add_preference(self.dia, str((await request.json()).get("text", "")))
        return web.json_response({"text": text})

    async def decide_preference(self, request: web.Request) -> web.Response:
        from dia.preferences import Preferences

        prefs = Preferences(self.dia.config)
        index, action = int(request.match_info["index"]), request.match_info["action"]
        try:
            if action == "remove":
                text = prefs.remove(index)
            elif action in ("accept", "reject"):
                text = prefs.decide(index, action == "accept")
            else:
                raise web.HTTPNotFound(text=f"unknown action {action}")
        except IndexError as exc:
            raise web.HTTPNotFound(text=str(exc)) from None
        self.dia.audit(f"preference.{action}", None, text)
        return web.json_response(prefs.snapshot())

    async def resume(self, request: web.Request) -> web.Response:
        await self.dia.resume()
        return web.json_response({"message": "resumed"})

    async def audit_log(self, request: web.Request) -> web.Response:
        limit = max(1, min(1000, int(request.query.get("limit", 200))))
        rows = self.dia.store.audit(limit, request.query.get("action"), request.query.get("target"))
        return web.json_response(rows)

    async def usage(self, request: web.Request) -> web.Response:
        days = max(1, min(365, int(request.query.get("days", 30))))
        data = self.dia.store.usage(days)
        data["limits"] = self.dia.limit_status()
        from dia.benchmark import agent_stats, suggestions

        data["agents_by_project"] = agent_stats(self.dia.store, max(days, 30))
        data["suggestions"] = suggestions(self.dia.config, data["agents_by_project"])
        from dia.scorecard import scorecard

        data["scorecard"] = scorecard(self.dia.store, int(request.query.get("weeks", 8)))
        return web.json_response(data)

    async def list_decisions(self, request: web.Request) -> web.Response:
        project = request.query.get("project") or None
        limit = max(1, min(1000, int(request.query.get("limit", 100))))
        return web.json_response(self.dia.store.decisions(project, limit=limit))

    async def get_profile(self, request: web.Request) -> web.Response:
        from dia import profile

        return web.json_response(
            {"text": profile.read(self.dia), "proposal": profile.proposal(self.dia)}
        )

    async def put_profile(self, request: web.Request) -> web.Response:
        from dia import profile

        body = await request.json()
        profile.write(self.dia, str(body.get("text", "")))
        return web.json_response({"message": "saved"})

    async def profile_action(self, request: web.Request) -> web.Response:
        from dia import profile

        action = request.match_info["action"]
        if action == "accept":
            return web.json_response({"text": profile.accept(self.dia)})
        if action == "update":
            return web.json_response({"proposal": await profile.update(self.dia)})
        raise web.HTTPNotFound(text=f"unknown action {action}")

    async def ask_why(self, request: web.Request) -> web.Response:
        from dia.decisions import describe, why

        project = request.query.get("project") or None
        found = await why(self.dia, request.query.get("q", ""), project)
        return web.json_response({**found, "text": describe(found)})

    async def get_scorecard(self, request: web.Request) -> web.Response:
        from dia.scorecard import scorecard

        weeks = max(1, min(104, int(request.query.get("weeks", 8))))
        return web.json_response(scorecard(self.dia.store, weeks))

    # ---------------------------------------------------------------- push ---

    async def push_info(self, request: web.Request) -> web.Response:
        if not push_available():
            return web.json_response({"available": False})
        device = request[DEVICE].name if request[DEVICE] else None
        mine = [
            s for s in self.push.subscriptions() if s.get("device") == (device or "this computer")
        ]
        return web.json_response(
            {"available": True, "key": self.push.public_key(), "subscriptions": len(mine)}
        )

    async def push_subscribe(self, request: web.Request) -> web.Response:
        device = request[DEVICE].name if request[DEVICE] else None
        self.push.subscribe(await request.json(), device)
        return web.json_response({"message": "subscribed"}, status=201)

    async def push_unsubscribe(self, request: web.Request) -> web.Response:
        endpoint = (await request.json()).get("endpoint", "")
        return web.json_response({"removed": self.push.unsubscribe(endpoint)})

    async def push_test(self, request: web.Request) -> web.Response:
        sent = await self.push.send("Dia", "🔔 Test", "/", tag="test")
        return web.json_response({"message": f"sent to {sent} device(s)"})

    # ----------------------------------------------------------------- pwa ---

    async def manifest(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "name": "Dia",
                "short_name": "Dia",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "background_color": "#0b0b0f",
                "theme_color": "#0b0b0f",
                "icons": [
                    *(
                        {
                            "src": f"/static/icons/icon-{size}.png",
                            "sizes": f"{size}x{size}",
                            "type": "image/png",
                            "purpose": "any",
                        }
                        for size in (192, 512)
                    ),
                    *(
                        {
                            "src": f"/static/icons/maskable-{size}.png",
                            "sizes": f"{size}x{size}",
                            "type": "image/png",
                            "purpose": "maskable",
                        }
                        for size in (192, 512)
                    ),
                    {"src": "/static/icons/dia.svg", "sizes": "any", "type": "image/svg+xml"},
                ],
            },
            content_type="application/manifest+json",
        )

    async def service_worker(self, request: web.Request) -> web.FileResponse:
        response = web.FileResponse(STATIC / "sw.js")
        response.headers["Cache-Control"] = "no-cache"
        return response

    # --------------------------------------------------------------- tasks ---

    async def tasks(self, request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", 50))
        tasks = self.dia.store.recent(limit, request.query.get("project") or None)
        return web.json_response([task_json(t) for t in tasks])

    def _get(self, request: web.Request) -> TaskRecord:
        task = self.dia.store.get(request.match_info["id"])
        if not task:
            raise web.HTTPNotFound(text="no such task")
        return task

    async def task(self, request: web.Request) -> web.Response:
        task = self._get(request)
        data = task_json(task)
        data["has_test_log"] = self.dia.test_log_path(task.id).exists()
        return web.json_response(data)

    async def diff(self, request: web.Request) -> web.Response:
        return web.Response(text=await self.dia.task_diff(self._get(request).id))

    async def tests(self, request: web.Request) -> web.Response:
        path = self.dia.test_log_path(self._get(request).id)
        if not path.exists():
            raise web.HTTPNotFound(text="no test log for this task")
        return web.Response(text=path.read_text())

    async def create_task(self, request: web.Request) -> web.Response:
        body = await request.json()
        mode = Mode.READ_ONLY if body.get("mode") == "read-only" else Mode.EDIT
        task = await self._start(
            lambda on_start: self.dia.run_task(
                body["project"],
                body["prompt"],
                body.get("agent") or None,
                mode,
                on_start=on_start,
                review=body.get("review"),
                model=body.get("model") or None,
            )
        )
        return web.json_response(task_json(task), status=201)

    async def create_plan(self, request: web.Request) -> web.Response:
        body = await request.json()
        plan = await self.dia.create_plan(
            body["project"],
            body["goal"],
            pipeline=body.get("pipeline") or None,
            planner=body.get("planner") or None,
        )
        return web.json_response(task_json(plan), status=201)

    async def task_action(self, request: web.Request) -> web.Response:
        task = self._get(request)
        action = request.match_info["action"]
        body = await request.json() if request.can_read_body else {}
        reason = (body.get("reason") or None) if isinstance(body, dict) else None
        if action == "merge":
            override = (body.get("override") or None) if isinstance(body, dict) else None
            sha = await self.dia.merge_task(task.id, reason, override)
            return web.json_response({"message": f"merged as {sha[:10]}"})
        if action == "discard":
            await self.dia.discard_task(task.id, reason)
            return web.json_response({"message": "discarded"})
        if action == "publish":
            publication = await self.dia.publish_task(task.id)
            return web.json_response({"message": publication.message, "url": publication.url})
        if action == "publish-itch":
            from dia.release import Releases

            pushed = await Releases(self.dia).publish_itch(task.id)
            return web.json_response({"message": "published: " + ", ".join(pushed)})
        if action == "publish-steam":
            from dia.release import Releases

            target = await Releases(self.dia).publish_steam(task.id)
            return web.json_response({"message": f"published: {target}"})
        if action == "learn":
            stored = self.dia.decide_facts(task.id, body.get("accept"), body.get("reject"))
            self._spawn(
                self._broadcast({"type": "task", "task": task_json(self.dia.store.get(task.id))})
            )
            return web.json_response({"message": f"remembered {len(stored)}", "stored": stored})
        if action == "rollback":  # prepared as a new task; merging it stays a click
            revert = await self.dia.rollback_task(task.id, reason)
            return web.json_response(task_json(revert), status=201)
        if action == "howto":  # propose how this task was done, as a how-to
            howto = await self.dia.propose_howto(task.id)
            self._spawn(
                self._broadcast({"type": "task", "task": task_json(self.dia.store.get(task.id))})
            )
            return web.json_response({"howto": howto})
        if action == "howto-accept":
            path = self.dia.accept_howto(task.id, body)
            self._spawn(
                self._broadcast({"type": "task", "task": task_json(self.dia.store.get(task.id))})
            )
            return web.json_response({"message": f"saved {path}", "path": path})
        if action == "fix-build":
            started = await self._start(lambda on_start: self.dia.fix_build(task.id, on_start))
            return web.json_response(task_json(started), status=202)
        if action == "fix-bug":  # the confirmed cause of a debugging task
            from dia.swarm import fix

            started = await self._start(lambda on_start: fix(self.dia, task.id, on_start))
            return web.json_response(task_json(started), status=202)
        if action == "run-plan":
            started = await self._start(lambda on_start: self.dia.run_plan(task.id, on_start))
            return web.json_response(task_json(started), status=202)
        long_running = {
            "review": self.dia.review_task,
            "fix-ci": self.dia.fix_ci,
            "address-comments": self.dia.address_comments,
        }
        if action not in long_running:
            raise web.HTTPNotFound(text=f"unknown action {action}")
        self._spawn(self._report_errors(task.id, long_running[action](task.id)))
        return web.json_response({"message": f"{action} started"}, status=202)

    async def _report_errors(self, task_id: str, coro: Any) -> None:
        try:
            await coro
        except Exception as exc:
            await self._broadcast({"type": "error", "task_id": task_id, "message": str(exc)})

    # ---------------------------------------------------------------- chat ---

    async def chat(self, request: web.Request) -> web.Response:
        """Free-form request, understood by the brain, as on Discord or by voice."""
        body = await request.json()
        text = body["text"]
        device = request[DEVICE].name if request[DEVICE] else "ui"
        surface = "phone" if request[DEVICE] else "desktop"
        conversation = device
        if session := body.get("session"):
            self.dia.conversations._session(session)  # it must exist (KeyError: 400)
            conversation = session
            provider, model = self.dia.conversations.engine(session)
            if provider != "dia":
                return web.json_response(await self._plain_chat(session, provider, model, text))
        intent = await self.assistant.interpret(text, conversation=conversation, surface=surface)
        answer: dict[str, Any] = {"action": intent.action, "brain": intent.brain}
        starts_plan = intent.action == "confirm" and not self.assistant.pending_action
        if intent.action in ("run", "ask", "scenario", "research") or starts_plan:

            async def run(on_start: Any) -> TaskReport:
                return (await self.assistant.execute(intent, on_start=on_start)).report

            task = await self._start(run)
            answer.update(reply=intent.reply or "", task=task_json(task))
        else:
            response = await self.assistant.execute(intent)
            answer["reply"] = response.text
            plan_id = self.dia.conversations.pending_plan(conversation)
            if intent.action in ("plan", "mission") and plan_id:
                answer["plan"] = task_json(self.dia.store.get(plan_id))
        return web.json_response(answer)

    async def _plain_chat(self, session: str, provider: str, model: str, text: str) -> dict:
        """A session that talks straight to a model (dia.plainchat), not to Dia."""
        from dia.plainchat import reply

        chats = self.dia.conversations
        history = chats.messages(session)
        chats.add_message(session, "me", text)
        try:
            answer = await reply(self.dia, provider, model, history, text)
        except (RuntimeError, ValueError, ConfigError) as exc:
            answer = f"⚠ {exc}"
        chats.add_message(session, "dia", answer, model=f"{provider}:{model or 'default'}")
        return {"action": "chat", "reply": answer, "provider": provider, "model": model}

    async def chat_providers(self, request: web.Request) -> web.Response:
        from dia.plainchat import providers

        return web.json_response(await asyncio.to_thread(providers, self.dia))

    async def list_sessions(self, request: web.Request) -> web.Response:
        return web.json_response(self.dia.conversations.sessions())

    async def create_session(self, request: web.Request) -> web.Response:
        body = await request.json() if request.can_read_body else {}
        key = self.dia.conversations.create(
            str(body.get("title", "")), str(body.get("provider", "")), str(body.get("model", ""))
        )
        return web.json_response({"id": key}, status=201)

    async def get_session(self, request: web.Request) -> web.Response:
        chats = self.dia.conversations
        key = request.match_info["id"]
        chats._session(key)
        return web.json_response({"id": key, "messages": chats.messages(key)})

    async def rename_session(self, request: web.Request) -> web.Response:
        """Rename a session, or choose who answers in it (``provider``, ``model``)."""
        body = await request.json()
        key = request.match_info["id"]
        if "title" in body:
            self.dia.conversations.rename(key, str(body["title"]))
        if "provider" in body:
            provider, model = str(body["provider"]), str(body.get("model", ""))
            self.dia.conversations.set_engine(key, provider, model)
        return web.json_response({"message": "saved"})

    async def delete_session(self, request: web.Request) -> web.Response:
        self.dia.conversations.delete(request.match_info["id"])
        return web.json_response({"message": "deleted"})

    # --------------------------------------------------------------- voice ---

    async def voice(self, request: web.Request) -> web.Response:
        """Same as `dia voice <action>`: drives the voice channel of `dia serve`."""
        from dia.channels.voice import send_command, socket_path

        action = request.match_info["action"]
        if action not in ("toggle", "start", "stop", "cancel", "ping"):
            raise web.HTTPNotFound(text=f"unknown voice action {action}")
        options = next(
            (o for n, o in self.dia.config.channels.items() if o.get("type", n) == "voice"), None
        )
        if options is None:
            return web.json_response({"error": "voice is not configured"}, status=409)
        path = Path(os.path.expanduser(options.get("socket", str(socket_path()))))
        try:
            reply = await send_command(action, path)
        except RuntimeError as exc:
            return web.json_response({"error": str(exc)}, status=409)
        return web.json_response({"reply": reply})

    # -------------------------------------------------------------- config ---

    async def get_config(self, request: web.Request) -> web.Response:
        source = self.dia.config.source
        return web.json_response(
            {
                "path": str(source) if source else None,
                "text": source.read_text() if source and source.exists() else "",
                "shadowed": [str(p) for p in self.dia.config.shadowed],
            }
        )

    async def put_config(self, request: web.Request) -> web.Response:
        """Validate and save the config file (the old one is kept as .bak)."""
        source = self.dia.config.source
        if not source:
            raise ConfigError("Dia was started without a config file")
        text = (await request.json())["text"]
        try:
            parse_config(tomllib.loads(text), source)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"invalid TOML: {exc}") from None
        if source.exists():
            source.with_suffix(source.suffix + ".bak").write_text(source.read_text())
        source.write_text(text)
        self.dia.audit("config.save", str(source))
        return web.json_response({"saved": str(source), "restart_required": True})

    # -------------------------------------------------------------- themes ---

    async def themes(self, request: web.Request) -> web.Response:
        built_in = sorted(p.stem for p in (STATIC / "themes").glob("*.css"))
        user_dir = user_themes_dir()
        custom = sorted(p.stem for p in user_dir.glob("*.css")) if user_dir.is_dir() else []
        return web.json_response({"built_in": built_in, "custom": custom, "dir": str(user_dir)})

    async def theme_css(self, request: web.Request) -> web.FileResponse:
        name = request.match_info["name"]
        for folder in (user_themes_dir(), STATIC / "themes"):
            path = folder / f"{name}.css"
            if path.is_file() and path.resolve().parent == folder.resolve():
                return web.FileResponse(path, headers={"Content-Type": "text/css"})
        raise web.HTTPNotFound(text="no such theme")

    # ----------------------------------------------------------- live data ---

    async def websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._sockets.add(ws)
        try:
            async for message in ws:
                if message.type == WSMsgType.ERROR:
                    break
        finally:
            self._sockets.discard(ws)
        return ws

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, default=str)
        for ws in list(self._sockets):
            try:
                await ws.send_str(data)
            except (ConnectionError, RuntimeError):
                self._sockets.discard(ws)

    def _on_task_saved(self, task: TaskRecord) -> None:
        if self._sockets:
            self._spawn(self._broadcast({"type": "task", "task": task_json(task)}))

    def _on_audit(self, entry: dict[str, Any]) -> None:
        self._spawn(self._broadcast({"type": "audit", "entry": entry}))

    async def _on_event(self, event: Event) -> None:
        if event.kind == "voice":
            self.voice_state = event.message.split(":", 1)[0]
        await self._broadcast(
            {
                "type": "event",
                "kind": event.kind,
                "task_id": event.task.id if event.task else None,
                "message": event.message,
            }
        )
