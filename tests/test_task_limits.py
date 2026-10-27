from pathlib import Path

from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.task_limits import TaskLimits


def make(tmp_path: Path, repo: Path, agent: list[str], limits: dict) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": agent}},
        "projects": {"demo": {"path": str(repo), "test_command": "false"}},
        "task_limits": limits,
        "retry": {"test_fixes": 5},  # would keep calling the agent without a limit
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_a_task_stops_at_its_call_limit(tmp_path, repo) -> None:
    dia = make(tmp_path, repo, ["sh", "-c", "date +%N > x.txt"], {"calls": 3})
    task = (await dia.run_task("demo", "keep trying")).task
    assert dia.store.usage_for([task.id])["calls"] == 3
    assert task.status == "failed"
    assert len(task.details["retries"]) == 3  # the third fix was refused by the limit


async def test_a_call_is_cut_at_the_agent_timeout(tmp_path, repo) -> None:
    dia = make(tmp_path, repo, ["sleep", "5"], {"agent_timeout": 0.5})
    dia.config.project("demo").test_command = None
    task = (await dia.run_task("demo", "slow")).task
    assert task.status == "failed" and "timed out" in (task.error or "")


def test_priority_and_project_overrides(tmp_path, repo) -> None:
    dia = make(tmp_path, repo, ["true"], {"nice": 30, "minutes": 10})
    project = dia.config.project("demo")
    project.options["task_limits"] = {"minutes": 90}
    limits = TaskLimits.for_project(dia.config, project)
    assert (limits.nice, limits.minutes) == (19, 90)
    assert limits.wrap(["godot"])[:3] == ["nice", "-n", "19"]
    assert TaskLimits().wrap(["godot"]) == ["godot"]
    assert TaskLimits(agent_timeout=60).timeout(dia.store, None, 600) == 60
    assert TaskLimits().timeout(dia.store, None, None) is None


async def test_the_minute_budget_bounds_a_call(tmp_path, repo) -> None:
    import time

    dia = make(tmp_path, repo, ["sleep", "10"], {"minutes": 0.01, "agent_timeout": 5})
    dia.config.project("demo").test_command = None
    started = time.monotonic()
    task = (await dia.run_task("demo", "slow")).task
    assert time.monotonic() - started < 3  # 0.6 s of budget, not the 5 s timeout
    assert task.status == "failed" and "timed out after 0.6" in (task.error or "")
