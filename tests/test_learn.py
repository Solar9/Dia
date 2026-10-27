from pathlib import Path

import pytest

from dia.config import parse_config
from dia.learn import parse_facts
from dia.orchestrator import Orchestrator, TaskActionError


def test_parse_facts() -> None:
    answer = 'Sure:\n{"facts": ["Tests run with  `gut`.", "", 3, "Saves live in user://"]}'
    assert parse_facts(answer) == ["Tests run with `gut`.", "Saves live in user://"]
    assert parse_facts('{"facts": []}') == []
    assert parse_facts("nothing worth keeping") == []
    assert len(parse_facts('{"facts": ["a", "b", "c", "d"]}')) == 3


def make(tmp_path: Path, repo: Path, learn: bool = True) -> Orchestrator:
    learner = ["sh", "-c", """echo '{"facts": ["The build uses make."]}'"""]
    worker = ["sh", "-c", "echo x > x.txt; echo done"]
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "worker"},
            "agents": {
                "worker": {"type": "command", "argv": worker},
                "learner": {"type": "command", "argv": learner},
            },
            "projects": {"demo": {"path": str(repo)}},
            "memory": {
                "type": "markdown",
                "vault": str(tmp_path / "vault"),
                "learn": learn,
                "learn_agent": "learner",
            },
        }
    )
    (tmp_path / "vault").mkdir(parents=True)
    return Orchestrator(config)


async def test_task_proposes_facts_and_accepting_appends_them(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo)
    events = []

    async def listen(event):
        events.append(event)

    orch.listeners.append(listen)
    task = (await orch.run_task("demo", "add x")).task
    await orch.drain()
    task = orch.store.get(task.id)
    assert task.details["learn"] == [{"fact": "The build uses make.", "status": "proposed"}]
    assert [e.kind for e in events] == ["learn"]
    assert orch.pending_facts()[0].id == task.id

    note = tmp_path / "vault" / "Dia" / "Projects" / "demo.md"
    before = note.read_text()
    assert orch.decide_facts(task.id) == ["The build uses make."]
    after = note.read_text()
    assert after.startswith(before)  # append-only
    assert "## Learned by Dia" in after and "- The build uses make. (" in after
    assert orch.pending_facts() == []
    # Deciding again stores nothing twice.
    assert orch.decide_facts(task.id) == []

    orch.remember("demo", "Second  fact")
    text = note.read_text()
    assert text.count("## Learned by Dia") == 1 and "- Second fact (" in text


async def test_rejecting_and_learning_off(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo)
    task = (await orch.run_task("demo", "add x")).task
    await orch.drain()
    assert orch.decide_facts(task.id, accept=[], reject=[0]) == []
    assert orch.store.get(task.id).details["learn"][0]["status"] == "rejected"

    off = make(tmp_path / "off", repo, learn=False)
    task = (await off.run_task("demo", "add y")).task
    await off.drain()
    assert "learn" not in off.store.get(task.id).details
    with pytest.raises(TaskActionError):
        off.decide_facts(task.id)
