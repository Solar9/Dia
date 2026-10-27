import asyncio
import sys
import wave
from array import array
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from test_voice import lines, voice_setup, wait_for

from dia import plugins
from dia.voice.wake import OpenWakeWord, WakeWord

CHUNK = 1280
MARK = 1234  # a chunk of this constant value plays the wake word in these tests


class FakeWake(WakeWord):
    kind = "fake"

    def detect(self, chunk: bytes) -> bool:
        return set(array("h", chunk)) == {MARK}


def pcm(*parts: tuple[str, int]) -> bytes:
    out = array("h")
    for kind, chunks in parts:
        for _ in range(chunks):
            if kind == "wake":
                out.extend([MARK] * CHUNK)
            elif kind == "speech":
                out.extend([5000, -5000] * (CHUNK // 2))
            else:
                out.extend([0] * CHUNK)
    return out.tobytes()


@pytest.fixture
async def wake_voice(tmp_path: Path, repo: Path, monkeypatch):
    monkeypatch.setitem(plugins._BUILTINS["dia.wake"], "fake", "test_wake:FakeWake")
    voice, transcript, spoken = voice_setup(tmp_path, repo)
    raw = tmp_path / "mic.raw"
    voice.options.update(wake={"type": "fake"}, stream_command=["cat", str(raw)])
    voice.__init__(voice.name, voice.options, voice.dia)  # rebuild with the wake word on
    heard: list[int] = []

    async def fake_process(audio: Path) -> None:
        with wave.open(str(audio)) as w:
            heard.append(w.getnframes())

    monkeypatch.setattr(voice, "process", fake_process)
    yield voice, raw, heard, spoken
    # Let Dia finish speaking: a reply cancelled while its synthesis process starts
    # can hang the event loop's shutdown on Python 3.11 (its child watcher loses
    # the exit), as seen in CI.
    while voice._background:
        await asyncio.wait_for(asyncio.gather(*voice._background, return_exceptions=True), 10)


async def test_wake_word_then_record_until_silence(wake_voice) -> None:
    voice, raw, heard, spoken = wake_voice
    raw.write_bytes(
        pcm(("silence", 10), ("wake", 1), ("silence", 3), ("speech", 12), ("silence", 20))
        + pcm(("wake", 1), ("silence", 70))  # woken, but nothing said
    )
    await voice.listen()
    await wait_for(lambda: heard and lines(spoken))
    # 3 quiet chunks before speaking + 12 speech + 10 chunks (0.8 s) of trailing silence
    assert heard == [25 * CHUNK]
    assert lines(spoken) == ["Nie usłyszałam, spróbuj jeszcze raz."]


async def test_dia_does_not_wake_herself(wake_voice) -> None:
    voice, raw, heard, _ = wake_voice
    raw.write_bytes(pcm(("wake", 1), ("speech", 5), ("silence", 20)))
    voice._speaking = True
    await voice.listen()
    assert heard == [] and voice._utterance is None


async def test_shortcut_records_from_the_shared_stream(wake_voice) -> None:
    voice, _, heard, _ = wake_voice
    assert voice.check() is None
    assert await voice.command("toggle") == "recording"
    voice._capture += [pcm(("speech", 1))] * 4  # what listen() would append
    assert await voice.command("toggle") == "processing"
    await wait_for(lambda: heard)
    assert heard == [4 * CHUNK]


def test_openwakeword_adapter(monkeypatch) -> None:
    np = pytest.importorskip("numpy")
    calls = {}

    class Model:
        def __init__(self, wakeword_models, inference_framework):
            calls["model"] = (wakeword_models, inference_framework)

        def predict(self, x):
            calls["dtype"] = x.dtype
            return {"hey_jarvis": 0.9 if x[0] else 0.1}

        def reset(self):
            calls["reset"] = True

    oww = ModuleType("openwakeword")
    oww.model = SimpleNamespace(Model=Model)
    oww.utils = SimpleNamespace(download_models=lambda names: calls.setdefault("dl", names))
    monkeypatch.setitem(sys.modules, "openwakeword", oww)
    monkeypatch.setitem(sys.modules, "openwakeword.model", oww.model)
    monkeypatch.setitem(sys.modules, "openwakeword.utils", oww.utils)

    detector = OpenWakeWord({"threshold": 0.5})
    assert detector.check() is None
    assert detector.detect(array("h", [1] * CHUNK).tobytes())
    assert not detector.detect(array("h", [0] * CHUNK).tobytes())
    detector.reset()
    assert calls["model"] == (["hey_jarvis"], "onnx") and calls["dl"] == ["hey_jarvis"]
    assert calls["dtype"] == np.int16 and calls["reset"]
    assert "not found" in OpenWakeWord({"model": "/nope/hey_dia.onnx"}).check()


def _chunk(level: int) -> bytes:
    from array import array

    return array("h", [level, -level] * 640).tobytes()


def _say(wake, loud_chunks: int) -> bool:
    """Feed quiet, then speech, then a pause; poll until the transcription is judged."""
    import time

    for _ in range(10):
        wake.detect(_chunk(50))
    for _ in range(loud_chunks):
        wake.detect(_chunk(5000))
    for _ in range(10):
        if wake.detect(_chunk(50)):
            return True
    for _ in range(50):
        time.sleep(0.02)
        if wake.detect(_chunk(50)):
            return True
    return False


def test_keyword_wake_hears_hej_dia_and_the_request() -> None:
    from dia.voice.wake import KeywordWake

    heard = iter(["Hej Dia, jaka pogoda w Krakowie?", "zwykła rozmowa przy kawie", "Dia."])
    wake = KeywordWake({}, transcribe=lambda audio: next(heard))
    assert _say(wake, 15)
    assert wake.take_text() == "jaka pogoda w Krakowie"
    voice = wake.take_audio()  # what speaker recognition gets: the speech, not the silence
    assert len(voice) >= 15 * 1280 * 2 and wake.take_audio() == b""
    assert not _say(wake, 15)  # someone talking, no keyword
    assert _say(wake, 6)
    assert wake.take_text() == ""
    assert wake.check() is None


def test_keyword_wake_ignores_clicks() -> None:
    from dia.voice.wake import KeywordWake

    calls = []
    wake = KeywordWake({}, transcribe=lambda audio: calls.append(audio) or "dia")
    assert not _say(wake, 2)  # 160 ms: a click or a cough, not worth transcribing
    assert calls == []
