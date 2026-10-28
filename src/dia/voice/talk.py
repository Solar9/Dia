"""A phone's own voice conversation, all on this computer.

A paired phone may not use the computer's microphone (docs/MOBILE.md), so it
records itself and sends the recording here: Dia's own speech-to-text turns it
into text, the answer is spoken with Dia's own voice and goes back as audio.
The engines are the ones set for the voice channel (``[channels.voice]`` stt
and tts), local Whisper and Piper by default.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from dia.voice import SpeechToText, TextToSpeech

log = logging.getLogger("dia.talk")

# The phone sends 16 kHz mono 16-bit WAV; 30 s of it is just under 1 MB.
MAX_SECONDS = 30
MAX_BYTES = 44 + 16000 * 2 * MAX_SECONDS


def audio_type(data: bytes) -> str:
    """The media type of what a TTS engine wrote (WAV from Piper, MP3 from some services)."""
    if data[:4] == b"RIFF":
        return "audio/wav"
    if data[:3] == b"ID3" or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if data[:4] == b"OggS":
        return "audio/ogg"
    return "application/octet-stream"


class Talk:
    def __init__(self, options: dict[str, Any], language: str) -> None:
        self.options = options
        self.language: str = options.get("language", language)
        self._stt: SpeechToText | None = None
        self._tts: TextToSpeech | None = None
        self._lock = asyncio.Lock()  # one recording at a time through the model

    @classmethod
    def from_config(cls, config: Any) -> Talk:
        options = next((o for n, o in config.channels.items() if o.get("type", n) == "voice"), None)
        return cls(dict(options or {}), config.language)

    @property
    def stt(self) -> SpeechToText:
        if self._stt is None:
            from dia.channels.voice import _load

            self._stt = _load("dia.stt", self.options.get("stt"), "faster-whisper")
        return self._stt

    @property
    def tts(self) -> TextToSpeech:
        if self._tts is None:
            from dia.channels.voice import _load

            self._tts = _load("dia.tts", self.options.get("tts"), "piper")
        return self._tts

    def check(self) -> str | None:
        """Why the phone can't talk this way (then it falls back to the browser), or None."""
        try:
            return self.stt.check()
        except Exception as exc:  # an engine that can't even load
            return str(exc)

    async def hear(self, wav: bytes) -> str:
        with tempfile.TemporaryDirectory(prefix="dia-talk-") as tmp:
            path = Path(tmp) / "phone.wav"
            path.write_bytes(wav)
            async with self._lock:
                return (await self.stt.transcribe(path, self.language)).strip()

    async def speak(self, text: str) -> bytes | None:
        """The answer as audio, or None when the voice can't write a file (text only)."""
        tts = self.tts
        if not text or not tts.writes_file or tts.check():
            return None
        with tempfile.TemporaryDirectory(prefix="dia-talk-") as tmp:
            path = Path(tmp) / "reply.wav"
            try:
                await tts.synthesize(text, path)
                return path.read_bytes()
            except Exception as exc:
                log.warning("talk: the answer could not be spoken: %s", exc)
                return None
