import json
import subprocess
from pathlib import Path

import pytest

from dia.ci import CIWatcher
from dia.config import parse_config
from dia.forges.builtin import GitLabForge
from dia.orchestrator import Orchestrator, TaskActionError

# Writes v1; when asked to fix CI, writes the fix.
AUTHOR = [
    "sh",
    "-c",
    'case "$0" in *"CI failed"*) echo ok > fix.txt; echo "fixed the test";; '
    '*) echo v1 > f.txt; echo "wrote v1";; esac',
    "{prompt}",
]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def fake_gh(tmp_path: Path) -> tuple[Path, Path]:
    """A gh whose `pr checks` answer comes from checks.json."""
    checks = tmp_path / "checks.json"
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'case "$1 $2" in\n'
        '  "pr create") cat > /dev/null; echo https://github.com/me/demo/pull/1;;\n'
        f'  "pr checks") cat {checks}; exit 1;;\n'
        '  "run view") echo "FAILED test_save: expected 2, got 3";;\n'
        "esac\n"
    )
    gh.chmod(0o755)
    return gh, checks


@pytest.fixture
def setup(tmp_path: Path, repo: Path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    gh, checks = fake_gh(tmp_path)

    def make(**ci) -> Orchestrator:
        return Orchestrator(
            parse_config(
                {
                    "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "author"},
                    "agents": {"author": {"type": "command", "argv": AUTHOR}},
                    "projects": {
                        "demo": {
                            "path": str(repo),
                            "forge": "github",
                            "forge_options": {"command": str(gh)},
                        }
                    },
                    "ci": ci,
                }
            )
        )

    def set_checks(*items: tuple[str, str]) -> None:
        checks.write_text(
            json.dumps(
                [
                    {
                        "name": n,
                        "bucket": b,
                        "link": f"https://github.com/me/demo/actions/runs/42/job/{i}",
                    }
                    for i, (n, b) in enumerate(items)
                ]
            )
        )

    return make, set_checks, bare


async def published(orch: Orchestrator) -> str:
    task = (await orch.run_task("demo", "write f.txt")).task
    await orch.publish_task(task.id)
    return task.id


async def test_watcher_reports_and_fix_is_pushed(setup) -> None:
    make, set_checks, bare = setup
    orch = make()
    events = []

    async def listener(event):
        events.append((event.kind, event.message))

    orch.listeners.append(listener)
    task_id = await published(orch)
    watcher = CIWatcher(orch)

    set_checks(("lint", "pass"), ("tests", "pending"))
    await watcher.poll()
    assert events == [] and orch.store.get(task_id).details["ci"]["state"] == "pending"

    set_checks(("lint", "pass"), ("tests", "fail"))
    await watcher.poll()
    assert events == [("ci", "failed")]
    ci = orch.store.get(task_id).details["ci"]
    assert ci["failed"][0]["name"] == "tests"
    await watcher.poll()  # a finished result is reported once
    assert len(events) == 1

    await orch.fix_ci(task_id)
    task = orch.store.get(task_id)
    assert task.details["ci"] == {"state": "pending"} and task.details["ci_fixes"] == 1
    assert task.summary == "fixed the test"
    assert git(bare, "show", f"{task.branch}:fix.txt") == "ok"  # pushed to the PR branch
    assert not Path(task.details["worktree"]).exists()

    set_checks(("lint", "pass"), ("tests", "pass"))
    await watcher.poll()
    assert events[-1] == ("ci", "success")


async def test_autofix_once(setup) -> None:
    make, set_checks, bare = setup
    orch = make(autofix=True, fix_rounds=1)
    events = []

    async def listener(event):
        events.append(event.message)

    orch.listeners.append(listener)
    task_id = await published(orch)
    set_checks(("tests", "fail"))
    await CIWatcher(orch).poll()
    assert events == ["failed; asking the author to fix it", "fix pushed"]
    await CIWatcher(orch).poll()  # still failing: no rounds left, so only reported
    assert events[-1] == "failed"
    assert orch.store.get(task_id).details["ci_fixes"] == 1


async def test_fix_ci_requires_failure(setup) -> None:
    make, set_checks, _ = setup
    orch = make()
    task_id = await published(orch)
    with pytest.raises(TaskActionError, match="has not failed"):
        await orch.fix_ci(task_id)


async def test_gitlab_pipeline_parsing(tmp_path: Path) -> None:
    pipeline = {
        "status": "failed",
        "web_url": "https://gitlab.com/me/nova/-/pipelines/9",
        "jobs": [
            {"id": 1, "name": "export", "status": "success"},
            {"id": 2, "name": "gut-tests", "status": "failed", "web_url": "u2"},
            {"id": 3, "name": "lint", "status": "failed", "allow_failure": True},
        ],
    }
    glab = tmp_path / "glab"
    glab.write_text(f"#!/bin/sh\necho 'Getting pipeline...'\necho '{json.dumps(pipeline)}'\n")
    glab.chmod(0o755)
    status = await GitLabForge({"command": str(glab)}).ci_status(tmp_path, "dia/x")
    assert status.state == "failed" and status.url.endswith("/pipelines/9")
    assert status.failed == [{"name": "gut-tests", "id": 2, "url": "u2"}]
