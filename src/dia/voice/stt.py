"""Speech-to-text engines."""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path
from typing import Any

from dia.agents.base import find_executable
from dia.voice import SpeechToText


def read_wav(path: Path) -> Any:
    """16 kHz mono 16-bit WAV (what Dia records) as float samples; other files as a path.

    Passing samples skips faster-whisper's own decoding through PyAV, which
    breaks between some versions (faster-whisper 1.2.1 with PyAV 19).
    """
    import numpy as np

    try:
        with wave.open(str(path)) as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2):
                frames = wav.readframes(wav.getnframes())
                return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    except (wave.Error, EOFError, OSError):
        pass
    return str(path)


class FasterWhisperSTT(SpeechToText):
    """Local Whisper via faster-whisper (``pip install 'dia[voice]'``).

    The model is downloaded on first use and kept in memory. On a laptop CPU,
    ``small`` with ``int8`` is a good balance for short commands; ``medium``
    is more accurate but several times slower.
    """

    kind = "faster-whisper"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self._model: Any = None

    def check(self) -> str | None:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return "faster-whisper is not installed: pip install 'dia[voice]'"
        return None

    def _load(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.options.get("model", "small"),
                device=self.options.get("device", "cpu"),
                compute_type=self.options.get("compute_type", "int8"),
                download_root=self.options.get("download_root"),
            )
        return self._model

    def _transcribe(self, audio: Path, language: str | None) -> str:
        segments, _ = self._load().transcribe(
            read_wav(audio),
            language=language,
            beam_size=int(self.options.get("beam_size", 5)),
            vad_filter=bool(self.options.get("vad_filter", True)),
            # a hint of the words to expect: without it Whisper hears "Dia" as "Media"
            initial_prompt=self.options.get("initial_prompt", "Dia"),
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    async def warm_up(self) -> None:
        """Load the model ahead of the first request (it can take a few seconds)."""
        await asyncio.to_thread(self._load)

    async def transcribe(self, audio: Path, language: str | None = None) -> str:
        return await asyncio.to_thread(self._transcribe, audio, language)


class CommandSTT(SpeechToText):
    """Any CLI that prints the transcript, e.g. whisper.cpp::

    stt = { type = "command", argv = ["whisper-cli", "-m", "ggml-small.bin", "-l", "{language}",
                                      "-nt", "-np", "-f", "{audio}"] }
    """

    kind = "command"

    def check(self) -> str | None:
        argv = self.options.get("argv")
        if not argv:
            return "stt type 'command' requires 'argv'"
        if not find_executable(argv[0]):
            return f"command '{argv[0]}' not found"
        return None

    async def transcribe(self, audio: Path, language: str | None = None) -> str:
        values = {"{audio}": str(audio), "{language}": language or ""}
        argv = list(self.options["argv"])
        for i, part in enumerate(argv):
            for key, value in values.items():
                part = part.replace(key, value)
            argv[i] = part
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode:
            raise RuntimeError(f"stt command failed: {err.decode(errors='replace').strip()}")
        return out.decode(errors="replace").strip()
