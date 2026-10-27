"""Who is speaking: Dia recognises the voices you enrolled and limits what a
voice it doesn't know may ask for.

    [channels.voice]
    speaker = { type = "sherpa-onnx", model = "~/.local/share/dia/speaker.onnx" }
    # threshold = 0.5         # how alike a voice must be (cosine similarity, 0..1)
    # unknown = "limited"     # a voice Dia doesn't know: "limited", "ignore" or "allow"
    # guest_skills = ["weather", "news", "stocks"]

Enroll each person with ``dia voice enroll <name>`` (a few sentences, three
times). Voices are kept as numbers (embeddings) in ``<data_dir>/speakers.json``,
never as recordings. An unknown voice ("limited", the default) may chat and
ask for the guest skills; it cannot start tasks, end processes, control the
house, read your mail or calendar, or look at the screen or camera.

Recognition reduces mistakes in a shared room; it is not a lock: a good
recording of your voice can fool it. Approvals (merge, publish) stay buttons.
Speaker models: any sherpa-onnx speaker embedding model, e.g. 3D-Speaker
``eres2net`` or WeSpeaker ``resnet34`` from k2-fsa/sherpa-onnx releases
(``speaker-recongition-models``).
"""

from __future__ import annotations

import json
import math
import os
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from dia.config import Config

# What a voice Dia doesn't know may still do in "limited" mode.
GUEST_ACTIONS = {"chat", "status", "skill", "cancel"}
GUEST_SKILLS = ["weather", "news", "stocks"]


class SpeakerEmbedder(ABC):
    kind: ClassVar[str]

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options = dict(options or {})

    @abstractmethod
    def embed(self, samples: list[float], sample_rate: int = 16000) -> list[float]:
        """A fixed-length vector describing the voice in ``samples`` (mono, -1..1)."""

    def check(self) -> str | None:
        return None


class SherpaEmbedder(SpeakerEmbedder):
    """sherpa-onnx speaker embeddings (``pip install sherpa-onnx``), CPU only."""

    kind = "sherpa-onnx"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self.model = os.path.expanduser(str(self.options.get("model", "")))
        self._extractor: Any = None

    def check(self) -> str | None:
        try:
            import sherpa_onnx  # noqa: F401
        except ImportError:
            return "sherpa-onnx is not installed: pip install sherpa-onnx"
        if not self.model or not os.path.exists(self.model):
            return f"speaker model not found: {self.model or '(set speaker.model)'}"
        return None

    def embed(self, samples: list[float], sample_rate: int = 16000) -> list[float]:
        import sherpa_onnx

        if self._extractor is None:
            config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=self.model, num_threads=int(self.options.get("threads", 1))
            )
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(config)
        stream = self._extractor.create_stream()
        stream.accept_waveform(sample_rate=sample_rate, waveform=samples)
        stream.input_finished()
        return list(self._extractor.compute(stream))


def read_samples(path: Path) -> list[float]:
    """16 kHz mono 16-bit WAV (what Dia records) as floats."""
    from array import array

    with wave.open(str(path)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (16000, 1, 2):
            raise ValueError(f"{path.name}: expected 16 kHz mono 16-bit WAV")
        frames = array("h", wav.readframes(wav.getnframes()))
    return [s / 32768.0 for s in frames]


def pcm_samples(pcm: bytes) -> list[float]:
    from array import array

    frames = array("h", pcm[: len(pcm) - len(pcm) % 2])
    return [s / 32768.0 for s in frames]


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(_normalise(a), _normalise(b), strict=False))


class Speakers:
    """The enrolled voices, and recognising them."""

    def __init__(
        self,
        config: Config,
        options: dict[str, Any] | None = None,
        embedder: SpeakerEmbedder | None = None,
    ) -> None:
        from dia import plugins

        self.options = dict(options or {})
        self.path = config.data_dir / "speakers.json"
        self.threshold = float(self.options.get("threshold", 0.5))
        self.unknown = str(self.options.get("unknown", "limited"))
        if self.unknown not in ("limited", "ignore", "allow"):
            raise ValueError("speaker.unknown must be 'limited', 'ignore' or 'allow'")
        self.guest_skills = list(self.options.get("guest_skills", GUEST_SKILLS))
        if embedder is None:
            kind = self.options.get("type", "sherpa-onnx")
            embedder = plugins.load("dia.speakers", kind)(self.options)
        self.embedder = embedder

    def check(self) -> str | None:
        return self.embedder.check()

    def _load(self) -> dict[str, list[list[float]]]:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, voices: dict[str, list[list[float]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(voices))
        self.path.chmod(0o600)

    def names(self) -> list[str]:
        return sorted(self._load())

    def enroll(self, name: str, samples: list[list[float]]) -> int:
        """Add recordings of ``name``'s voice; returns how many Dia now knows."""
        name = name.strip()
        if not name:
            raise ValueError("a speaker needs a name")
        voices = self._load()
        voices.setdefault(name, []).extend(
            _normalise(self.embedder.embed(s)) for s in samples if len(s) >= 8000
        )
        self._save(voices)
        return len(voices[name])

    def forget(self, name: str) -> bool:
        voices = self._load()
        if voices.pop(name, None) is None:
            return False
        self._save(voices)
        return True

    def identify(self, samples: list[float]) -> tuple[str | None, float]:
        """The enrolled speaker most like ``samples`` and how alike (None if nobody is)."""
        voices = self._load()
        if not voices or len(samples) < 4000:  # under a quarter of a second
            return None, 0.0
        vector = self.embedder.embed(samples)
        best, score = None, 0.0
        for name, embeddings in voices.items():
            s = max(_cosine(vector, e) for e in embeddings)
            if s > score:
                best, score = name, s
        return (best, score) if score >= self.threshold else (None, score)

    def allows(self, speaker: str | None, action: str, skill: str | None = None) -> bool:
        """May this speaker (None: a voice Dia doesn't know) ask for ``action``?"""
        if speaker is not None or self.unknown == "allow":
            return True
        if self.unknown == "ignore":
            return False
        if action == "skill":
            return skill in self.guest_skills
        return action in GUEST_ACTIONS
