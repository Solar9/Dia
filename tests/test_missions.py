import json
import subprocess
from pathlib import Path

import pytest

from dia.config import parse_config
from dia.missions import Missions, parse_mission
from dia.orchestrator import Orchestrator

PLAN = {
    "steps": [
        {
            "id": "s1",
            "title": "Design",
            "agent": "worker",
            "prompt": "FILE:design",
            "depends_on": [],
        },
        {
            "id": "s2",
            "title": "Server",
            "agent": "worker",
            "prompt": "FILE:server",
            "depends_on": ["s1"],
        },
        {
            "id": "s3",
            "title": "Client",
            "agent": "worker",
            "prompt": "FILE:client",
            "depends_on": ["s1"],
        },
        {
            "id": "s4",
            "title": "Docs",
            "agent": "worker",
            "prompt": "FILE:docs",
            "depends_on": ["s2", "s3"],
        },
    ]
}
# Writes <name>.txt for the last FILE:<name> in its prompt (its own step comes last).
WORKER = (
    'f=$(echo "$0" | grep -o "FILE:[a-z]*" | tail -1 | cut -d: -f2); '
    'echo ok > "$f.txt"; echo "made $f"'
)


def make(tmp_path: Path, repo: Path, plan: dict, budget_calls: int = 30) -> Orchestrator:
    config = parse_config(
        {
            "dia": {
                "data_dir": str(tmp_path / "data"),
                "default_agent": "worker",
                "max_parallel_tasks": 2,
            },
            "agents": {
                "worker": {"type": "command", "argv": ["sh", "-c", WORKER, "{prompt}"]},
                "planner": {"type": "command", "argv": ["echo", json.dumps(plan)]},
            },
            "projects": {"demo": {"path": str(repo), "test_command": "test -f docs.txt"}},
            "missions": {"planner": "planner", "budget_calls": budget_calls},
        }
    )
    return Orchestrator(config, use_memory=False)


def test_parse_mission_validates_the_graph() -> None:
    steps = parse_mission(json.dumps(PLAN), ["worker"], 6)
    assert [s.depends_on for s in steps] == [[], ["s1"], ["s1"], ["s2", "s3"]]
    cycle = {
        "steps": [
            {"id": "a", "agent": "worker", "prompt": "x", "depends_on": ["b"]},
            {"id": "b", "agent": "worker", "prompt": "y", "depends_on": ["a"]},
        ]
    }
    with pytest.raises(ValueError, match="cycle"):
        parse_mission(json.dumps(cycle), ["worker"], 6)
    with pytest.raises(ValueError, match="unknown steps"):
        parse_mission(
            '{"steps": [{"id": "a", "agent": "worker", "prompt": "x", "depends_on": ["zz"]}]}',
            ["worker"],
            6,
        )


async def test_mission_runs_a_graph_and_integrates(tmp_path: Path, repo: Path) -> None:
    dia = make(tmp_path, repo, PLAN)
    missions = Missions(dia)
    mission = await missions.create("demo", "Add a co-op mode")
    assert mission.status == "planned" and mission.mode == "mission"

    report = await dia.run_plan(mission.id)  # the same "run" path plans use
    mission = report.task
    assert mission.status == "done", mission.error
    assert mission.tests_ok is True and mission.branch == f"dia/{mission.id}"
    files = subprocess.run(
        ["git", "ls-tree", "--name-only", mission.branch], cwd=repo, capture_output=True, text=True
    ).stdout.split()
    assert {"design.txt", "server.txt", "client.txt", "docs.txt"} <= set(files)
    steps = mission.details["mission"]["steps"]
    assert all(s["status"] == "done" and s["task_id"] for s in steps)
    log = [e["text"] for e in mission.details["mission"]["log"]]
    assert log[-1].startswith("ready for your review")
    assert missions.budget(mission)["used"]["calls"] == 4

    sha = await dia.merge_task(mission.id)
    assert sha and (repo / "docs.txt").exists()
    leftovers = subprocess.run(
        ["git", "branch", "--list", "dia/*"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert leftovers.strip() == ""  # step and helper branches cleaned up


async def test_budget_pauses_and_continue_resumes(tmp_path: Path, repo: Path) -> None:
    dia = make(tmp_path, repo, PLAN, budget_calls=1)
    mission = await Missions(dia).create("demo", "Add a co-op mode")
    mission = (await dia.run_plan(mission.id)).task
    assert mission.status == "paused" and "budget" in mission.error
    statuses = [s["status"] for s in mission.details["mission"]["steps"]]
    assert statuses == ["done", "skipped", "skipped", "skipped"]

    mission.details["mission"]["budget"]["calls"] = 10
    dia.store.save(mission)
    mission = (await dia.run_plan(mission.id)).task
    assert mission.status == "done", mission.error


async def test_continue_reruns_failed_steps_and_reintegrates(tmp_path: Path, repo: Path) -> None:
    flag = tmp_path / "docs-may-pass"
    flaky = (
        'f=$(echo "$0" | grep -o "FILE:[a-z]*" | tail -1 | cut -d: -f2); '
        f'if [ "$f" = docs ] && [ ! -f {flag} ]; then echo "not yet" >&2; exit 1; fi; '
        'echo ok > "$f.txt"; echo "made $f"'
    )
    dia = make(tmp_path, repo, PLAN)
    dia.config.agents["worker"]["argv"] = ["sh", "-c", flaky, "{prompt}"]
    mission = await Missions(dia).create("demo", "Add a co-op mode")
    mission = (await dia.run_plan(mission.id)).task
    assert mission.status == "failed" and "Docs" in mission.error

    flag.write_text("")
    mission = (await dia.run_plan(mission.id)).task  # Continue
    assert mission.status == "done", mission.error
    steps = {s["id"]: s["status"] for s in mission.details["mission"]["steps"]}
    assert set(steps.values()) == {"done"}
