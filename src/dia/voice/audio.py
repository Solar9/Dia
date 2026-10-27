"""Recording and playback through whatever audio CLI the system has.

Using the system's own tools (PipeWire, PulseAudio, ALSA or ffmpeg) keeps Dia
free of native audio dependencies and works on practically any Linux desktop.
Override with ``record_command`` / ``play_command`` ({output} / {input}).
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import signal
import wave
from array import array
from pathlib import Path

from dia.agents.base import find_executable

# 16 kHz mono 16-bit WAV: what speech recognisers want.
RECORDERS = [
    ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "{output}"],
    ["parecord", "--rate=16000", "--channels=1", "--format=s16le", "--file-format=wav", "{output}"],
    ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "wav", "{output}"],
    [
        "ffmpeg",
        "-loglevel",
        "error",
        "-f",
        "pulse",
        "-i",
        "default",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-y",
        "{output}",
    ],
]
PLAYERS = [
    ["pw-play", "{input}"],
    ["paplay", "{input}"],
    ["aplay", "-q", "{input}"],
    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", "{input}"],
]


def pick(candidates: list[list[str]], configured: list[str] | None) -> list[str] | None:
    if configured:
        return list(configured)
    return next((list(c) for c in candidates if find_executable(c[0])), None)


def _fill(template: list[str], placeholder: str, path: Path) -> list[str]:
    argv = [part.replace(placeholder, str(path)) for part in template]
    return [find_executable(argv[0]) or argv[0], *argv[1:]]


class Recorder:
    def __init__(self, command: list[str] | None = None) -> None:
        self.template = pick(RECORDERS, command)
        self._proc: asyncio.subprocess.Process | None = None
        self.path: Path | None = None

    def check(self) -> str | None:
        if not self.template:
            return "no recorder found: install pipewire (pw-record), pulseaudio-utils or alsa-utils"
        return None

    @property
    def recording(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, path: Path) -> None:
        if problem := self.check():
            raise RuntimeError(problem)
        self.path = path
        self._proc = await asyncio.create_subprocess_exec(
            *_fill(self.template, "{output}", path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

    async def stop(self) -> Path:
        """Stop recording (SIGINT lets the tool finish the WAV header) and return the file."""
        proc, self._proc = self._proc, None
        if proc is None or self.path is None:
            raise RuntimeError("not recording")
        if proc.returncode is None:
            proc.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(proc.wait(), 3)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        if not self.path.exists() or self.path.stat().st_size == 0:
            err = (await proc.stderr.read()).decode(errors="replace").strip() if proc.stderr else ""
            raise RuntimeError(f"recording failed: {err or 'no audio written'}")
        return self.path


class Player:
    def __init__(self, command: list[str] | None = None) -> None:
        self.template = pick(PLAYERS, command)
        self._proc: asyncio.subprocess.Process | None = None

    def check(self) -> str | None:
        if not self.template:
            return (
                "no audio player found: install pipewire (pw-play), pulseaudio-utils or alsa-utils"
            )
        return None

    async def play(self, path: Path) -> None:
        """Play a file to the end, unless :meth:`stop` interrupts it."""
        if problem := self.check():
            raise RuntimeError(problem)
        self._proc = await asyncio.create_subprocess_exec(
            *_fill(self.template, "{input}", path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await self._proc.wait()

    def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.kill()


# Continuous capture for wake word listening: raw 16 kHz mono s16le on stdout.
STREAMERS = [
    ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "-"],
    ["parec", "--rate=16000", "--channels=1", "--format=s16le"],
    ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw"],
    [
        "ffmpeg",
        "-loglevel",
        "error",
        "-f",
        "pulse",
        "-i",
        "default",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "-",
    ],
]
SAMPLE_RATE = 16000


class MicStream:
    """The microphone as an endless stream of raw audio chunks."""

    def __init__(self, command: list[str] | None = None) -> None:
        self.template = pick(STREAMERS, command)
        self._proc: asyncio.subprocess.Process | None = None

    def check(self) -> str | None:
        if not self.template:
            return "no audio capture tool found: install pipewire, pulseaudio-utils or alsa-utils"
        return None

    async def start(self) -> None:
        if problem := self.check():
            raise RuntimeError(problem)
        argv = [find_executable(self.template[0]) or self.template[0], *self.template[1:]]
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def read(self, samples: int) -> bytes | None:
        """The next ``samples`` samples, or None when the stream ended."""
        assert self._proc and self._proc.stdout
        try:
            return await self._proc.stdout.readexactly(samples * 2)
        except asyncio.IncompleteReadError:
            return None

    async def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.kill()
            await self._proc.wait()


def rms(chunk: bytes) -> float:
    samples = array("h", chunk)
    return math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0


def is_silent(path: Path, threshold: float = 30.0) -> bool:
    """True for a WAV that holds (almost) nothing but zeros: a muted or wrong microphone."""
    try:
        with wave.open(str(path)) as wav:
            return rms(wav.readframes(wav.getnframes())) < threshold
    except (wave.Error, EOFError):
        return False


def write_wav(path: Path, chunks: list[bytes]) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(b"".join(chunks))
    return path
