import subprocess
from pathlib import Path

import pytest

from dia.agents import Mode
from dia.config import parse_config
from dia.orchestrator import Orchestrator, TaskActionError


def make(tmp_path: Path, repo: Path, agent_argv: list[str], test_command: str | None = None):
    project = {"path": str(repo)}
    if test_command:
        project["test_command"] = test_command
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "fake"},
            "agents": {"fake": {"type": "command", "argv": agent_argv}},
            "projects": {"demo": project},
        }
    )
    return Orchestrator(config)


def branches(repo: Path) -> str:
    return subprocess.run(
        ["git", "branch", "--list", "dia/*"], cwd=repo, capture_output=True, text=True
    ).stdout


async def test_edit_task_commits_on_its_own_branch(tmp_path: Path, repo: Path) -> None:
    agent = ["sh", "-c", "echo feature > feature.txt; echo added it"]
    orch = make(tmp_path, repo, agent, test_command="test -f feature.txt")
    report = await orch.run_task("demo", "add a feature")
    task = report.task

    assert task.status == "done", task.error
    assert task.summary == "added it"
    assert task.commit_sha and task.branch == f"dia/{task.id}"
    assert task.tests_ok is True
    assert "feature.txt" in report.diff_stat
    # The user's checkout is untouched; the change lives only on the task branch.
    assert not (repo / "feature.txt").exists()
    assert task.branch in branches(repo)
    assert orch.store.get(task.id).commit_sha == task.commit_sha


async def test_failing_tests_mark_task_failed(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "echo x > x.txt"], "exit 3")
    task = (await orch.run_task("demo", "break things")).task
    assert task.status == "failed" and task.tests_ok is False


async def test_read_only_task_leaves_no_branch(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "cat README.md"])
    task = (await orch.run_task("demo", "what is here?", mode=Mode.READ_ONLY)).task
    assert task.status == "done" and task.summary == "hello"
    assert task.commit_sha is None and branches(repo) == ""


async def test_uncommitted_changes_are_reported(tmp_path: Path, repo: Path) -> None:
    (repo / "README.md").write_text("local edit\n")
    report = await make(tmp_path, repo, ["cat", "README.md"]).run_task(
        "demo", "read", mode=Mode.READ_ONLY
    )
    assert report.task.summary == "hello"  # the agent saw the committed version
    assert "README.md" in report.warnings[0]


async def test_non_git_project_fails_cleanly(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    task = (await make(tmp_path, plain, ["true"]).run_task("demo", "x")).task
    assert task.status == "failed" and "not a git repository" in task.error


def git_out(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True).stdout.strip()


async def test_merge_brings_the_branch_in_and_cleans_up(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "echo new > new.txt"])
    started = []

    async def on_start(task):
        started.append(task.id)

    task = (await orch.run_task("demo", "add new.txt", on_start=on_start)).task
    assert started == [task.id]
    assert "new.txt" in await orch.task_diff(task.id)

    sha = await orch.merge_task(task.id)
    assert (repo / "new.txt").read_text() == "new\n"
    assert git_out(repo, "rev-parse", "HEAD") == sha
    assert branches(repo) == "" and not Path(task.details["worktree"]).exists()
    assert orch.store.get(task.id).status == "merged"
    with pytest.raises(TaskActionError, match="already merged"):
        await orch.merge_task(task.id)


async def test_merge_refuses_when_checkout_is_elsewhere(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "echo new > new.txt"])
    task = (await orch.run_task("demo", "add new.txt")).task
    git_out(repo, "checkout", "-q", "-b", "other")
    with pytest.raises(TaskActionError, match="check out 'main'"):
        await orch.merge_task(task.id)
    assert orch.store.get(task.id).status == "done"


async def test_conflicting_merge_is_aborted(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "echo agent > README.md"])
    task = (await orch.run_task("demo", "rewrite readme")).task
    (repo / "README.md").write_text("mine\n")
    git_out(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "mine")
    with pytest.raises(TaskActionError, match="aborted"):
        await orch.merge_task(task.id)
    assert (repo / "README.md").read_text() == "mine\n"
    assert git_out(repo, "status", "--porcelain") == ""


async def test_discard_removes_branch(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "echo x > x.txt"], "exit 1")
    task = (await orch.run_task("demo", "x")).task
    assert task.status == "failed" and task.branch in branches(repo)
    with pytest.raises(TaskActionError, match="only 'done'"):
        await orch.merge_task(task.id)
    await orch.discard_task(task.id)
    assert branches(repo) == "" and orch.store.get(task.id).status == "discarded"


async def test_parallel_tasks_are_limited(tmp_path: Path, repo: Path) -> None:
    import asyncio

    orch = make(tmp_path, repo, ["sh", "-c", "sleep 0.3; echo done"])
    orch._slots = asyncio.Semaphore(1)
    statuses = []

    async def on_start(task):
        statuses.append(task.status)

    loop = asyncio.get_running_loop()
    started_at = loop.time()
    reports = await asyncio.gather(
        *(orch.run_task("demo", f"t{i}", mode=Mode.READ_ONLY, on_start=on_start) for i in range(2))
    )
    assert statuses == ["queued", "queued"]
    assert all(r.task.status == "done" for r in reports)
    assert loop.time() - started_at >= 0.6  # one after the other, not side by side


async def test_work_committed_by_the_agent_itself_is_kept(tmp_path: Path, repo: Path) -> None:
    agent = [
        "sh",
        "-c",
        "echo x > x.txt && git add x.txt && "
        "git -c user.name=a -c user.email=a@a commit -qm 'agent commit' && echo committed",
    ]
    task = (await make(tmp_path, repo, agent).run_task("demo", "commit yourself")).task
    assert task.status == "done" and task.commit_sha
    assert task.branch in branches(repo)
    assert git_out(repo, "log", "-1", "--format=%s", task.branch) == "agent commit"


async def test_edit_prompts_say_dia_commits_and_tests_are_logged(
    tmp_path: Path, repo: Path
) -> None:
    agent = ["sh", "-c", 'echo x > x.txt; echo "$0"', "{prompt}"]
    orch = make(tmp_path, repo, agent, "echo all good")
    task = (await orch.run_task("demo", "add x")).task
    assert "Do not commit: when you finish, Dia commits your changes" in task.summary
    assert orch.test_log_path(task.id).read_text() == "all good\n"

    read = (await orch.run_task("demo", "look", mode=Mode.READ_ONLY)).task
    assert "Do not commit" not in read.summary  # read-only tasks don't get the note


async def test_merge_works_without_a_git_identity(tmp_path: Path, repo: Path, monkeypatch) -> None:
    # A fresh machine or CI runner: git doesn't know who you are.
    for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    orch = make(tmp_path, repo, ["sh", "-c", "echo new > new.txt"])
    task = (await orch.run_task("demo", "add new.txt")).task
    await orch.merge_task(task.id)
    assert git_out(repo, "log", "-1", "--format=%an <%ae>") == "Dia <dia@localhost>"


async def test_rollback_prepares_a_revert_to_merge(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "echo feature > feature.txt; echo added"])
    task = (await orch.run_task("demo", "add a feature")).task
    with pytest.raises(TaskActionError, match="not merged"):
        await orch.rollback_task(task.id)
    await orch.merge_task(task.id)
    assert (repo / "feature.txt").exists()

    revert = await orch.rollback_task(task.id)
    assert revert.status == "done", revert.error
    assert revert.details["reverts"] == task.id
    assert orch.store.get(task.id).details["reverted_by"] == revert.id
    assert (repo / "feature.txt").exists()  # nothing changes before you merge it
    await orch.merge_task(revert.id)
    assert not (repo / "feature.txt").exists()
