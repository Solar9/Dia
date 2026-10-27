"""Speech: speech-to-text and text-to-speech plugins, plus audio I/O helpers.

Both are plugin groups (``dia.stt``, ``dia.tts``), so any engine can be used:
the built-ins wrap faster-whisper and Piper (local, offline) and a generic
``command`` variant drives any CLI (whisper.cpp, espeak-ng, ...).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar


class SpeechToText(ABC):
    kind: ClassVar[str]

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options: dict[str, Any] = dict(options or {})

    @abstractmethod
    async def transcribe(self, audio: Path, language: str | None = None) -> str: ...

    def check(self) -> str | None:
        return None


class TextToSpeech(ABC):
    kind: ClassVar[str]
    # False when the engine plays the audio itself instead of writing a file.
    writes_file: ClassVar[bool] = True

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options: dict[str, Any] = dict(options or {})

    @abstractmethod
    async def synthesize(self, text: str, output: Path) -> None:
        """Write speech for ``text`` to the WAV file ``output``."""

    def check(self) -> str | None:
        return None
