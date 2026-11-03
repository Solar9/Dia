"""Local voice: press a shortcut, speak, hear the answer.

The voice channel runs inside ``dia serve`` and listens on a Unix socket.
``dia voice toggle`` (bound to a global shortcut in your desktop's settings,
which works the same on KDE, GNOME, Xfce, Hyprland, Sway, X11 or Wayland)
starts recording; pressing it again stops, transcribes, lets the brain decide
and speaks the reply. Tasks keep running in the background and Dia speaks
again when they finish.

Optionally, a wake word ("Hej Dia", or a trained openWakeWord model) starts listening
hands-free; recording then stops by itself after you stop speaking. The
shortcut keeps working and shares the same microphone stream.

Commands on the socket (one per line): toggle, start, stop, cancel, ping.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.agents.base import find_executable
from dia.assistant import Assistant
from dia.audit import ACTOR
from dia.channels import Channel
from dia.channels.voice.audio import AudioMixin
from dia.channels.voice.conversation import ConversationMixin
from dia.channels.voice.helpers import (  # noqa: F401  (re-exported: other modules import them from here)
    PHRASES,
    _load,
    send_command,
    sentences,
    socket_path,
    speakable,
)
from dia.voice import SpeechToText, TextToSpeech
from dia.voice.audio import MicStream, Player, Recorder, write_wav
from dia.voice.wake import WakeWord

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator
    from dia.voice.speaker import Speakers

log = logging.getLogger("dia.voice")


class VoiceChannel(AudioMixin, ConversationMixin, Channel):
    def __init__(self, name: str, options: dict[str, Any], dia: Orchestrator) -> None:
        super().__init__(name, options, dia)
        self.language: str = options.get("language", dia.config.language)
        self.phrases = PHRASES.get(self.language, PHRASES["en"])
        self.stt: SpeechToText = _load("dia.stt", options.get("stt"), "faster-whisper")
        self.tts: TextToSpeech = _load("dia.tts", options.get("tts"), "piper")
        self.recorder = Recorder(options.get("record_command"))
        self.player = Player(options.get("play_command"))
        self.socket = Path(os.path.expanduser(options.get("socket", str(socket_path()))))
        self.speak_max_chars = int(options.get("speak_max_chars", 400))
        self.notifications = options.get("notifications", True) and find_executable("notify-send")
        self.assistant = Assistant(dia, language=self.language)
        self.assistant.surface = "voice"
        self._tmp = Path(tempfile.mkdtemp(prefix="dia-voice-"))
        self._background: set[asyncio.Task] = set()
        self._speech_lock = asyncio.Lock()
        self._recordings = 0
        self._last_state = "idle"
        # Wake word: one shared microphone stream, also used by the shortcut.
        wake = options.get("wake")
        self.wake: WakeWord | None = _load("dia.wake", wake, "openwakeword") if wake else None
        self.mic = MicStream(options.get("stream_command")) if self.wake else None
        self.silence_s = float(options.get("silence_seconds", 0.8))
        self.max_s = float(options.get("max_seconds", 15))
        self.wait_s = float(options.get("wait_seconds", 5))
        self.min_level = float(options.get("min_speech_level", 300))
        self._capture: list[bytes] | None = None  # shortcut recording from the stream
        self._utterance: dict[str, Any] | None = None  # recording after the wake word
        self._speaking = False
        self._interrupted = False
        speaker = options.get("speaker")
        self.speakers: Speakers | None = None
        if speaker:
            from dia.voice.speaker import Speakers

            self.speakers = Speakers(dia.config, speaker)

    def check(self) -> str | None:
        return (
            (self.mic.check() or self.wake.check() if self.mic and self.wake else None)
            or (self.recorder.check() if not self.mic else None)
            or (self.player.check() if self.tts.writes_file else None)
            or self.stt.check()
            or self.tts.check()
            or (self.speakers.check() if self.speakers else None)
        )

    async def run(self) -> None:
        if problem := self.check():
            raise RuntimeError(f"voice: {problem}")
        self.socket.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.socket.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(self._client, path=str(self.socket))
        os.chmod(self.socket, 0o600)  # only you can trigger recording
        log.info("voice: listening for `dia voice toggle` on %s", self.socket)
        if warm_up := getattr(self.stt, "warm_up", None):
            self._spawn(warm_up())
        if self.wake:
            self._spawn(self.listen())
        if self.options.get("announce", True):
            self.dia.listeners.append(self.on_dia_event)
        try:
            async with server:
                await server.serve_forever()
        finally:
            self.socket.unlink(missing_ok=True)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        ACTOR.set("voice")
        command = (await reader.readline()).decode().strip()
        try:
            reply = await self.command(command)
        except Exception as exc:
            log.exception("voice command %r failed", command)
            reply = f"error: {exc}"
        writer.write(reply.encode() + b"\n")
        await writer.drain()
        writer.close()

    async def command(self, command: str) -> str:
        if command == "ping":
            return "pong"
        if command == "toggle":
            command = "stop" if self.recording else "start"
        if command == "start":
            if self.recording:
                return "already recording"
            self.interrupt()  # pressing the key while Dia talks interrupts her
            self._utterance = None
            if self.mic:
                self._capture = []  # the wake word loop feeds it
            else:
                await self.recorder.start(self._next_wav())
            self._notify(self.phrases["listening"])
            self._state("listening")
            return "recording"
        if command == "stop":
            if not self.recording:
                return "not recording"
            if self._capture is not None:
                chunks, self._capture = self._capture, None
                audio = write_wav(self._next_wav(), chunks)
            else:
                audio = await self.recorder.stop()
            self._spawn(self.process(audio))
            self._state("processing")
            return "processing"
        if command == "cancel":
            self._capture = self._utterance = None
            if self.recorder.recording:
                await self.recorder.stop()
            self.interrupt()
            self._state("idle")
            return "cancelled"
        return f"unknown command: {command}"

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
