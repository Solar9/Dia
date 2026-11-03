"""API routes: chat."""

from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from typing import Any

from aiohttp import web

from dia.channels.api._util import DEVICE, ApiBase, read_body, task_json
from dia.core.config import ConfigError
from dia.core.orchestrator import TaskReport


class ChatRoutes(ApiBase):
    async def chat(self, request: web.Request) -> web.Response:
        """Free-form request, understood by the brain, as on Discord or by voice."""
        body = await request.json()
        return web.json_response(await self._answer(request, body["text"], body.get("session")))

    async def talk(self, request: web.Request) -> web.Response:
        """A phone's own voice: its recording (WAV) in; what Dia heard, her answer
        and the answer spoken (base64, unless quiet mode) out. All on this computer."""
        from dia.channels.voice import speakable
        from dia.voice.talk import MAX_BYTES, audio_type

        talk = self._talk()
        if problem := talk.check():
            return web.json_response({"error": problem}, status=409)
        if (request.content_length or 0) > MAX_BYTES:
            raise web.HTTPRequestEntityTooLarge(
                max_size=MAX_BYTES, actual_size=request.content_length or 0
            )
        audio = await request.read()
        if audio[:4] != b"RIFF" or len(audio) > MAX_BYTES:
            raise web.HTTPBadRequest(text="expected a WAV recording")
        heard = await talk.hear(audio)
        if not heard:
            return web.json_response({"heard": ""})
        answer = await self._answer(request, heard, request.query.get("session"))
        answer["heard"] = heard
        if answer.get("reply") and not self.dia.quiet:
            spoken = await talk.speak(speakable(answer["reply"]))
            if spoken:
                answer["audio"] = base64.b64encode(spoken).decode()
                answer["audio_type"] = audio_type(spoken)
        return web.json_response(answer)

    async def _answer(self, request: web.Request, text: str, session: str | None) -> dict[str, Any]:
        device = request[DEVICE].name if request[DEVICE] else "ui"
        surface = "phone" if request[DEVICE] else "desktop"
        conversation = device
        if session:
            self.dia.conversations._session(session)  # it must exist (KeyError: 400)
            conversation = session
            provider, model = self.dia.conversations.engine(session)
            if provider != "dia":
                return await self._plain_chat(session, provider, model, text)
        intent = await self.assistant.interpret(text, conversation=conversation, surface=surface)
        answer: dict[str, Any] = {"action": intent.action, "brain": intent.brain}
        starts_plan = intent.action == "confirm" and not self.assistant.pending_action
        if intent.action in ("run", "ask", "scenario", "research") or starts_plan:

            async def run(on_start: Any) -> TaskReport:
                return (await self.assistant.execute(intent, on_start=on_start)).report

            task = await self._start(run)
            # what was understood comes first: action, project, agent (DIA-12)
            answer.update(reply=self.assistant.announce(intent), task=task_json(task))
        else:
            response = await self.assistant.execute(intent)
            answer["reply"] = response.text
            plan_id = self.dia.conversations.pending_plan(conversation)
            if intent.action in ("plan", "mission") and plan_id:
                answer["plan"] = task_json(self.dia.store.get(plan_id))
        return answer

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
        body = await read_body(request)
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


def routes(ch: ChatRoutes) -> list[web.RouteDef]:
    return [
        web.post("/api/chat", ch.chat),
        web.post("/api/talk", ch.talk),
        web.get("/api/chat/providers", ch.chat_providers),
        web.get("/api/sessions", ch.list_sessions),
        web.post("/api/sessions", ch.create_session),
        web.get("/api/sessions/{id}", ch.get_session),
        web.patch("/api/sessions/{id}", ch.rename_session),
        web.delete("/api/sessions/{id}", ch.delete_session),
        web.post("/api/voice/{action}", ch.voice),
    ]
