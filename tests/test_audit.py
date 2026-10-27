from pathlib import Path

from dia.audit import acting_as
from dia.config import parse_config
from dia.orchestrator import Orchestrator


async def test_actions_are_logged_with_their_actor(tmp_path: Path, repo: Path) -> None:
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a"},
            "agents": {"a": {"type": "command", "argv": ["sh", "-c", "echo x > x.txt"]}},
            "projects": {"demo": {"path": str(repo)}},
        }
    )
    dia = Orchestrator(config, use_memory=False)
    seen = []
    dia.store.audit_listeners.append(seen.append)
    task = (await dia.run_task("demo", "add x")).task
    with acting_as("device:phone"):
        await dia.discard_task(task.id)
    rows = dia.store.audit()
    assert [(r["actor"], r["action"]) for r in reversed(rows)] == [
        ("cli", "task.start"),
        ("cli", "task.finish"),
        ("device:phone", "task.discard"),
    ]
    assert rows[1]["detail"] == "done" and rows[0]["target"] == task.id
    assert [r["action"] for r in dia.store.audit(action="task.d")] == ["task.discard"]
    assert len(seen) == 3


async def test_emergency_stop_ends_agents_and_blocks_new_work(tmp_path: Path, repo: Path) -> None:
    import asyncio

    import pytest

    from dia.orchestrator import TaskActionError

    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "slow"},
            "agents": {"slow": {"type": "command", "argv": ["sh", "-c", "sleep 30; echo done"]}},
            "projects": {"demo": {"path": str(repo)}},
        }
    )
    dia = Orchestrator(config, use_memory=False)
    running = asyncio.create_task(dia.run_task("demo", "take forever"))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if dia.store.recent(1) and dia.store.recent(1)[0].status == "running":
            break
    await asyncio.sleep(0.3)  # the agent process has started
    stopped = await dia.stop_all("test")
    assert len(stopped) == 1
    report = await asyncio.wait_for(running, 10)
    assert report.task.status == "failed" and "emergency stop" in report.task.error

    with pytest.raises(TaskActionError, match="stopped"):
        await dia.run_task("demo", "anything")
    assert Orchestrator(config, use_memory=False).halted  # survives a restart
    await dia.resume()
    assert not Orchestrator(config, use_memory=False).halted
    assert [r["action"] for r in dia.store.audit(action="dia.")] == ["dia.resume", "dia.stop"]
