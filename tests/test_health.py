import asyncio
import os
import subprocess
from pathlib import Path

import pytest

from dia import health
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.store import TaskRecord


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", "echo x > x.txt"]}},
        "projects": {"nova": {"path": str(repo)}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_a_crashing_job_is_restarted(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    runs = []

    async def flaky() -> None:
        runs.append(1)
        if len(runs) < 3:
            raise ConnectionError("discord dropped")

    await asyncio.wait_for(health.supervise(dia, "discord", flaky, first_pause=0.01), 5)
    assert len(runs) == 3
    assert health.state(dia)["discord"] == {
        "state": "finished",
        "at": health.state(dia)["discord"]["at"],
        "restarts": 2,
    }
    assert [a["detail"] for a in dia.store.audit(action="health.restart")][0].startswith(
        "ConnectionError"
    )


async def test_cancelling_stops_it(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)

    async def forever() -> None:
        await asyncio.sleep(3600)

    job = asyncio.ensure_future(health.supervise(dia, "ui", forever))
    await asyncio.sleep(0.01)
    assert health.state(dia)["ui"]["state"] == "running"
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job


async def test_doctor_fix(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    done = (await dia.run_task("nova", "x")).task
    kept = (await dia.run_task("nova", "y")).task
    await dia.discard_task(done.id)
    # a worktree left behind by a task that is gone, and one by a merged task
    leftover = tmp_path / "d" / "worktrees" / "nova" / "20200101-000000-dead"
    subprocess.run(
        ["git", "worktree", "add", "-q", "--detach", str(leftover)], cwd=repo, check=True
    )
    os.chmod(tmp_path / "d", 0o755)
    dia.store.save(TaskRecord(id="stuck", project="nova", agent="a", mode="edit", prompt="z",
                              status="running"))  # fmt: skip

    fixed, left = await health.fix(dia)
    assert any("20200101-000000-dead" in line for line in fixed)
    assert any("permissions" in line for line in fixed)
    assert (os.stat(tmp_path / "d").st_mode & 0o777) == 0o700
    assert not leftover.exists()
    assert Path(kept.details["worktree"]).exists()  # still waiting for review: kept
    assert any("marked running" in line for line in left)
    assert health.interrupted(dia) == ["stuck"]
    assert dia.store.get("stuck").error == "interrupted by a restart"
