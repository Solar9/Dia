import json
import subprocess
from pathlib import Path

import pytest

from dia.ci import CIWatcher
from dia.config import parse_config
from dia.forges.builtin import GitLabForge
from dia.orchestrator import Orchestrator, TaskActionError

# Writes v1; asked to address comments, it records the prompt it got.
AUTHOR = [
    "sh",
    "-c",
    'case "$0" in *"Reviewers left"*) printf "%s" "$0" > addressed.txt; echo "renamed it";; '
    '*) echo v1 > f.txt; echo "wrote v1";; esac',
    "{prompt}",
]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def setup(tmp_path: Path, repo: Path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    pr = tmp_path / "pr.json"
    inline = tmp_path / "inline.json"
    pr.write_text(json.dumps({"number": 5, "reviews": [], "comments": []}))
    inline.write_text("[]")
    gh = tmp_path / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'case "$1 $2" in\n'
        '  "pr create") cat > /dev/null; echo https://github.com/me/demo/pull/5;;\n'
        f'  "pr view") cat {pr};;\n'
        f'  "api repos/{{owner}}/{{repo}}/pulls/5/comments") cat {inline};;\n'
        '  "pr checks") echo "[]"; exit 1;;\n'
        '  *) echo "unexpected: $*" >&2; exit 2;;\n'
        "esac\n"
    )
    gh.chmod(0o755)

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

    return make, pr, inline, bare


async def test_comments_are_reported_once_and_addressed(setup) -> None:
    make, pr, inline, bare = setup
    orch = make()
    events = []

    async def listener(event):
        events.append((event.kind, event.message))

    orch.listeners.append(listener)
    task = (await orch.run_task("demo", "write f.txt")).task
    await orch.publish_task(task.id)

    pr.write_text(
        json.dumps(
            {
                "number": 5,
                "reviews": [
                    {
                        "id": 1,
                        "author": {"login": "ana"},
                        "body": "Please rename f.txt",
                        "state": "COMMENTED",
                    },
                    {"id": 2, "author": {"login": "ana"}, "body": "", "state": "APPROVED"},
                ],
                "comments": [
                    {"id": 3, "author": {"login": "ci-bot"}, "body": "coverage 80%", "url": "u"}
                ],
            }
        )
    )
    inline.write_text(
        json.dumps(
            [
                {
                    "id": 4,
                    "user": {"login": "olek"},
                    "body": "Typo here",
                    "path": "f.txt",
                    "line": 1,
                    "html_url": "https://github.com/me/demo/pull/5#r4",
                },
                {
                    "id": 5,
                    "user": {"login": "renovate[bot]"},
                    "body": "bump",
                    "path": "x",
                    "line": 2,
                },
            ]
        )
    )
    watcher = CIWatcher(orch)
    await watcher.poll()
    assert events == [("review", "2 new comment(s) from ana, olek")]  # bots ignored
    pending = orch.store.get(task.id).details["comments_pending"]
    assert [(c["author"], c["path"]) for c in pending] == [("ana", None), ("olek", "f.txt")]

    await watcher.poll()  # nothing new: no second notification
    assert len(events) == 1

    await orch.address_comments(task.id)
    saved = orch.store.get(task.id)
    assert saved.details["comments_pending"] == []
    assert saved.details["comments_addressed"] == ["review-1", "inline-4"]
    assert saved.summary == "renamed it"
    prompt = git(bare, "show", f"{saved.branch}:addressed.txt")
    assert "- ana:\nPlease rename f.txt" in prompt and "- olek on f.txt:1:\nTypo here" in prompt
    assert "Do not commit" in prompt
    with pytest.raises(TaskActionError, match="no pending review comments"):
        await orch.address_comments(task.id)


async def test_comments_can_be_addressed_automatically(setup) -> None:
    make, pr, inline, bare = setup
    orch = make(autofix_comments=True)
    events = []

    async def listener(event):
        events.append(event.message)

    orch.listeners.append(listener)
    task = (await orch.run_task("demo", "write f.txt")).task
    await orch.publish_task(task.id)
    pr.write_text(
        json.dumps(
            {
                "number": 5,
                "reviews": [],
                "comments": [
                    {"id": 9, "author": {"login": "ana"}, "body": "Add a header", "url": "u"}
                ],
            }
        )
    )
    await CIWatcher(orch).poll()
    assert events == ["1 new comment(s) from ana", "comments addressed"]
    assert git(bare, "show", f"{task.branch}:addressed.txt")


async def test_gitlab_notes(tmp_path: Path) -> None:
    notes = [
        {"id": 1, "body": "added 1 commit", "system": True, "author": {"username": "me"}},
        {
            "id": 2,
            "body": "Use a constant",
            "system": False,
            "author": {"username": "kasia"},
            "position": {"new_path": "player.gd", "new_line": 12},
        },
        {"id": 3, "body": "LGTM otherwise", "system": False, "author": {"username": "kasia"}},
    ]
    glab = tmp_path / "glab"
    glab.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  mr) echo '{\"iid\": 7}';;\n"
        f"  api) echo '{json.dumps(notes)}';;\n"
        "esac\n"
    )
    glab.chmod(0o755)
    comments = await GitLabForge({"command": str(glab)}).review_comments(tmp_path, "dia/x")
    assert [(c.id, c.author, c.path, c.line) for c in comments] == [
        ("note-2", "kasia", "player.gd", 12),
        ("note-3", "kasia", None, None),
    ]
