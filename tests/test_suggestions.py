from pathlib import Path

import pytest

from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.store import TaskRecord
from dia.suggestions import Suggestions, find


def make(tmp_path: Path, repo: Path, **suggestions) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", "echo looked"]}},
        "projects": {"nova": {"path": str(repo)}},
        "suggestions": suggestions,
    }
    return Orchestrator(parse_config(raw), use_memory=False)


def troubled(dia: Orchestrator) -> None:
    """Two merges in combat/ this week, one rolled back, one slower."""
    for n, flaw in (("1", {"reverted_by": "r"}), ("2", {"regression": [{"metric": "fps"}]})):
        task = TaskRecord(id=f"t{n}", project="nova", agent="a", mode="edit", prompt=f"parry {n}",
                          status="merged", details=flaw)  # fmt: skip
        dia.store.save(task)
        dia.store.log_decision("merge", "merged", task.prompt, "nova", task.id,
                               detail={"files": [f"combat/parry{n}.gd"]})  # fmt: skip
    for n in range(3):  # tests keep failing
        dia.store.save(TaskRecord(id=f"f{n}", project="nova", agent="a", mode="edit",
                                  prompt="x", status="failed", tests_ok=False))  # fmt: skip


def test_patterns_from_history_only(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    troubled(dia)
    keys = {s["key"] for s in find(dia)}
    assert keys == {"trouble:nova:combat/", "failing:nova"}


async def test_a_few_a_day_never_repeated_and_accepted_on_request(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    troubled(dia)
    events = []

    async def listen(event):
        events.append(event)

    dia.listeners.append(listen)
    suggestions = Suggestions(dia)
    first = await suggestions.check()
    assert len(first) == 1 and events[0].kind == "suggestion"  # per_day = 1
    assert await suggestions.check() == []  # the day's one is made
    key = first[0]["key"]
    report = await suggestions.accept(key)
    assert report.task.mode == "read-only" and report.task.status == "done"
    with pytest.raises(ValueError):
        await suggestions.accept(key)


async def test_dismissed_never_again(tmp_path, repo) -> None:
    dia = make(tmp_path, repo, per_day=5)
    troubled(dia)
    suggestions = Suggestions(dia)
    made = await suggestions.check()
    assert len(made) == 2
    suggestions.dismiss(made[0]["key"])
    data = suggestions._load()
    data["seen"] = {}  # even after the repeat window
    suggestions._save(data)
    again = await suggestions.check()
    assert made[0]["key"] not in {s["key"] for s in again}


async def test_off(tmp_path, repo) -> None:
    dia = make(tmp_path, repo, enabled=False)
    troubled(dia)
    assert await Suggestions(dia).check() == []


def test_a_suggestion_counts_for_the_local_day_it_was_made(monkeypatch) -> None:
    import time
    from datetime import date

    from dia.suggestions import _local_day

    monkeypatch.setenv("TZ", "Europe/Warsaw")
    time.tzset()
    try:
        # made just before midnight UTC = after midnight in Warsaw (stored times are UTC)
        assert _local_day("2026-10-26T23:56:47+00:00") == date(2026, 10, 27)
        assert _local_day("garbage") is None
    finally:
        monkeypatch.undo()
        time.tzset()
