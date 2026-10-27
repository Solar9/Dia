from pathlib import Path

import pytest

from dia.config import parse_config
from dia.orchestrator import Orchestrator, TaskActionError
from dia.review import APPROVED, CHANGES_REQUESTED, UNCLEAR, parse_verdict

# Writes v1 for the task; when asked to address a review, adds the requested line.
AUTHOR = [
    "sh",
    "-c",
    'case "$0" in *"requested changes"*) echo fixed >> f.txt; echo "done: fixed";; '
    '*) echo v1 > f.txt; echo "wrote v1";; esac',
    "{prompt}",
]
# Approves once the diff contains "fixed", otherwise asks for it.
REVIEWER = [
    "sh",
    "-c",
    'case "$0" in *+fixed*) echo "VERDICT: APPROVE"; echo "Looks good.";; '
    '*) echo "VERDICT: CHANGES_REQUESTED"; echo "- f.txt: please add fixed";; esac',
    "{prompt}",
]


def setup(tmp_path: Path, repo: Path, review: dict | None = None, test: str | None = None):
    project = {"path": str(repo)}
    if test:
        project["test_command"] = test
    return Orchestrator(
        parse_config(
            {
                "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "author"},
                "agents": {
                    "author": {"type": "command", "argv": AUTHOR},
                    "critic": {"type": "command", "argv": REVIEWER},
                },
                "projects": {"demo": project},
                "review": review or {},
            }
        )
    )


def test_parse_verdict() -> None:
    assert parse_verdict("VERDICT: APPROVE\nok") == APPROVED
    assert parse_verdict("**Verdict:** changes requested") == CHANGES_REQUESTED
    assert parse_verdict("VERDICT: REQUEST_CHANGES") == CHANGES_REQUESTED
    assert parse_verdict("lgtm") == UNCLEAR


async def test_review_fix_loop_until_approved(tmp_path: Path, repo: Path) -> None:
    orch = setup(tmp_path, repo, test="grep -q fixed f.txt")
    report = await orch.run_task("demo", "create f.txt", review=True)
    task = report.task

    verdicts = [(r["reviewer"], r["verdict"], r["round"]) for r in task.details["reviews"]]
    assert verdicts == [("critic", CHANGES_REQUESTED, 0), ("critic", APPROVED, 1)]
    assert task.details["review"] == APPROVED
    # Tests failed on v1, passed after the fix, and the task followed them.
    assert task.tests_ok is True and task.status == "done"
    assert task.summary == "done: fixed"
    worktree = Path(task.details["worktree"])
    assert (worktree / "f.txt").read_text() == "v1\nfixed\n"
    assert orch.store.get(task.id).details["review"] == APPROVED


async def test_review_only_without_fix_rounds(tmp_path: Path, repo: Path) -> None:
    orch = setup(tmp_path, repo, review={"fix_rounds": 0})
    task = (await orch.run_task("demo", "create f.txt")).task
    assert "reviews" not in task.details  # auto review is off by default

    report = await orch.review_task(task.id)
    assert [r["verdict"] for r in report.task.details["reviews"]] == [CHANGES_REQUESTED]
    assert (Path(task.details["worktree"]) / "f.txt").read_text() == "v1\n"


async def test_auto_review_from_config(tmp_path: Path, repo: Path) -> None:
    orch = setup(tmp_path, repo, review={"auto": True, "reviewer": "critic"})
    task = (await orch.run_task("demo", "create f.txt")).task
    assert task.details["review"] == APPROVED


async def test_reviewer_must_exist(tmp_path: Path, repo: Path) -> None:
    orch = setup(tmp_path, repo)
    del orch.config.agents["critic"]
    task = (await orch.run_task("demo", "create f.txt")).task
    with pytest.raises(TaskActionError, match="second agent"):
        await orch.review_task(task.id)
