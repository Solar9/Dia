import os
import wave
from pathlib import Path

import pytest

from dia import secrets
from dia.voice.tts import ElevenLabsTTS


@pytest.fixture
def xdg(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("DIA_TEST_KEY", raising=False)
    return tmp_path / "dia" / "env"


def test_secrets_are_stored_privately_and_never_listed(xdg: Path) -> None:
    xdg.parent.mkdir(parents=True)
    xdg.write_text("# comment\nDIA_DISCORD_TOKEN='abc'\n")
    secrets.set_secret("ELEVENLABS_API_KEY", "  sk-123 ")
    secrets.set_secret("ELEVENLABS_API_KEY", "sk-456")
    assert xdg.read_text().count("ELEVENLABS_API_KEY") == 1
    assert xdg.stat().st_mode & 0o777 == 0o600
    status = {s["name"]: s for s in secrets.status()}
    assert status["ELEVENLABS_API_KEY"]["set"] and "sk-456" not in str(status)
    assert os.environ["ELEVENLABS_API_KEY"] == "sk-456"
    assert secrets.remove_secret("ELEVENLABS_API_KEY")
    assert "ELEVENLABS_API_KEY" not in secrets.names()
    with pytest.raises(ValueError):
        secrets.set_secret("bad name", "x")
    os.environ.pop("DIA_DISCORD_TOKEN", None)
    secrets.load_into_environment()
    assert os.environ.pop("DIA_DISCORD_TOKEN") == "abc"


async def test_elevenlabs_writes_wav_and_falls_back(xdg: Path, tmp_path: Path, monkeypatch) -> None:
    tts = ElevenLabsTTS({"voice_id": "v1", "stability": 0.4})
    assert "ELEVENLABS_API_KEY" in tts.check()
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk")
    assert tts.check() is None
    assert tts.body("cześć") == {
        "text": "cześć",
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.4},
    }
    monkeypatch.setattr(tts, "_request", lambda text: b"\x00\x01" * 2205)
    out = tmp_path / "a.wav"
    await tts.synthesize("cześć", out)
    with wave.open(str(out)) as wav:
        assert (wav.getframerate(), wav.getnframes()) == (22050, 2205)

    def offline(text):
        raise OSError("no network")

    spoken = tmp_path / "fallback.txt"
    fallback = ElevenLabsTTS(
        {
            "voice_id": "v1",
            "fallback": {"type": "command", "argv": ["sh", "-c", f"echo {{text}} > {spoken}"]},
        }
    )
    monkeypatch.setattr(fallback, "_request", offline)
    await fallback.synthesize("hej", tmp_path / "b.wav")
    assert spoken.read_text().strip() == "hej"
