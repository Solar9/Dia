import subprocess
from pathlib import Path

import pytest

from dia.config import parse_config
from dia.forges import detect
from dia.forges.builtin import GitLabForge
from dia.orchestrator import Orchestrator, TaskActionError


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def remote(tmp_path: Path, repo: Path) -> Path:
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "origin", "main")
    return bare


def setup(tmp_path: Path, repo: Path, **project) -> Orchestrator:
    agent = ["sh", "-c", "echo feature > feature.txt; echo added"]
    return Orchestrator(
        parse_config(
            {
                "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a"},
                "agents": {"a": {"type": "command", "argv": agent}},
                "projects": {"demo": {"path": str(repo), **project}},
            }
        )
    )


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("git@github.com:me/dia.git", "github"),
        ("https://github.com/me/dia", "github"),
        ("git@gitlab.com:me/nova.git", "gitlab"),
        ("https://user@gitlab.example.org/team/nova.git", "gitlab"),
        ("ssh://git@codeberg.org/me/x.git", "git"),
        ("/srv/git/x.git", "git"),
    ],
)
async def test_detect_forge_from_remote(repo: Path, url: str, kind: str) -> None:
    git(repo, "remote", "add", "origin", url)
    assert await detect(repo) == kind


async def test_publish_pushes_branch_to_plain_git(tmp_path: Path, repo: Path, remote: Path) -> None:
    orch = setup(tmp_path, repo)
    task = (await orch.run_task("demo", "add feature")).task
    publication = await orch.publish_task(task.id)

    assert publication.url is None and "pushed" in publication.message
    assert git(remote, "branch", "--list", task.branch).strip("* ") == task.branch
    saved = orch.store.get(task.id)
    assert saved.status == "published" and saved.details["published"]["forge"] == "git"
    assert saved.details["ci"] == {"state": "none"}  # plain git has no CI to wait for
    assert not Path(task.details["worktree"]).exists()
    with pytest.raises(TaskActionError, match="already published"):
        await orch.publish_task(task.id)


async def test_github_pull_request_via_gh(tmp_path: Path, repo: Path, remote: Path) -> None:
    log = tmp_path / "gh.log"
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        f'#!/bin/sh\necho "$@" > {log}\ncat >> {log}\necho "https://github.com/me/demo/pull/7"\n'
    )
    fake_gh.chmod(0o755)
    orch = setup(
        tmp_path, repo, forge="github", forge_options={"command": str(fake_gh), "draft": True}
    )
    task = (await orch.run_task("demo", "Add feature file")).task
    publication = await orch.publish_task(task.id)

    assert publication.url == "https://github.com/me/demo/pull/7"
    call = log.read_text()
    assert f"pr create --head {task.branch} --base main --title Add feature file" in call
    assert "--draft" in call and "**Task:** Add feature file" in call  # body on stdin
    assert git(remote, "branch", "--list", task.branch)


async def test_gitlab_merge_request_via_glab(tmp_path: Path, repo: Path, remote: Path) -> None:
    log = tmp_path / "glab.log"
    fake = tmp_path / "glab"
    fake.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > {log}\n'
        'echo "!3 Add feature (dia/x)"\necho " https://gitlab.com/me/demo/-/merge_requests/3"\n'
    )
    fake.chmod(0o755)
    orch = setup(tmp_path, repo, forge="gitlab", forge_options={"command": str(fake)})
    task = (await orch.run_task("demo", "Add feature")).task
    publication = await orch.publish_task(task.id)
    assert publication.url == "https://gitlab.com/me/demo/-/merge_requests/3"
    args = log.read_text().splitlines()
    assert args[:3] == ["mr", "create", "--source-branch"] and "--remove-source-branch" in args


def test_gitlab_push_options_without_glab() -> None:
    forge = GitLabForge({"draft": True})
    options = forge.push_options("main", "Add gamepad", "line one\nline two")
    assert options[0] == "merge_request.create"
    assert "merge_request.target=main" in options
    assert "merge_request.title=Draft: Add gamepad" in options
    assert "merge_request.description=line one line two" in options


async def test_publish_needs_a_remote(tmp_path: Path, repo: Path) -> None:
    orch = setup(tmp_path, repo)
    task = (await orch.run_task("demo", "add feature")).task
    with pytest.raises(TaskActionError, match="no remote 'origin'"):
        await orch.publish_task(task.id)
    assert orch.store.get(task.id).status == "done"
