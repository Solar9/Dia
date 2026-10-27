import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dia import goals
from dia.config import parse_config
from dia.orchestrator import Orchestrator

MILESTONES = {"milestones": [
    {"title": "Saving works", "done_when": "a save loads back"},
    {"title": "Steam page", "done_when": "the page is live"},
]}  # fmt: skip
REVIEW = {
    "progress": "Saving is done; the Steam page has not started.",
    "done": [1],
    "blockers": ["no capsule art"],
    "next": {"milestone": 2, "mission": "Prepare the Steam page texts"},
}
STEPS = {"steps": [{"id": "s1", "title": "Texts", "agent": "planner", "prompt": "write texts"}]}

# The planner answers by what it is asked; it records the review prompt.
PLANNER = f"""
case "$0" in
  *"break the goal"*) echo '{json.dumps(MILESTONES)}' ;;
  *"review progress"*) printf '%s' "$0" > "$SEEN"; echo '{json.dumps(REVIEW)}' ;;
  *) echo '{json.dumps(STEPS)}' ;;
esac
"""


def make(tmp_path: Path, repo: Path, monkeypatch) -> Orchestrator:
    monkeypatch.setenv("SEEN", str(tmp_path / "seen.txt"))
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "planner"},
        "agents": {"planner": {"type": "command", "argv": ["sh", "-c", PLANNER, "{prompt}"]}},
        "projects": {"uv": {"path": str(repo)}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_goal_milestones_review_and_next_mission(tmp_path, repo, monkeypatch) -> None:
    dia = make(tmp_path, repo, monkeypatch)
    goal = await goals.create(dia, "uv", "Starfall do Early Access", weeks=8)
    assert goal.status == "active" and goal.mode == "goal"
    assert [m["title"] for m in goal.details["milestones"]] == ["Saving works", "Steam page"]
    assert goal.details["deadline"]
    assert goals.due(dia) == []  # the first review comes in a week
    week_later = datetime.now(UTC) + timedelta(days=7, minutes=1)
    assert [g.id for g in goals.due(dia, week_later)] == [goal.id]

    # a failed task for the goal is a blocker the review sees
    failed = (await dia.run_task("uv", "save the inventory", details={"goal": goal.id})).task
    failed.status, failed.error = "failed", "tests failed"
    dia.store.save(failed)
    result = await goals.review(dia, goal.id)
    assert result["done"] == [1] and result["next"]["milestone"] == 2
    assert "failed: save the inventory" in (tmp_path / "seen.txt").read_text()
    assert dia.store.get(goal.id).details["milestones"][0]["status"] == "open"  # not yet

    mission = await goals.approve(dia, goal.id)
    assert mission.mode == "mission" and mission.status == "planned"  # you start it
    assert mission.details["goal"] == goal.id
    goal = dia.store.get(goal.id)
    assert goal.details["milestones"][0]["status"] == "done"
    assert goal.details["milestones"][1]["missions"] == [mission.id]
    assert goal.details["reviews"][-1]["status"] == "approved"
    with pytest.raises(ValueError, match="already decided"):
        await goals.approve(dia, goal.id)
    assert "[x] 1. Saving works" in goals.describe(goal)
