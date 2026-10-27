from pathlib import Path

from dia.assistant import Assistant
from dia.brains.rules import RulesBrain
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.persona import persona_prompt
from dia.preferences import Preferences, learn_preferences, parse_preferences


def make(tmp_path: Path, repo: Path | None = None, **assistant) -> Orchestrator:
    learner = ["sh", "-c", """echo '{"preferences": ["The user prefers short answers"]}'"""]
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "language": "pl", "default_agent": "learner"},
        "agents": {"learner": {"type": "command", "argv": learner}},
        "assistant": assistant,
    }
    if repo:
        raw["projects"] = {"demo": {"path": str(repo)}}
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_a_stated_preference_is_kept_and_followed(tmp_path) -> None:
    dia = make(tmp_path, preferences=["Uses Godot 4"])
    assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
    answer = (await assistant.handle("Dia, zapamiętaj, że wolę krótkie odpowiedzi.")).text
    assert answer == "Zapamiętam: wolę krótkie odpowiedzi."
    prompt = persona_prompt(dia.config)
    assert "- Uses Godot 4\n- wolę krótkie odpowiedzi" in prompt
    assert dia.store.audit(action="preference.add")[0]["detail"] == "wolę krótkie odpowiedzi"
    # Said twice, kept once.
    await assistant.handle("zapamiętaj, że wolę krótkie odpowiedzi")
    assert Preferences(dia.config).active() == ["Uses Godot 4", "wolę krótkie odpowiedzi"]


async def test_agents_get_the_preferences_too(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    Preferences(dia.config).add("Type hints everywhere")
    assert "Type hints everywhere" in dia._context(dia.config.project("demo"), "anything")


def test_parse_preferences() -> None:
    assert parse_preferences('x {"preferences": ["a", 3, "", "b"]}') == ["a", "b"]
    assert parse_preferences("none") == []


async def test_noticed_preferences_wait_for_approval(tmp_path) -> None:
    dia = make(tmp_path)
    prefs = Preferences(dia.config)
    new = await learn_preferences(dia, [("krócej proszę", "Dobrze.")])
    assert new == ["The user prefers short answers"]
    assert prefs.active() == []  # not before you accept it
    assert await learn_preferences(dia, [("x", "y")]) == []  # already proposed
    assert prefs.decide(0, accept=True) == "The user prefers short answers"
    assert prefs.active() == ["The user prefers short answers"]
    assert prefs.remove(0) == "The user prefers short answers" and prefs.active() == []


async def test_learning_runs_every_n_turns_when_switched_on(tmp_path) -> None:
    dia = make(tmp_path, learn_preferences=True, learn_every=2)
    assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
    await assistant.handle("status")
    await dia.drain()
    assert Preferences(dia.config).snapshot()["proposed"] == []
    await assistant.handle("zadania")
    await dia.drain()
    assert [p["text"] for p in Preferences(dia.config).snapshot()["proposed"]] == [
        "The user prefers short answers"
    ]
