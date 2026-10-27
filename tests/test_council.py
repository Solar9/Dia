from pathlib import Path

import pytest

from dia.config import parse_config
from dia.council import convene
from dia.orchestrator import Orchestrator, TaskActionError


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    agents = {
        "claude": {"type": "command", "argv": ["echo", "Use ENet: reliable, simple."]},
        "codex": {"type": "command", "argv": ["echo", "Use WebRTC: works through NAT."]},
        # The moderator gets both answers in its prompt and echoes it.
        "judge": {"type": "command", "argv": ["sh", "-c", 'echo "SUMMARY: $0"', "{prompt}"]},
    }
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "judge", "language": "pl"},
            "agents": agents,
            "projects": {"nova": {"path": str(repo)}},
            "council": {"members": ["claude", "codex"]},
        }
    )
    return Orchestrator(config, use_memory=False)


async def test_council_collects_answers_and_a_verdict(tmp_path: Path, repo: Path) -> None:
    dia = make(tmp_path, repo)
    task = await convene(dia, "Which networking for 4-player co-op?", "nova")
    assert task.status == "done" and task.mode == "council"
    answers = {a["agent"]: a["answer"] for a in task.details["council"]}
    assert answers == {
        "claude": "Use ENet: reliable, simple.",
        "codex": "Use WebRTC: works through NAT.",
    }
    assert task.summary.startswith("SUMMARY:")
    assert "### claude" in task.summary and "Polish" in task.summary
    assert task.details["moderator"] == "judge"
    leftovers = list((tmp_path / "d" / "worktrees" / "nova").iterdir())
    assert leftovers == []  # the read-only worktree is gone
    assert dia.store.usage(1)["purposes"]["council"] == 3


async def test_council_needs_two_members(tmp_path: Path, repo: Path) -> None:
    dia = make(tmp_path, repo)
    with pytest.raises(TaskActionError):
        await convene(dia, "x", members=["claude"])
