"""Local voice: press a shortcut, speak, hear the answer.

The voice channel runs inside ``dia serve`` and listens on a Unix socket.
``dia voice toggle`` (bound to a global shortcut in your desktop's settings,
which works the same on KDE, GNOME, Xfce, Hyprland, Sway, X11 or Wayland)
starts recording; pressing it again stops, transcribes, lets the brain decide
and speaks the reply. Tasks keep running in the background and Dia speaks
again when they finish.

Optionally, a wake word ("Hey Jarvis", or a custom "Hey Dia") starts listening
hands-free; recording then stops by itself after you stop speaking. The
shortcut keeps working and shares the same microphone stream.

Commands on the socket (one per line): toggle, start, stop, cancel, ping.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import statistics
import tempfile
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia import plugins
from dia.agents import Mode
from dia.agents.base import find_executable
from dia.assistant import Assistant
from dia.audit import ACTOR
from dia.channels import Channel
from dia.voice import SpeechToText, TextToSpeech
from dia.voice.audio import MicStream, Player, Recorder, is_silent, rms, write_wav
from dia.voice.wake import WakeWord

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator
    from dia.voice.speaker import Speakers

log = logging.getLogger("dia.voice")

PHRASES = {
    "pl": {
        "listening": "Słucham…",
        "not_heard": "Nie usłyszałam, spróbuj jeszcze raz.",
        "silence": "Mikrofon nagrał samą ciszę. Sprawdź, czy wybrane jest właściwe wejście.",
        "unknown_voice": "Nie rozpoznaję Twojego głosu, więc tego nie zrobię.",
        "starting": "Zlecam zadanie w projekcie {project}.",
        "finished": "Zadanie w {project} zakończone.",
        "failed": "Zadanie w {project} się nie powiodło.",
        "changes": "Zmiany czekają na zatwierdzenie.",
        "error": "Coś poszło nie tak: {error}",
        "ci_success": "Testy CI w projekcie {project} przeszły.",
        "ci_failed": "Testy CI w projekcie {project} nie przeszły.",
        "ci_other": "CI w projekcie {project}: {message}",
        "review": "Nowe uwagi do zmian w projekcie {project}.",
        "build_failed": "Uwaga, ostatni commit w projekcie {project} psuje testy.",
        "build_fixed": "Testy w projekcie {project} znowu przechodzą.",
    },
    "en": {
        "listening": "Listening…",
        "not_heard": "I didn't catch that, please try again.",
        "silence": "The microphone recorded only silence. Check the selected input device.",
        "unknown_voice": "I don't recognise your voice, so I can't do that.",
        "starting": "Starting a task in {project}.",
        "finished": "The task in {project} is done.",
        "failed": "The task in {project} failed.",
        "changes": "Changes are waiting for your approval.",
        "error": "Something went wrong: {error}",
        "ci_success": "CI passed in {project}.",
        "ci_failed": "CI failed in {project}.",
        "ci_other": "CI in {project}: {message}",
        "review": "New review comments on {project}.",
        "build_failed": "Heads up: the latest commit in {project} breaks the tests.",
        "build_fixed": "The tests in {project} pass again.",
    },
}


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return Path(runtime) / "dia" / "voice.sock"


def speakable(text: str, limit: int = 400) -> str:
    """Markdown and code removed, cut at a sentence boundary: fit for reading aloud."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", text)  # [[note|alias]] -> alias
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [label](url) -> label
    text = re.sub(r"[`*_#>|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0] + "…"


def sentences(text: str, min_chars: int = 40) -> list[str]:
    """Split for speaking one sentence at a time; very short ones join the next."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1]) < min_chars:
            merged[-1] += " " + part
        else:
            merged.append(part)
    return merged


async def send_command(command: str, path: Path | None = None) -> str:
    """Client side of the socket, used by ``dia voice ...``."""
    path = path or socket_path()
    try:
        reader, writer = await asyncio.open_unix_connection(str(path))
    except (FileNotFoundError, ConnectionRefusedError):
        raise RuntimeError(
            "Dia's voice channel is not running: start `dia serve` with [channels.voice] configured"
        ) from None
    writer.write(command.encode() + b"\n")
    await writer.drain()
    reply = (await reader.readline()).decode().strip()
    writer.close()
    await writer.wait_closed()
    return reply


def _load(group: str, options: dict[str, Any] | str | None, default: str) -> Any:
    options = {"type": options} if isinstance(options, str) else dict(options or {})
    kind = options.pop("type", default)
    return plugins.load(group, kind)(options)


class VoiceChannel(Channel):
    kind = "voice"

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

    # ------------------------------------------------------------- server ---

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

    @property
    def recording(self) -> bool:
        return self._capture is not None or self.recorder.recording

    def _next_wav(self) -> Path:
        self._recordings += 1
        return self._tmp / f"request-{self._recordings}.wav"

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

    async def on_dia_event(self, event: Any) -> None:
        from dia.attention import URGENT, Attention

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

    # ---------------------------------------------------------- wake word ---

    async def listen(self) -> None:
        ACTOR.set("voice")
        """Read the microphone continuously: wake word, then record until silence."""
        assert self.wake and self.mic
        await asyncio.to_thread(self.wake.prepare)
        await self.mic.start()
        log.info("voice: waiting for the wake word")
        samples = self.wake.chunk_samples
        chunk_s = samples / 16000
        noise: deque[float] = deque(maxlen=50)  # ~4 s of background level
        try:
            while (chunk := await self.mic.read(samples)) is not None:
                if self._capture is not None:
                    self._capture.append(chunk)
                elif self._utterance is not None:
                    self._follow_utterance(chunk, chunk_s, noise)
                elif not self._speaking:
                    noise.append(rms(chunk))
                    if self.wake.detect(chunk):
                        said = self.wake.take_text() if hasattr(self.wake, "take_text") else ""
                        voice = self.wake.take_audio() if hasattr(self.wake, "take_audio") else b""
                        self.wake.reset()
                        self.interrupt()
                        if len(said.split()) >= 2:  # "Hej Dia, jaka pogoda?" in one breath
                            self._state("processing")
                            self._spawn(self._handle_breath(said, voice))
                            continue
                        self._utterance = {"chunks": [], "speech": False, "silent": 0}
                        self._notify(self.phrases["listening"])
                        self._state("listening")
            log.warning("voice: the microphone stream ended")
        finally:
            await self.mic.stop()

    def _follow_utterance(self, chunk: bytes, chunk_s: float, noise: deque[float]) -> None:
        """Collect the request after the wake word; end it after a pause in speech."""
        u = self._utterance
        u["chunks"].append(chunk)
        floor = statistics.median(noise) if noise else 0.0
        if rms(chunk) > max(self.min_level, floor * 2.5):
            u["speech"], u["silent"] = True, 0
        elif u["speech"]:
            u["silent"] += 1
        # Durations in whole chunks: summing float seconds would drift.
        length = len(u["chunks"])
        if u["speech"] and (
            u["silent"] >= round(self.silence_s / chunk_s) or length >= self.max_s / chunk_s
        ):
            self._utterance = None
            self._spawn(self.process(write_wav(self._next_wav(), u["chunks"])))
            self._state("processing")
        elif not u["speech"] and length >= round(self.wait_s / chunk_s):
            self._utterance = None
            self._spawn(self.say(self.phrases["not_heard"]))

    # ------------------------------------------------------------ dialogue ---

    async def process(self, audio: Path) -> None:
        ACTOR.set("voice")
        if is_silent(audio):
            audio.unlink(missing_ok=True)
            log.warning("recording is silent: wrong or muted input device?")
            await self.say(self.phrases["silence"])
            return
        speaker: str | None = None
        try:
            if self.speakers:
                from dia.voice.speaker import read_samples

                speaker = await self._identify(read_samples(audio))
            text = (await self.stt.transcribe(audio, self.language)).strip()
        except Exception as exc:
            log.exception("transcription failed")
            await self.say(self.phrases["error"].format(error=exc))
            return
        finally:
            audio.unlink(missing_ok=True)
        if not text:
            await self.say(self.phrases["not_heard"])
            return
        await self.handle_text(text, speaker)

    async def _identify(self, samples: list[float]) -> str | None:
        assert self.speakers
        who, score = await asyncio.to_thread(self.speakers.identify, samples)
        log.info("speaker: %s (%.2f)", who or "unknown", score)
        return who

    async def _handle_breath(self, text: str, pcm: bytes) -> None:
        """A request said with the wake word; its voice is the keyword's stretch of speech."""
        speaker = None
        if self.speakers:
            from dia.voice.speaker import pcm_samples

            speaker = await self._identify(pcm_samples(pcm))
        await self.handle_text(text, speaker)

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
                    intent.reply or self.phrases["starting"].format(project=intent.project)
                )
            # The task runs in the background; recording stays available meanwhile.
            self._spawn(self._run_task(intent))
            return
        if intent.action in ("plan", "mission"):  # planning takes a while; then Dia asks
            if intent.reply:
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

    async def say(self, text: str) -> None:
        text = speakable(text, self.speak_max_chars)
        if not text:
            return
        if self.dia.quiet:  # quiet mode: show it, don't say it
            log.info("quiet mode, not saying: %s", text)
            self._notify(text)
            self._state("idle", text)
            return
        log.info("saying: %s", text)
        async with self._speech_lock:  # one reply at a time, never overlapping
            self._speaking = True  # so the wake word detector does not hear Dia herself
            self._interrupted = False
            self._state("speaking", text)
            try:
                await self._speak(sentences(text))
            except Exception:
                log.exception("speaking failed")
                self._notify(text)
            finally:
                self._speaking = False
                self._state("idle")
                if self.wake:
                    self.wake.reset()

    async def _speak(self, parts: list[str]) -> None:
        """Speak sentence by sentence: the next one is synthesized while the current
        one plays, so long answers start at once; an interruption ends them all."""
        if not self.tts.writes_file:
            for part in parts:
                if self._interrupted:
                    return
                await self.tts.synthesize(part, self._tmp / "reply.wav")
            return

        async def make(i: int) -> Path:
            path = self._tmp / f"reply-{i % 2}.wav"
            await self.tts.synthesize(parts[i], path)
            return path

        upcoming = asyncio.ensure_future(make(0))
        try:
            for i in range(len(parts)):
                wav = await upcoming
                if i + 1 < len(parts):
                    upcoming = asyncio.ensure_future(make(i + 1))
                if self._interrupted:
                    return
                await self.player.play(wav)
                if self._interrupted:
                    return
        finally:
            if not upcoming.done():
                upcoming.cancel()

    def interrupt(self) -> None:
        """Stop talking now (the shortcut, or the wake word, pressed while Dia talks)."""
        self._interrupted = True
        self.player.stop()

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

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
