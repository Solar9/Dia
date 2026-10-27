"""Wake word detection ("Hey Jarvis", or your own trained "Hey Dia").

Detectors are plugins (``dia.wake``) fed with 16 kHz mono 16-bit audio in
chunks of ``chunk_samples``. The built-in one uses openWakeWord, which runs
comfortably on a laptop CPU.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, ClassVar


class WakeWord(ABC):
    kind: ClassVar[str]
    chunk_samples: ClassVar[int] = 1280  # 80 ms

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options: dict[str, Any] = dict(options or {})

    @abstractmethod
    def detect(self, chunk: bytes) -> bool:
        """Feed one chunk; True when the wake word was just heard."""

    def reset(self) -> None:
        """Forget buffered audio (after a detection, or after Dia spoke)."""
        return None

    def prepare(self) -> None:
        """Load models (may download them); called once before listening."""
        return None

    def check(self) -> str | None:
        return None


class OpenWakeWord(WakeWord):
    """openWakeWord (``pip install 'dia[wake]'``).

    ``model``: a pre-trained name (hey_jarvis, alexa, hey_mycroft, hey_rhasspy)
    downloaded on first use, or a path to your own ``.onnx`` model, e.g. a
    "hey dia" trained with openWakeWord's training notebook.
    """

    kind = "openwakeword"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self._model: Any = None
        self.threshold = float(self.options.get("threshold", 0.5))

    @property
    def model_name(self) -> str:
        return os.path.expanduser(self.options.get("model", "hey_jarvis"))

    def check(self) -> str | None:
        try:
            import numpy  # noqa: F401
            import openwakeword  # noqa: F401
        except ImportError:
            return "openwakeword is not installed: see docs/VOICE.md (wake word)"
        if self.model_name.endswith((".onnx", ".tflite")) and not os.path.exists(self.model_name):
            return f"wake word model not found: {self.model_name}"
        return None

    def prepare(self) -> None:
        if self._model is not None:
            return
        from openwakeword.model import Model
        from openwakeword.utils import download_models

        name = self.model_name
        if not name.endswith((".onnx", ".tflite")):
            download_models([name])  # also fetches the shared feature models; no-op when present
        else:
            download_models([])
        self._model = Model(wakeword_models=[name], inference_framework="onnx")

    def detect(self, chunk: bytes) -> bool:
        import numpy as np

        self.prepare()
        scores = self._model.predict(np.frombuffer(chunk, dtype=np.int16))
        return max(scores.values(), default=0.0) >= self.threshold

    def reset(self) -> None:
        if self._model is not None:
            self._model.reset()


DEFAULT_KEYWORD = r"\b(?:hej|hey|hi|cześć|czesc)?[\s,.!]*(?:dia|dija|dzia|dya|diya|dii)\b"


class KeywordWake(WakeWord):
    """ "Hej Dia" without training a model: short stretches of speech are
    transcribed by a tiny Whisper model and matched against ``keyword`` (a
    regular expression). Uses ``pip install 'dia[voice]'`` (faster-whisper).

    Speaking the request in one breath works too: "Hej Dia, jaka pogoda?"
    leaves "jaka pogoda?" in :meth:`take_text` and Dia answers it right away.
    More CPU than openWakeWord while you talk; nothing while it's quiet.
    """

    kind = "whisper-keyword"
    chunk_samples = 1280  # 80 ms at 16 kHz

    def __init__(self, options: dict[str, Any] | None = None, transcribe: Any = None) -> None:
        super().__init__(options)
        import re
        from concurrent.futures import ThreadPoolExecutor

        self.pattern = re.compile(self.options.get("keyword", DEFAULT_KEYWORD), re.IGNORECASE)
        self.language = self.options.get("language", "pl")
        self._transcribe_fn = transcribe
        self._model: Any = None
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._pending: Any = None  # a transcription in progress
        self._text = ""
        self._audio = b""  # the speech the keyword was heard in (for speaker recognition)
        self._pending_audio = b""
        self._segment: list[bytes] = []
        self._silent = 0
        self._noise: list[float] = []
        self.max_chunks = int(float(self.options.get("max_seconds", 4.0)) / 0.08)
        self.end_chunks = int(float(self.options.get("pause_seconds", 0.5)) / 0.08)
        self.min_level = float(self.options.get("min_level", 400))

    def check(self) -> str | None:
        if self._transcribe_fn:
            return None
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return "faster-whisper is not installed: pip install 'dia[voice]'"
        return None

    def prepare(self) -> None:
        if self._transcribe_fn or self._model is not None:
            return
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self.options.get("model", "tiny"), device="cpu", compute_type="int8"
        )

    def _transcribe(self, audio: bytes) -> str:
        if self._transcribe_fn:
            return self._transcribe_fn(audio)
        import numpy as np

        self.prepare()
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(
            samples,
            language=self.language,
            beam_size=1,
            vad_filter=False,
            initial_prompt=self.options.get("initial_prompt", "Hej Dia"),
        )
        return " ".join(s.text.strip() for s in segments)

    @staticmethod
    def _level(chunk: bytes) -> float:
        from array import array

        samples = array("h", chunk[: len(chunk) - len(chunk) % 2])
        return (sum(s * s for s in samples) / max(len(samples), 1)) ** 0.5

    def _check_pending(self) -> bool:
        if self._pending is None or not self._pending.done():
            return False
        try:
            heard = self._pending.result()
        except Exception:
            heard = ""
        self._pending = None
        if match := self.pattern.search(heard or ""):
            self._text = heard[match.end() :].strip(" ,.!?:;-")
            self._audio = self._pending_audio
            return True
        return False

    def detect(self, chunk: bytes) -> bool:
        if self._check_pending():
            return True
        level = self._level(chunk)
        floor = sorted(self._noise)[len(self._noise) // 2] if self._noise else 0.0
        speaking = level > max(self.min_level, floor * 3)
        if not speaking and not self._segment:
            self._noise = (self._noise + [level])[-50:]
            return False
        self._segment.append(chunk)
        self._silent = 0 if speaking else self._silent + 1
        if self._silent >= self.end_chunks or len(self._segment) >= self.max_chunks:
            voiced = len(self._segment) - self._silent
            audio, self._segment, self._silent = b"".join(self._segment), [], 0
            if voiced >= 4 and self._pending is None:  # at least ~0.3 s of speech
                self._pending = self._pool.submit(self._transcribe, audio)
                self._pending_audio = audio
        return False

    def take_text(self) -> str:
        """What was said after the keyword in the same breath ('' if nothing)."""
        text, self._text = self._text, ""
        return text

    def take_audio(self) -> bytes:
        """The 16 kHz PCM of the stretch the keyword was in (b'' if none)."""
        audio, self._audio = self._audio, b""
        return audio

    def reset(self) -> None:
        self._segment, self._silent, self._text, self._audio = [], 0, "", b""
