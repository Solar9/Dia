"""API routes: memory."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from dia.channels.api._util import ApiBase


class MemoryRoutes(ApiBase):
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

    async def list_preferences(self, request: web.Request) -> web.Response:
        from dia.knowledge.preferences import Preferences

        return web.json_response(Preferences(self.dia.config).snapshot())

    async def add_preference(self, request: web.Request) -> web.Response:
        from dia.persona import add_preference

        text = add_preference(self.dia, str((await request.json()).get("text", "")))
        return web.json_response({"text": text})

    async def decide_preference(self, request: web.Request) -> web.Response:
        from dia.knowledge.preferences import Preferences

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

    async def list_decisions(self, request: web.Request) -> web.Response:
        project = request.query.get("project") or None
        limit = max(1, min(1000, int(request.query.get("limit", 100))))
        return web.json_response(self.dia.store.decisions(project, limit=limit))

    async def get_profile(self, request: web.Request) -> web.Response:
        from dia.knowledge import profile

        return web.json_response(
            {"text": profile.read(self.dia), "proposal": profile.proposal(self.dia)}
        )

    async def put_profile(self, request: web.Request) -> web.Response:
        from dia.knowledge import profile

        body = await request.json()
        profile.write(self.dia, str(body.get("text", "")))
        return web.json_response({"message": "saved"})

    async def profile_action(self, request: web.Request) -> web.Response:
        from dia.knowledge import profile

        action = request.match_info["action"]
        if action == "accept":
            return web.json_response({"text": profile.accept(self.dia)})
        if action == "update":
            return web.json_response({"proposal": await profile.update(self.dia)})
        raise web.HTTPNotFound(text=f"unknown action {action}")

    async def ask_why(self, request: web.Request) -> web.Response:
        from dia.knowledge.decisions import describe, why

        project = request.query.get("project") or None
        found = await why(self.dia, request.query.get("q", ""), project)
        return web.json_response({**found, "text": describe(found)})


def routes(ch: MemoryRoutes) -> list[web.RouteDef]:
    return [
        web.get("/api/memory", ch.memory_overview),
        web.get("/api/memory/note", ch.memory_note),
        web.put("/api/memory/note", ch.memory_write),
        web.get("/api/memory/search", ch.memory_search),
        web.get("/api/preferences", ch.list_preferences),
        web.post("/api/preferences", ch.add_preference),
        web.post("/api/preferences/{index}/{action}", ch.decide_preference),
        web.get("/api/decisions", ch.list_decisions),
        web.get("/api/profile", ch.get_profile),
        web.put("/api/profile", ch.put_profile),
        web.post("/api/profile/{action}", ch.profile_action),
        web.get("/api/why", ch.ask_why),
    ]
