from pathlib import Path

import pytest

from dia import swarm
from dia.config import parse_config
from dia.orchestrator import Orchestrator, TaskActionError

# One fake agent plays every part, by what it is asked:
# - a role (hypotheses): two agents agree the cause is in physics.gd, one blames input.gd;
# - a check: it writes a test that fails for physics.gd (confirmed), passes for input.gd;
# - the fix: it fixes physics.gd.
AGENT = r"""
case "$0" in
  *"Your role"*)
    case "$0" in
      *"error output"*|*"code paths"*) where="physics.gd:move" ;;
      *) where="input.gd:dash" ;;
    esac
    h="{\"cause\": \"speed not clamped in $where\", \"where\": \"$where\""
    echo "{\"hypotheses\": [$h, \"test\": \"dash into a wall\"}]}" ;;
  *"Suspected cause"*)
    mkdir -p tests
    case "$0" in
      *physics.gd*) echo "grep -q clamp physics.gd" > tests/wall.sh ;;
      *) echo "true" > tests/dash.sh ;;
    esac
    echo "wrote a test" ;;
  *"Fix this bug"*)
    echo "clamp" > physics.gd; echo fixed ;;
esac
"""


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    (repo / "physics.gd").write_text("move\n")
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", AGENT, "{prompt}"]}},
        "projects": {
            "nova": {
                "path": str(repo),
                "test_command": "for t in tests/*.sh; do sh $t || exit 1; done",
            }
        },
    }
    return Orchestrator(parse_config(raw), use_memory=False)


def test_merging_hypotheses() -> None:
    found = [
        ("logs", "a", {"cause": "x", "where": "physics.gd:move", "test": ""}),
        ("code", "b", {"cause": "y", "where": "physics.gd (line 4)", "test": ""}),
        ("history", "a", {"cause": "z", "where": "input.gd:dash", "test": ""}),
    ]
    merged = swarm.merge(found)
    assert merged[0]["proposed_by"] == ["a (logs)", "b (code)"] and len(merged) == 2


async def test_hypotheses_are_settled_by_tests(tmp_path, repo) -> None:
    import subprocess

    dia = make(tmp_path, repo)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "game"],
        cwd=repo,
        check=True,
    )
    task = await swarm.debug(dia, "nova", "the player goes through walls after a dash")
    assert task.mode == "debug" and task.status == "done"
    results = {h["where"]: h["result"] for h in task.details["hypotheses"]}
    assert results == {"physics.gd:move": "confirmed", "input.gd:dash": "ruled out"}
    assert "Confirmed by a failing test: speed not clamped in physics.gd:move" in task.summary

    report = await swarm.fix(dia, task.id)
    # The fix starts from the test's branch, so the test that proved it now passes.
    assert report.task.status == "done" and report.task.tests_ok is True
    assert report.task.details["debug_fix"] == task.id


async def test_nothing_confirmed_nothing_to_fix(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    with pytest.raises(TaskActionError):
        await swarm.fix(dia, "nope")
