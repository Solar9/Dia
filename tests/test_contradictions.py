import json
import subprocess
from pathlib import Path

from dia.config import parse_config
from dia.contradictions import check, parse, proposal
from dia.orchestrator import Orchestrator

ANSWER = {
    "contradictions": [
        {
            "claim": "Saves are JSON files",
            "source": "nova.md",
            "evidence": "save.gd:12 opens a SQLite database",
            "correction": "Saves are stored in SQLite (user://save.db).",
        }
    ]
}


def test_parse() -> None:
    text = "I checked.\n" + json.dumps(ANSWER)
    [item] = parse(text)
    assert item["claim"] == "Saves are JSON files"
    assert proposal(item).startswith("Saves are stored in SQLite (user://save.db). (see save.gd")
    assert parse('{"contradictions": []}') == [] and parse("no json") == []
    assert parse('{"contradictions": [{"claim": "x"}]}') == []  # no correction: dropped


async def test_corrections_are_proposals(tmp_path: Path, repo: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    answer = json.dumps(ANSWER).replace("'", "")
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", f"echo '{answer}'"]}},
        "projects": {"nova": {"path": str(repo)}},
        "memory": {"type": "markdown", "vault": str(vault)},
    }
    dia = Orchestrator(parse_config(raw))
    task = await check(dia, "nova")
    assert task.status == "done" and "1 note(s) contradict the code" in task.summary
    assert task.details["learn"][0]["status"] == "proposed"
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True)
    assert status.stdout == b""  # read-only: nothing in the repository changed
    [stored] = dia.decide_facts(task.id)
    assert "SQLite" in stored
    note = next(vault.rglob("nova.md")).read_text()
    assert "Saves are stored in SQLite" in note
