"""Voice channel helpers: phrases, text for speech, the control socket."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.core import plugins

log = logging.getLogger("dia.voice")

if TYPE_CHECKING:
    from dia.assistant import Assistant
    from dia.core.orchestrator import Orchestrator
    from dia.voice import SpeechToText, TextToSpeech
    from dia.voice.audio import MicStream, Player, Recorder
    from dia.voice.speaker import Speakers
    from dia.voice.wake import WakeWord


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


class VoiceBase:
    """What the audio and conversation parts expect from VoiceChannel: declared for type
    checkers only, VoiceChannel sets and defines all of it."""

    dia: Orchestrator
    language: str
    phrases: dict[str, str]
    stt: SpeechToText
    tts: TextToSpeech
    recorder: Recorder
    player: Player
    speak_max_chars: int
    notifications: Any
    assistant: Assistant
    wake: WakeWord | None
    mic: MicStream | None
    speakers: Speakers | None
    silence_s: float
    max_s: float
    wait_s: float
    min_level: float
    _tmp: Path
    _speech_lock: asyncio.Lock
    _recordings: int
    _capture: list[bytes] | None
    _utterance: dict[str, Any] | None
    _speaking: bool
    _interrupted: bool
    _last_state: str

    if TYPE_CHECKING:

        async def say(self, text: str) -> None: ...
        async def handle_text(self, text: str, speaker: str | None = None) -> None: ...
        def _state(self, state: str, text: str = "") -> None: ...
        def _spawn(self, coro: Any) -> None: ...
        def _notify(self, text: str) -> None: ...
