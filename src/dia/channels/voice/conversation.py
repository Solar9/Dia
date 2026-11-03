"""Voice channel, conversation side: what Dia does with a transcript, and what it announces."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from dia.agents import Mode
from dia.audit import ACTOR
from dia.channels.voice.helpers import VoiceBase

if TYPE_CHECKING:
    pass

log = logging.getLogger("dia.voice")


class ConversationMixin(VoiceBase):
    async def on_dia_event(self, event: Any) -> None:
        from dia.knowledge.attention import URGENT, Attention

        attention = Attention(self.dia)
        if event.kind not in attention.options.get("urgent", URGENT) and (attention.quiet_hours()):
            return  # quiet hours: Dia says nothing on its own
        if event.kind == "review":
            if "new comment" in event.message:
                await self.say(self.phrases["review"].format(project=event.task.project))
            return
        if event.kind == "system":
            await self.say(event.message)
            return
        if event.kind == "schedule":
            if event.data.get("job", {}).get("speak"):
                await self.say(event.message)
            return
        if event.kind == "watch" and event.task:
            key = "build_fixed" if event.message == "fixed" else "build_failed"
            await self.say(self.phrases[key].format(project=event.task.project))
            return
        if event.kind != "ci":
            return
        key = {"success": "ci_success", "failed": "ci_failed"}.get(event.message, "ci_other")
        await self.say(self.phrases[key].format(project=event.task.project, message=event.message))

    async def handle_text(self, text: str, speaker: str | None = None) -> None:
        """A request in words (transcribed, or said right after the wake word).

        With speaker recognition on, ``speaker`` is who said it (None: a voice
        Dia doesn't know), and an unknown voice may only ask for little."""
        ACTOR.set(f"voice:{speaker}" if speaker else "voice")
        log.info("heard: %s", text)
        self._notify(f"🗣 {text}")
        conversation = speaker or ("guest" if self.speakers else "default")
        intent = await self.assistant.interpret(text, conversation)
        if self.speakers and not self.speakers.allows(speaker, intent.action, intent.skill):
            log.info("unknown voice asked for %s; refused", intent.action)
            if self.speakers.unknown != "ignore":
                await self.say(self.phrases["unknown_voice"])
            return
        starts_plan = intent.action == "confirm" and not self.assistant.pending_action
        if intent.action in ("run", "ask", "scenario", "research") or starts_plan:
            if intent.action != "confirm":
                await self.say(
                    self.assistant.announce(intent, spoken=True)
                    or self.phrases["starting"].format(project=intent.project)
                )
            # The task runs in the background; recording stays available meanwhile.
            self._spawn(self._run_task(intent))
            return
        if intent.action in ("plan", "mission"):  # planning takes a while; then Dia asks
            if intent.reply:  # the approval question that follows says what was understood
                await self.say(intent.reply)
            self._spawn(self._prepare_plan(intent))
            return
        response = await self.assistant.execute(intent)
        await self.say(response.text)

    async def _prepare_plan(self, intent: Any) -> None:
        try:
            response = await self.assistant.execute(intent)
        except Exception as exc:
            await self.say(self.phrases["error"].format(error=exc))
            return
        await self.say(response.text)

    async def _run_task(self, intent: Any) -> None:
        response = await self.assistant.execute(intent)
        task = response.report.task if response.report else None
        if not task:
            await self.say(response.text)
            return
        key = "finished" if task.status == "done" else "failed"
        parts = [self.phrases[key].format(project=task.project), response.text]
        if task.commit_sha and task.mode == Mode.EDIT:
            parts.append(self.phrases["changes"])
        self._notify(f"{task.project}: {task.status}\n{(task.summary or task.error or '')[:300]}")
        await self.say(" ".join(p for p in parts if p))

    @property
    def state(self) -> str:
        return self._last_state

    def _state(self, state: str, text: str = "") -> None:
        """Tell listeners (the UI) what the voice is doing: listening/processing/speaking/idle."""
        self._last_state = state
        self._spawn(self.dia.emit("voice", None, f"{state}:{text}" if text else state))

    def _notify(self, text: str) -> None:
        if self.notifications:
            self._spawn(self._notify_async(text))

    async def _notify_async(self, text: str) -> None:
        with contextlib.suppress(OSError):
            proc = await asyncio.create_subprocess_exec(
                "notify-send",
                "--app-name=Dia",
                "Dia",
                text,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
