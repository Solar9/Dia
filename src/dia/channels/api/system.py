"""API routes: system."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aiohttp import web

from dia import __version__
from dia.about import snapshot as about_snapshot
from dia.channels.api._util import DEVICE, ApiBase, _models_of, _sandbox_state, read_body
from dia.core import processes
from dia.core.taskstate import RUNNING, counts
from dia.knowledge.attention import Attention


class SystemRoutes(ApiBase):
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
        recent = self.dia.store.recent(200)
        active = [t.id for t in recent if t.status in RUNNING]
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
                "counts": counts(recent),
                "halted": self.dia.halted,
                "quiet": self.dia.quiet,
                "screen": self.dia.screen_enabled,
                "camera": self.dia.camera_enabled,
                "sandbox": _sandbox_state(self.dia.config),
                "quiet_hours": Attention(self.dia).quiet_hours(),
                "processes": len(processes.running()),
                "pending_plan": self.assistant.pending_plan,
                "voice": self.voice_state,
                "talk": self._talk().check() is None,
                **self._theme_status(request),
                "device": request[DEVICE].name if request[DEVICE] else None,
                "device_full": bool(request[DEVICE] and request[DEVICE].full),
                "remote": self.remote,
            }
        )

    async def about(self, request: web.Request) -> web.Response:
        return web.json_response(about_snapshot(self.dia.config))

    async def desktop_state(self, request: web.Request) -> web.Response:
        from dia.desktop import desktop, runtime, service
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
        body = await read_body(request)
        source = self.dia.config.source
        try:
            done = await self._desktop(action, body, source)
        except RuntimeError as exc:  # no systemd, no KDE Plasma 6...
            return web.json_response({"error": str(exc)}, status=409)
        self.dia.audit(f"desktop.{action}", None, "; ".join(done))
        return web.json_response({"message": "\n".join(done) or "-"})

    async def _desktop(self, action: str, body: dict[str, Any], source: Path | None) -> list[str]:
        from dia.desktop import desktop, runtime, service
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

    async def health(self, request: web.Request) -> web.Response:
        """What runs supervised in `dia serve`, and what is restarting (dia.health)."""
        from dia.desktop.health import state

        return web.json_response(state(self.dia))

    async def system_info(self, request: web.Request) -> web.Response:
        from dia.desktop import system

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

    async def tidy_plan(self, request: web.Request) -> web.Response:
        """A preview of tidying a folder; nothing moves until .../apply."""
        from dia.desktop.tidy import Tidy, summary

        plan = Tidy(self.dia).plan(request.query.get("folder"))
        return web.json_response({**plan, "text": summary(plan, self.dia.config.language)})

    async def tidy_action(self, request: web.Request) -> web.Response:
        from dia.desktop.tidy import Tidy

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
        from dia.quality.agent_stats import agent_stats, suggestions

        data["agents_by_project"] = agent_stats(self.dia.store, max(days, 30))
        data["suggestions"] = suggestions(self.dia.config, data["agents_by_project"])
        from dia.quality.scorecard import scorecard

        data["scorecard"] = scorecard(self.dia.store, int(request.query.get("weeks", 8)))
        return web.json_response(data)

    async def get_scorecard(self, request: web.Request) -> web.Response:
        from dia.quality.scorecard import scorecard

        weeks = max(1, min(104, int(request.query.get("weeks", 8))))
        return web.json_response(scorecard(self.dia.store, weeks))

    def _theme_status(self, request: web.Request) -> dict[str, Any]:
        from dia.ui import theme

        data_dir = self.dia.config.data_dir
        name = theme.current(data_dir, "phone" if request[DEVICE] else None)
        return {
            "theme": name,
            "theme_colors": theme.colors(name),
            "widget_theme_colors": theme.colors(theme.current(data_dir, "widget")),
        }


def routes(ch: SystemRoutes) -> list[web.RouteDef]:
    return [
        web.get("/api/status", ch.status),
        web.get("/api/about", ch.about),
        web.get("/api/usage", ch.usage),
        web.get("/api/scorecard", ch.get_scorecard),
        web.post("/api/stop", ch.stop),
        web.get("/api/security", ch.security_report),
        web.get("/api/system", ch.system_info),
        web.get("/api/health", ch.health),
        web.post("/api/quiet", ch.quiet),
        web.post("/api/screen", ch.screen),
        web.post("/api/camera", ch.camera),
        web.get("/api/notifications", ch.held_notifications),
        web.get("/api/tidy", ch.tidy_plan),
        web.post("/api/tidy/{id}/{action}", ch.tidy_action),
        web.post("/api/resume", ch.resume),
        web.get("/api/audit", ch.audit_log),
        web.get("/api/desktop", ch.desktop_state),
        web.post("/api/desktop/{action}", ch.desktop_action),
    ]
