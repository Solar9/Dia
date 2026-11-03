"""API routes: cli sessions."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from aiohttp import web

from dia.agents import Mode
from dia.channels.api._util import ApiBase


class CliSessionRoutes(ApiBase):
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

    async def cli_new_session(self, request: web.Request) -> web.Response:
        """A new agent session started in the app: the chosen agent and model, in a
        project's folder; its first answer opens a conversation kept like a taken-over one."""
        from dia.agents import AgentRequest
        from dia.sessions import RESUME_HINT, Captured

        body = await request.json()
        text = str(body.get("text", "")).strip()
        if not text:
            raise ValueError("write the first message")
        name = str(body.get("agent", ""))
        options = self.dia.config.agents.get(name)
        if options is None or options.get("type", name) not in RESUME_HINT:
            kinds = ", ".join(RESUME_HINT)
            raise ValueError(f"pick an agent whose conversation can go on ({kinds})")
        project = self.dia.config.project(str(body.get("project", "")))
        model = str(body.get("model") or "").strip() or None
        mode = Mode.READ_ONLY if str(body.get("mode", "edit")) == "read-only" else Mode.EDIT
        use_web = bool(body.get("web"))
        # Interactive: never wait for a usage-limit reset, and always cap the call
        # so the UI cannot sit on "Starting…" forever when the CLI hangs.
        used, result = await self.dia.call_agent(
            self.dia.config.agent(name),
            AgentRequest(
                prompt=text,
                cwd=project.path,
                mode=mode,
                model=model,
                web=use_web,
                timeout=600,
            ),
            purpose="cli-session",
        )
        if not result.success:
            raise ValueError(f"{used.name}: {result.error or 'no answer'}")
        kind = self.dia.config.agents.get(used.name, {}).get("type", used.name)
        if not result.session_id or kind not in RESUME_HINT:
            raise ValueError(f"{used.name} answered but gave no conversation id to continue")
        item = Captured(
            id=result.session_id,
            kind=kind,
            cwd=str(project.path),
            model=model,
            taken_at=datetime.now().isoformat(timespec="seconds"),
            started_in_app=True,
            mode=mode.value,
            web=use_web,
        )
        self._captured().add(item)
        self.dia.audit("cli.new", item.id, f"{kind} in {project.path}")
        return web.json_response(
            {**item.__dict__, "resume": item.resume, "reply": result.summary}, status=201
        )

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

    async def cli_commands(self, request: web.Request) -> web.Response:
        """Slash commands of each agent CLI (Claude Code, Codex, Cursor), as in a terminal."""
        from dia.sessions import RESUME_HINT, agent_commands

        language = self.dia.config.language
        return web.json_response({kind: agent_commands(kind, language) for kind in RESUME_HINT})

    async def cli_captured_update(self, request: web.Request) -> web.Response:
        """Change a taken-over session (model, mode, web) without sending a message."""
        item = self._held(request)
        body = await request.json()
        fields: dict[str, object] = {}
        if "model" in body:
            fields["model"] = str(body.get("model") or "").strip() or None
        if "mode" in body:
            mode = str(body.get("mode") or "edit")
            fields["mode"] = "read-only" if mode == "read-only" else "edit"
        if "web" in body:
            fields["web"] = bool(body.get("web"))
        updated = self._captured().update(item.id, **fields) if fields else item
        return web.json_response({**updated.__dict__, "resume": updated.resume})

    async def cli_captured_send(self, request: web.Request) -> web.Response:
        """Continue a taken-over conversation: the CLI resumes it headless, in its folder."""
        from dia.agents import AgentRequest
        from dia.core import plugins

        item = self._held(request)
        body = await request.json()
        text = str(body.get("text", "")).strip()
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
        mode = Mode.READ_ONLY if (item.mode or "edit") == "read-only" else Mode.EDIT
        if str(body.get("mode") or "") == "read-only":
            mode = Mode.READ_ONLY
        elif str(body.get("mode") or "") == "edit":
            mode = Mode.EDIT
        use_web = bool(body["web"]) if "web" in body else bool(item.web)
        used, result = await self.dia.call_agent(
            agent,
            AgentRequest(
                prompt=text,
                cwd=Path(item.cwd),
                mode=mode,
                session_id=item.id,
                model=item.model,
                web=use_web,
                timeout=600,
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


def routes(ch: CliSessionRoutes) -> list[web.RouteDef]:
    return [
        web.get("/api/cli-sessions", ch.cli_sessions),
        web.get("/api/cli-sessions/{pid}/transcript", ch.cli_transcript),
        web.post("/api/cli-sessions/{pid}/capture", ch.cli_capture),
        web.get("/api/cli-commands", ch.cli_commands),
        web.get("/api/cli-captured", ch.cli_captured),
        web.post("/api/cli-captured", ch.cli_new_session),
        web.get("/api/cli-captured/{id}/transcript", ch.cli_captured_transcript),
        web.post("/api/cli-captured/{id}/send", ch.cli_captured_send),
        web.patch("/api/cli-captured/{id}", ch.cli_captured_update),
        web.delete("/api/cli-captured/{id}", ch.cli_release),
    ]
