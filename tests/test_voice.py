import asyncio
import json
import sys
from array import array
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from dia.channels.voice import VoiceChannel, send_command, speakable
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.voice.audio import Recorder
from dia.voice.stt import FasterWhisperSTT
from dia.voice.tts import CommandTTS, PiperTTS

# Records until SIGINT like pw-record/arecord do, writing a (fake) WAV.
FAKE_RECORDER = [
    "sh",
    "-c",
    "printf RIFF > \"$0\"; trap 'exit 0' INT TERM; while :; do sleep 0.05; done",
    "{output}",
]


def voice_setup(tmp_path: Path, repo: Path, llm_answer: dict | None = None):
    transcript = tmp_path / "heard.txt"
    spoken = tmp_path / "spoken.log"
    agents = {"worker": {"type": "command", "argv": ["sh", "-c", 'echo "answer: $0"', "{prompt}"]}}
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "worker", "brain": ["rules"]},
        "agents": agents,
        "projects": {"demo": {"path": str(repo)}},
        "channels": {
            "voice": {
                "language": "pl",
                "socket": str(tmp_path / "v.sock"),
                "notifications": False,
                "record_command": FAKE_RECORDER,
                "play_command": ["true", "{input}"],
                "stt": {"type": "command", "argv": ["cat", str(transcript)]},
                "tts": {
                    "type": "command",
                    "argv": [
                        "sh",
                        "-c",
                        'printf "%s\\n" "$0" >> "$1"; : > "$2"',
                        "{text}",
                        str(spoken),
                        "{output}",
                    ],
                },
            }
        },
    }
    if llm_answer:
        agents["llm"] = {"type": "command", "argv": ["echo", json.dumps(llm_answer)]}
        raw["brains"] = {"router": {"type": "agent", "agent": "llm"}}
        raw["dia"]["brain"] = ["rules", "router"]
    orch = Orchestrator(parse_config(raw))
    voice = orch.config.channel("voice", orch)
    return voice, transcript, spoken


async def wait_for(predicate, timeout: float = 10) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not predicate():
        if loop.time() > end:
            raise AssertionError("timed out")
        await asyncio.sleep(0.05)


def recording_started(voice):
    # The fake recorder writes its file right away; real ones do within milliseconds.
    return lambda: voice.recorder.path is not None and voice.recorder.path.exists()


def lines(path: Path) -> list[str]:
    return path.read_text().splitlines() if path.exists() else []


async def test_push_to_talk_round_trip_over_the_socket(tmp_path: Path, repo: Path) -> None:
    voice, transcript, spoken = voice_setup(tmp_path, repo)
    assert isinstance(voice, VoiceChannel) and voice.check() is None
    server = asyncio.create_task(voice.run())
    try:
        await wait_for(voice.socket.exists)
        assert await send_command("ping", voice.socket) == "pong"

        transcript.write_text("Dia, status\n")
        assert await send_command("toggle", voice.socket) == "recording"
        await wait_for(recording_started(voice))
        assert await send_command("toggle", voice.socket) == "processing"
        await wait_for(lambda: lines(spoken))
        assert lines(spoken)[0] == "Gotowi agenci: worker. Żadne zadanie teraz nie trwa."

        transcript.write_text("")  # silence
        await send_command("start", voice.socket)
        await wait_for(recording_started(voice))
        await send_command("stop", voice.socket)
        await wait_for(lambda: len(lines(spoken)) == 2)
        assert lines(spoken)[1] == "Nie usłyszałam, spróbuj jeszcze raz."
    finally:
        server.cancel()
        await asyncio.gather(server, return_exceptions=True)
    assert not voice.socket.exists()


async def test_spoken_request_runs_a_task_and_reports_back(tmp_path: Path, repo: Path) -> None:
    answer = {"action": "ask", "project": "demo", "prompt": "Co tu jest?", "reply": "Sprawdzam."}
    voice, transcript, spoken = voice_setup(tmp_path, repo, answer)
    transcript.write_text("co jest w projekcie demo?")
    await voice.command("start")
    await wait_for(recording_started(voice))
    await voice.command("stop")
    await wait_for(lambda: len(lines(spoken)) == 2)
    first, second = lines(spoken)
    assert first == "Sprawdzam."
    assert second.startswith("Zadanie w demo zakończone.") and "answer: Co tu jest?" in second


async def test_voice_client_without_server(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not running"):
        await send_command("toggle", tmp_path / "nothing.sock")


def test_speakable_strips_markdown_and_cuts_at_sentences() -> None:
    text = "**Gotowe.** Zmieniłam `player.gd`, zob. [[Gry/Nova|Nova]].\n```gd\ncode\n```\nKoniec."
    assert speakable(text) == "Gotowe. Zmieniłam player.gd, zob. Nova. Koniec."
    long = "Pierwsze zdanie jest tutaj. " * 30
    cut = speakable(long, 100)
    assert len(cut) <= 100 and cut.endswith(".")


async def test_recorder_stops_on_sigint(tmp_path: Path) -> None:
    recorder = Recorder(FAKE_RECORDER)
    await recorder.start(tmp_path / "a.wav")
    assert recorder.recording
    await wait_for(lambda: (tmp_path / "a.wav").exists())
    assert (await recorder.stop()).read_text() == "RIFF"
    silent = Recorder(["sh", "-c", "sleep 30", "{output}"])
    await silent.start(tmp_path / "b.wav")
    with pytest.raises(RuntimeError, match="recording failed"):
        await silent.stop()


async def test_faster_whisper_is_called_once_loaded(monkeypatch, tmp_path: Path) -> None:
    calls = {}
    # Decoding is tested separately (and needs numpy); here only the model call matters.
    monkeypatch.setattr("dia.voice.stt.read_wav", lambda path: str(path))

    class FakeModel:
        def __init__(self, name, device, compute_type, download_root):
            calls["init"] = (name, device, compute_type)

        def transcribe(self, audio, language, beam_size, vad_filter, initial_prompt=None):
            calls["transcribe"] = (language, vad_filter, initial_prompt)
            return iter([SimpleNamespace(text=" Dodaj "), SimpleNamespace(text="strzelbę. ")]), None

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    stt = FasterWhisperSTT({"model": "small"})
    assert await stt.transcribe(tmp_path / "x.wav", "pl") == "Dodaj strzelbę."
    assert calls == {"init": ("small", "cpu", "int8"), "transcribe": ("pl", True, "Dia")}


def test_piper_voice_resolution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "piper", ModuleType("piper"))  # installed or not
    tts = PiperTTS({"voice": "pl_PL-gosia-medium", "voices_dir": str(tmp_path)})
    assert tts.model_path == tmp_path / "pl_PL-gosia-medium.onnx"
    argv = tts.argv(tts.model_path, tmp_path / "o.wav")
    assert argv[1:3] == ["-m", "piper"] and argv[-2:] == ["-f", str(tmp_path / "o.wav")]
    missing = PiperTTS({"voice": str(tmp_path / "nope.onnx")})
    assert "not found" in (missing.check() or "")


def test_command_tts_may_speak_by_itself() -> None:
    assert not CommandTTS({"argv": ["spd-say", "{text}"]}).writes_file
    assert CommandTTS({"argv": ["espeak-ng", "-w", "{output}", "{text}"]}).writes_file


async def test_ci_results_are_announced(tmp_path: Path, repo: Path) -> None:
    voice, _, spoken = voice_setup(tmp_path, repo)
    task = SimpleNamespace(project="nova")
    await voice.on_dia_event(SimpleNamespace(kind="ci", task=task, message="failed"))
    assert lines(spoken) == ["Testy CI w projekcie nova nie przeszły."]


async def test_spoken_plan_waits_for_yes(tmp_path: Path, repo: Path) -> None:
    answer = {"action": "plan", "project": "demo", "prompt": "a cache", "reply": "Planuję."}
    voice, transcript, spoken = voice_setup(tmp_path, repo, answer)
    voice.dia.config.pipelines = {}
    voice.dia.config.plans = {"planner": "planner"}
    steps = {"steps": [{"title": "Build", "agent": "worker", "prompt": "Build a cache"}]}
    voice.dia.config.agents["planner"] = {"type": "command", "argv": ["echo", json.dumps(steps)]}

    async def say_aloud(text: str) -> None:
        transcript.write_text(text)
        await voice.command("start")
        await wait_for(recording_started(voice))
        await voice.command("stop")

    def said() -> str:  # Dia speaks sentence by sentence: one line each
        return " ".join(lines(spoken))

    await say_aloud("zbuduj cache w demo w kilku krokach")
    await wait_for(lambda: said().endswith("Powiedz tak albo nie."))
    assert said() == ("Planuję. Plan dla demo: 1. Build (worker). Uruchomić? Powiedz tak albo nie.")
    before = said()
    await say_aloud("tak")
    await wait_for(lambda: "zakończone" in said()[len(before) :])
    assert said()[len(before) :].strip().startswith("Zadanie w demo zakończone.")


async def test_silent_recording_is_reported(tmp_path: Path, repo: Path) -> None:
    from dia.voice.audio import write_wav

    voice, transcript, spoken = voice_setup(tmp_path, repo)
    transcript.write_text("Dia, status")  # would be heard if the audio were checked
    await voice.process(write_wav(tmp_path / "quiet.wav", [bytes(3200)]))
    assert lines(spoken) == [
        "Mikrofon nagrał samą ciszę. Sprawdź, czy wybrane jest właściwe wejście."
    ]


def test_whisper_gets_samples_not_a_file(tmp_path: Path) -> None:
    np = pytest.importorskip("numpy")
    from dia.voice.audio import write_wav
    from dia.voice.stt import read_wav

    samples = read_wav(write_wav(tmp_path / "a.wav", [array("h", [16384, -16384]).tobytes()]))
    assert isinstance(samples, np.ndarray) and samples.tolist() == [0.5, -0.5]
    other = tmp_path / "x.mp3"
    other.write_bytes(b"not a wav")
    assert read_wav(other) == str(other)  # anything else is left to faster-whisper


async def test_quiet_mode_keeps_dia_silent(tmp_path: Path, repo: Path) -> None:
    voice, _, spoken = voice_setup(tmp_path, repo)
    voice.dia.set_quiet(True)
    await voice.say("cicho")
    assert lines(spoken) == []
    voice.dia.set_quiet(False)
    await voice.say("głośno")
    assert lines(spoken) == ["głośno"]


def test_sentences_for_speaking() -> None:
    from dia.channels.voice import sentences

    assert sentences("Tak. Zrobione. Testy przeszły, gałąź czeka na scalenie! A co dalej?") == [
        "Tak. Zrobione. Testy przeszły, gałąź czeka na scalenie!",
        "A co dalej?",
    ]


async def test_interrupting_stops_the_rest_of_the_answer(tmp_path: Path, repo: Path) -> None:
    import asyncio

    voice, _, spoken = voice_setup(tmp_path, repo)
    long_answer = " ".join(
        f"To jest dość długie zdanie numer {i} w tej odpowiedzi." for i in range(6)
    )

    async def slow_play(path):
        await asyncio.sleep(0.2)

    voice.player.play = slow_play
    speaking = asyncio.create_task(voice.say(long_answer))
    await asyncio.sleep(0.3)
    voice.interrupt()
    await speaking
    assert 1 <= len(lines(spoken)) < 6
