from array import array
from pathlib import Path

from test_voice import lines, voice_setup

from dia.config import parse_config
from dia.voice.audio import write_wav
from dia.voice.speaker import SpeakerEmbedder, Speakers


class FakeEmbedder(SpeakerEmbedder):
    """A "voice" is the loudness of the recording: alice loud, bob quiet."""

    kind = "fake"

    def embed(self, samples, sample_rate=16000):
        level = sum(abs(s) for s in samples) / len(samples)
        return [level, 1 - level]


def tone(level: float, seconds: float = 1.0) -> list[float]:
    return [level if i % 2 else -level for i in range(int(16000 * seconds))]


def make(tmp_path: Path, **options) -> Speakers:
    config = parse_config({"dia": {"data_dir": str(tmp_path)}})
    return Speakers(config, {"threshold": 0.95, **options}, embedder=FakeEmbedder())


def test_enroll_and_recognise(tmp_path: Path) -> None:
    speakers = make(tmp_path)
    assert speakers.identify(tone(0.9)) == (None, 0.0)  # nobody enrolled
    assert speakers.enroll("alice", [tone(0.9), tone(0.88)]) == 2
    speakers.enroll("bob", [tone(0.1)])
    assert speakers.names() == ["alice", "bob"]
    assert speakers.identify(tone(0.89))[0] == "alice"
    assert speakers.identify(tone(0.12))[0] == "bob"
    assert speakers.identify(tone(0.5))[0] is None  # nobody Dia knows
    assert speakers.identify(tone(0.9, 0.1))[0] is None  # too short to tell
    assert (tmp_path / "speakers.json").stat().st_mode & 0o777 == 0o600
    assert speakers.forget("bob") and not speakers.forget("bob")


def test_what_an_unknown_voice_may_do(tmp_path: Path) -> None:
    limited = make(tmp_path)
    assert limited.allows("alice", "run")
    assert limited.allows(None, "chat") and limited.allows(None, "skill", "weather")
    for action in ("run", "process", "confirm", "camera_access", "screen_access", "build"):
        assert not limited.allows(None, action)
    assert not limited.allows(None, "skill", "mail")
    assert not make(tmp_path, unknown="ignore").allows(None, "chat")
    assert make(tmp_path, unknown="allow").allows(None, "run")


def wav(path: Path, level: float) -> Path:
    samples = array("h", [int(s * 32767) for s in tone(level)])
    return write_wav(path, [samples.tobytes()])


async def test_the_voice_channel_refuses_a_stranger(tmp_path: Path, repo: Path) -> None:
    voice, transcript, spoken = voice_setup(tmp_path, repo)
    voice.speakers = make(tmp_path / "speakers")
    voice.speakers.enroll("alice", [tone(0.9)])

    transcript.write_text("Dia, zadania")
    await voice.process(wav(tmp_path / "stranger.wav", 0.5))
    assert lines(spoken) == ["Nie rozpoznaję Twojego głosu, więc tego nie zrobię."]

    await voice.process(wav(tmp_path / "alice.wav", 0.9))
    assert lines(spoken)[-1] == "Nie ma jeszcze żadnych zadań."
