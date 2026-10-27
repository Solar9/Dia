import json
from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.brains.rules import RulesBrain
from dia.config import parse_config
from dia.learn import parse_howto
from dia.orchestrator import Orchestrator, TaskActionError

HOWTO = {
    "title": "Adding an enemy type",
    "when": "new enemy, enemy type, opponent",
    "steps": "1. Copy scenes/enemies/base.tscn.\n2. Register it in enemies.gd.",
}


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    writer = ["sh", "-c", f"echo '{json.dumps(HOWTO)}'"]
    worker = ["sh", "-c", "echo x > x.txt; echo 'added the bat enemy'"]
    config = parse_config(
        {
            "dia": {
                "data_dir": str(tmp_path / "data"),
                "default_agent": "worker",
                "language": "pl",
            },
            "agents": {
                "worker": {"type": "command", "argv": worker},
                "writer": {"type": "command", "argv": writer},
            },
            "projects": {"nova": {"path": str(repo)}, "other": {"path": str(repo)}},
            "memory": {
                "type": "markdown",
                "vault": str(tmp_path / "vault"),
                "learn_agent": "writer",
            },
        }
    )
    (tmp_path / "vault").mkdir(parents=True)
    return Orchestrator(config)


def test_parse_howto() -> None:
    assert parse_howto("Here:\n" + json.dumps(HOWTO)) == HOWTO
    assert parse_howto('{"title": "x"}') is None
    assert parse_howto("no json") is None


async def test_a_finished_task_becomes_a_howto_the_agents_follow(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    task = (await dia.run_task("nova", "add a bat enemy")).task
    with pytest.raises(TaskActionError):
        dia.accept_howto(task.id)  # nothing proposed yet

    assert await dia.propose_howto(task.id) == HOWTO
    path = dia.accept_howto(task.id, {"title": "Adding enemies"})
    note = tmp_path / "vault" / "Dia" / path
    assert path == "How-tos/Adding enemies.md" and "Register it in enemies.gd" in note.read_text()
    assert dia.store.get(task.id).details["howto"]["status"] == "accepted"

    memory = dia.memory
    assert [h["title"] for h in memory.howtos()] == ["Adding enemies"]
    project = dia.config.project("nova")
    assert "Register it in enemies.gd" in memory.context_for(
        project, "dodaj nowego enemy: nietoperz"
    )
    assert "How-tos" not in memory.context_for(project, "napraw zapisywanie gry")
    # Only for the project it came from.
    assert "How-tos" not in memory.context_for(dia.config.project("other"), "new enemy type")
    assert [n["kind"] for n in memory.notes() if n["path"] == path] == ["howto"]


async def test_by_voice_dia_asks_before_keeping_it(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
    assert "Nie widzę" in (await assistant.handle("Dia, zapamiętaj jak to zrobiłeś")).text

    await dia.run_task("nova", "add a bat enemy")
    ask = (await assistant.handle("Dia, zapamiętaj, jak to zrobiłeś")).text
    assert "Adding an enemy type" in ask and ask.endswith("?")
    assert dia.memory.howtos() == []
    assert "Zapisane" in (await assistant.handle("tak")).text
    assert len(dia.memory.howtos()) == 1
