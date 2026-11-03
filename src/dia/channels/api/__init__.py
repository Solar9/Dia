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
import secrets
from typing import TYPE_CHECKING, Any

from aiohttp import WSMsgType, web

from dia.assistant import Assistant
from dia.audit import ACTOR
from dia.channels import Channel
from dia.channels.api import chat, cli_sessions, memory, projects, settings, system, tasks, work
from dia.channels.api._util import (
    DEFAULT_PORT,
    DEVICE,
    LOOPBACK,
    NEVER_REMOTE,
    OWNER_ONLY,
    STATIC,
    api_token,
    log,
    task_json,
)
from dia.channels.api.chat import ChatRoutes
from dia.channels.api.cli_sessions import CliSessionRoutes
from dia.channels.api.memory import MemoryRoutes
from dia.channels.api.projects import ProjectRoutes
from dia.channels.api.settings import SettingsRoutes
from dia.channels.api.system import SystemRoutes
from dia.channels.api.tasks import TaskRoutes
from dia.channels.api.work import WorkRoutes
from dia.core.config import ConfigError
from dia.core.devices import Devices, public_url
from dia.core.orchestrator import Event, TaskActionError
from dia.core.store import TaskRecord
from dia.desktop.push import Push

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator


ROUTE_MODULES = (tasks, cli_sessions, chat, settings, projects, memory, work, system)


class ApiChannel(
    TaskRoutes,
    CliSessionRoutes,
    ChatRoutes,
    SettingsRoutes,
    ProjectRoutes,
    MemoryRoutes,
    WorkRoutes,
    SystemRoutes,
    Channel,
):
    kind = "api"

    def __init__(self, name: str, options: dict[str, Any], dia: Orchestrator) -> None:
        super().__init__(name, options, dia)
        self.port = int(options.get("port", DEFAULT_PORT))
        self.token = api_token(dia.config.data_dir)
        self.assistant = Assistant(dia)
        self._sockets: set[web.WebSocketResponse] = set()
        self._background: set[asyncio.Task] = set()
        self.voice_state = "idle"
        self._diff_stats: dict[tuple[str, str], dict[str, int] | None] = {}
        self._talk_engines: Any = None  # the phone's own voice (dia.voice.talk), on first use
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

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self._guard])
        r = app.router
        r.add_get("/", self.index)
        r.add_get("/ws", self.websocket)
        r.add_get("/manifest.webmanifest", self.manifest)
        r.add_get("/sw.js", self.service_worker)
        for module in ROUTE_MODULES:
            r.add_routes(module.routes(self))
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
            response = await handler(request)
        except (TaskActionError, ConfigError, LookupError, ValueError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        # The Qt window and the service worker keep a copy of the shell: always
        # revalidate HTML/JS/CSS so an updated checkout shows up after a reload.
        if request.method == "GET" and (
            request.path == "/" or request.path.endswith((".js", ".css", ".html"))
        ):
            response.headers["Cache-Control"] = "no-cache"
        return response

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

    async def index(self, request: web.Request) -> web.Response:
        html = (STATIC / "index.html").read_text()
        app_v = int((STATIC / "app.js").stat().st_mtime)
        css_v = int((STATIC / "style.css").stat().st_mtime)
        html = html.replace('src="/static/app.js"', f'src="/static/app.js?v={app_v}"')
        html = html.replace('href="/static/style.css"', f'href="/static/style.css?v={css_v}"')
        return web.Response(text=html, content_type="text/html", charset="utf-8")

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

    def _talk(self) -> Any:
        if self._talk_engines is None:
            from dia.voice.talk import Talk

            self._talk_engines = Talk.from_config(self.dia.config)
        return self._talk_engines

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
