"""Text-to-speech engines."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dia.agents.base import find_executable
from dia.voice import TextToSpeech

DEFAULT_VOICES_DIR = "~/.local/share/dia/voices"


async def _run(argv: list[str], stdin: bytes | None = None) -> None:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate(stdin)
    if proc.returncode:
        raise RuntimeError(f"{argv[0]} failed: {err.decode(errors='replace').strip()[-500:]}")


class PiperTTS(TextToSpeech):
    """Local neural voices via Piper (``pip install 'dia[voice]'``).

    ``voice`` is a voice name, downloaded on first use into ``voices_dir``
    (e.g. ``pl_PL-gosia-medium``, ``pl_PL-darkman-medium``, ``en_US-lessac-medium``),
    or a path to an ``.onnx`` file.
    """

    kind = "piper"

    @property
    def voices_dir(self) -> Path:
        return Path(os.path.expanduser(self.options.get("voices_dir", DEFAULT_VOICES_DIR)))

    @property
    def voice(self) -> str:
        return self.options.get("voice", "pl_PL-gosia-medium")

    @property
    def model_path(self) -> Path:
        voice = os.path.expanduser(self.voice)
        if voice.endswith(".onnx"):
            return Path(voice)
        return self.voices_dir / f"{voice}.onnx"

    def check(self) -> str | None:
        try:
            import piper  # noqa: F401
        except ImportError:
            return "piper-tts is not installed: pip install 'dia[voice]'"
        if not self.model_path.exists() and self.voice.endswith(".onnx"):
            return f"voice file not found: {self.model_path}"
        return None

    async def ensure_voice(self) -> Path:
        if not self.model_path.exists():
            if self.voice.endswith(".onnx"):
                raise RuntimeError(f"voice file not found: {self.model_path}")
            self.voices_dir.mkdir(parents=True, exist_ok=True)
            await _run(
                [
                    sys.executable,
                    "-m",
                    "piper.download_voices",
                    self.voice,
                    "--download-dir",
                    str(self.voices_dir),
                ]
            )
        return self.model_path

    def argv(self, model: Path, output: Path) -> list[str]:
        argv = [sys.executable, "-m", "piper", "-m", str(model), "-f", str(output)]
        if speaker := self.options.get("speaker"):
            argv += ["-s", str(speaker)]
        if rate := self.options.get("length_scale"):  # >1 slower, <1 faster
            argv += ["--length-scale", str(rate)]
        return argv

    async def synthesize(self, text: str, output: Path) -> None:
        model = await self.ensure_voice()
        await _run(self.argv(model, output), stdin=text.encode())


class CommandTTS(TextToSpeech):
    """Any CLI. With ``{output}`` in argv it must write a WAV there; without
    it, the command is expected to speak by itself (e.g. ``spd-say``)::

    tts = { type = "command", argv = ["espeak-ng", "-v", "pl", "-w", "{output}", "{text}"] }
    """

    kind = "command"

    @property
    def writes_file(self) -> bool:  # type: ignore[override]
        return any("{output}" in part for part in self.options.get("argv", []))

    def check(self) -> str | None:
        argv = self.options.get("argv")
        if not argv:
            return "tts type 'command' requires 'argv'"
        if not find_executable(argv[0]):
            return f"command '{argv[0]}' not found"
        return None

    async def synthesize(self, text: str, output: Path) -> None:
        argv = [
            part.replace("{text}", text).replace("{output}", str(output))
            for part in self.options["argv"]
        ]
        await _run(argv)


class ElevenLabsTTS(TextToSpeech):
    """ElevenLabs voices, including a voice you created or cloned in your account
    (with the consent of the person whose voice it is)::

        tts = { type = "elevenlabs", voice_id = "...", fallback = { type = "piper" } }

    The API key is the ``ELEVENLABS_API_KEY`` secret (``dia secret set``), or
    the variable named by ``api_key_env``. With ``fallback``, that engine speaks
    when ElevenLabs can't (offline, out of credits).
    """

    kind = "elevenlabs"
    url = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
    sample_rate = 22050

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.options.get("api_key_env", "ELEVENLABS_API_KEY"))

    def check(self) -> str | None:
        if not self.options.get("voice_id"):
            return "tts 'elevenlabs' needs 'voice_id' (from your ElevenLabs voice library)"
        if not self.api_key:
            return "no ElevenLabs API key: dia secret set ELEVENLABS_API_KEY"
        return None

    def body(self, text: str) -> dict:
        settings = {
            key: float(self.options[key])
            for key in ("stability", "similarity_boost", "style", "speed")
            if key in self.options
        }
        body: dict = {"text": text, "model_id": self.options.get("model", "eleven_multilingual_v2")}
        if settings:
            body["voice_settings"] = settings
        if language := self.options.get("language"):
            body["language_code"] = language
        return body

    def _request(self, text: str) -> bytes:
        import json
        import urllib.request

        url = self.url.format(voice=self.options["voice_id"])
        req = urllib.request.Request(
            f"{url}?output_format=pcm_{self.sample_rate}",
            data=json.dumps(self.body(text)).encode(),
            headers={"xi-api-key": self.api_key or "", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=float(self.options.get("timeout", 30))) as resp:
            return resp.read()

    async def synthesize(self, text: str, output: Path) -> None:
        import wave

        try:
            if problem := self.check():
                raise RuntimeError(problem)
            pcm = await asyncio.to_thread(self._request, text)
        except Exception:
            if fallback := self.options.get("fallback"):
                from dia import plugins

                options = {"type": fallback} if isinstance(fallback, str) else dict(fallback)
                engine = plugins.load("dia.tts", options.pop("type", "piper"))(options)
                await engine.synthesize(text, output)
                return
            raise
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm)
