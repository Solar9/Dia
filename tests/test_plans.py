import json
import subprocess
from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.config import parse_config
from dia.orchestrator import Orchestrator, TaskActionError
from dia.plans import Step, parse_plan, step_prompt

DESIGNER = ["sh", "-c", "echo 'use a dict' > DESIGN.md; echo 'wrote DESIGN.md'"]
# Implements from the design, and proves it saw the earlier step's summary.
BUILDER = [
    "sh",
    "-c",
    'test -f DESIGN.md || exit 3; case "$0" in *"wrote DESIGN.md"*) ;; *) exit 4;; esac; '
    "cp DESIGN.md impl.txt; echo 'built it'",
    "{prompt}",
]
FAILING = ["sh", "-c", "echo broken >&2; exit 1"]


def make(tmp_path: Path, repo: Path, **extra) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "designer"},
        "agents": {
            "designer": {"type": "command", "argv": DESIGNER, "role": "architect"},
            "builder": {"type": "command", "argv": BUILDER, "role": "implementer"},
            "failing": {"type": "command", "argv": FAILING},
        },
        "projects": {"demo": {"path": str(repo)}},
        "pipelines": {
            "feature": {
                "steps": [
                    {"agent": "designer", "title": "Design", "prompt": "Design {goal}"},
                    {"agent": "builder", "title": "Build", "prompt": "Build {goal}"},
                ]
            },
            "broken": {
                "steps": [
                    {"agent": "designer", "prompt": "a"},
                    {"agent": "failing", "prompt": "b"},
                    {"agent": "builder", "prompt": "c"},
                ]
            },
        },
    }
    raw.update(extra)
    return Orchestrator(parse_config(raw))


def log(repo: Path, branch: str) -> list[str]:
    out = subprocess.run(
        ["git", "log", "--format=%s", f"main..{branch}"], cwd=repo, capture_output=True, text=True
    ).stdout
    return out.splitlines()


async def test_pipeline_runs_steps_on_one_branch(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo)
    plan = await orch.create_plan("demo", "a cache", pipeline="feature")
    assert plan.status == "planned" and plan.agent == "designer+builder"
    assert [s["prompt"] for s in plan.details["plan"]] == ["Design a cache", "Build a cache"]

    report = await orch.run_plan(plan.id)
    task = report.task
    assert task.status == "done", task.error
    assert [s["agent"] for s in task.details["steps"]] == ["designer", "builder"]
    assert log(repo, task.branch) == ["dia: step 2: Build", "dia: step 1: Design"]
    assert task.details["author"] == "builder"  # fixes for review/CI go to the last author
    assert "### Design (designer)\nwrote DESIGN.md" in task.summary
    assert "impl.txt" in report.diff_stat
    with pytest.raises(TaskActionError, match="not a plan waiting"):
        await orch.run_plan(plan.id)


async def test_failed_step_stops_the_plan(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo)
    task = (await orch.run_plan((await orch.create_plan("demo", "x", pipeline="broken")).id)).task
    assert task.status == "failed"
    assert [(s["agent"], s["success"]) for s in task.details["steps"]] == [
        ("designer", True),
        ("failing", False),
    ]
    assert "broken" in task.error and task.commit_sha  # step 1's work is kept for review


async def test_planner_agent_proposes_steps(tmp_path: Path, repo: Path) -> None:
    proposal = {
        "steps": [
            {"title": "Design", "agent": "Designer", "prompt": "Design the inventory"},
            {"title": "Build", "agent": "builder", "prompt": "Build it"},
        ]
    }
    planner = [
        "sh",
        "-c",
        'case "$0" in *architect*implementer*) echo "$1";; *) exit 5;; esac',
        "{prompt}",
        json.dumps(proposal),
    ]
    orch = make(tmp_path, repo, plans={"planner": "planner", "max_steps": 3})
    orch.config.agents["planner"] = {"type": "command", "argv": planner}
    plan = await orch.create_plan("demo", "inventory system")
    assert [(s["agent"], s["title"]) for s in plan.details["plan"]] == [
        ("designer", "Design"),
        ("builder", "Build"),
    ]
    branches = subprocess.run(
        ["git", "branch", "--list", "dia/*"], cwd=repo, capture_output=True, text=True
    ).stdout
    assert branches == ""  # the planner's scratch worktree is gone


def test_parse_plan_validates() -> None:
    raw = '{"steps": [{"agent": "x", "prompt": "p"}, {"agent": "y", "prompt": "q"}]}'
    assert [s.agent for s in parse_plan(raw, ["x", "y"], 1)] == ["x"]  # capped
    with pytest.raises(ValueError, match="unknown agent"):
        parse_plan('{"steps": [{"agent": "z", "prompt": "p"}]}', ["x"], 3)
    with pytest.raises(ValueError, match="empty"):
        parse_plan('{"steps": []}', ["x"], 3)


def test_single_step_prompt_is_untouched() -> None:
    assert step_prompt("goal", [Step("a", "do it")], 0, []) == "do it"
    multi = step_prompt(
        "goal",
        [Step("a", "one", "A"), Step("b", "two", "B")],
        1,
        [{"title": "A", "agent": "a", "summary": "did one"}],
    )
    assert "Overall goal:\ngoal" in multi and "- A (a): did one" in multi and "two" in multi


async def test_unknown_pipeline_or_agent(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo)
    with pytest.raises(TaskActionError, match="unknown pipeline"):
        await orch.create_plan("demo", "x", pipeline="nope")
    orch.config.pipelines["bad"] = {"steps": [{"agent": "ghost", "prompt": "p"}]}
    with pytest.raises(TaskActionError, match="ghost"):
        await orch.create_plan("demo", "x", pipeline="bad")


async def test_brain_can_ask_for_a_plan(tmp_path: Path, repo: Path) -> None:
    proposal = {
        "steps": [
            {"title": "Design", "agent": "designer", "prompt": "Design it"},
            {"title": "Build", "agent": "builder", "prompt": "Build it"},
        ]
    }
    intent = {"action": "plan", "project": "demo", "prompt": "a cache", "reply": "Planuję."}
    orch = make(
        tmp_path,
        repo,
        plans={"planner": "planner"},
        brains={"router": {"type": "agent", "agent": "llm"}},
    )
    orch.config.agents["planner"] = {"type": "command", "argv": ["echo", json.dumps(proposal)]}
    orch.config.agents["llm"] = {"type": "command", "argv": ["echo", json.dumps(intent)]}
    orch.config.brain_order = ["router"]
    assistant = Assistant(orch, language="pl")

    proposal_reply = await assistant.handle("zaprojektuj i zbuduj cache w demo")
    assert proposal_reply.intent.action == "plan" and proposal_reply.report is None
    assert proposal_reply.text.startswith(
        "Plan dla demo: 1. Design (designer), 2. Build (builder)."
    )
    assert orch.store.get(assistant.pending_plan).status == "planned"  # nothing ran yet

    response = await assistant.handle("Dia, tak!")
    assert response.intent.action == "confirm" and assistant.pending_plan is None
    assert response.report.task.status == "done"
    assert [s["agent"] for s in response.report.task.details["steps"]] == ["designer", "builder"]

    await assistant.handle("zaprojektuj i zbuduj cache w demo")
    cancelled = await assistant.handle("nie")
    assert cancelled.intent.action == "cancel" and cancelled.text == "Dobrze, nie uruchamiam planu."
    assert assistant.pending_plan is None
