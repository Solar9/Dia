import json
import subprocess
from pathlib import Path

import pytest

from dia.config import parse_config
from dia.orchestrator import Orchestrator, TaskActionError
from dia.watch import ProjectWatcher


def commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Ann", "-c", "user.email=a@a", "commit", "-qm", f"edit {name}"],
        cwd=repo,
        check=True,
    )


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    fixer = ["sh", "-c", "echo ok > status.txt; echo fixed it"]
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "fixer"},
            "agents": {"fixer": {"type": "command", "argv": fixer}},
            "projects": {"demo": {"path": str(repo), "test_command": "grep -q ok status.txt"}},
            "watch": {"interval": 1},
        }
    )
    return Orchestrator(config)


async def test_watcher_tests_new_commits_and_reports_breakage(tmp_path: Path, repo: Path) -> None:
    commit(repo, "status.txt", "ok\n")
    orch = make(tmp_path, repo)
    events = []

    async def listen(event):
        events.append(event)

    orch.listeners.append(listen)
    watcher = ProjectWatcher(orch)

    await watcher.poll()  # first look only remembers HEAD
    assert orch.store.recent(10) == []

    commit(repo, "status.txt", "fail\n")
    await watcher.poll()
    check = orch.store.recent(1)[0]
    assert check.mode == "check" and check.status == "failed" and check.tests_ok is False
    assert check.details["watch"]["author"] == "Ann"
    assert [(e.kind, e.message) for e in events] == [("watch", "failed")]
    assert not any((tmp_path / "data" / "worktrees" / "demo").iterdir())

    await watcher.poll()  # same commit: nothing new
    assert len(orch.store.recent(10)) == 1

    report = await orch.fix_build(check.id)
    assert report.task.status == "done" and report.task.tests_ok is True
    assert "edit status.txt" in report.task.prompt
    assert orch.store.get(check.id).details["fix_task"] == report.task.id

    commit(repo, "status.txt", "ok again\n")
    await watcher.poll()
    assert events[-1].message == "fixed"
    state = json.loads((tmp_path / "data" / "watch.json").read_text())
    assert state["demo"]["ok"] is True


async def test_fix_build_only_for_failed_checks(tmp_path: Path, repo: Path) -> None:
    commit(repo, "status.txt", "ok\n")
    orch = make(tmp_path, repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    check = await orch.check_commit("demo", sha)
    assert check.status == "done" and check.tests_ok is True
    with pytest.raises(TaskActionError):
        await orch.fix_build(check.id)
