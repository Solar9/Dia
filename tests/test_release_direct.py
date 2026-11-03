"""Direct tests of release.py's main paths (DIA-36): the changelog, the two publishers, and
the checks that stop a build before it starts. Real git, fake agents and uploaders."""

import stat
import subprocess
from pathlib import Path

import pytest

from dia.core.config import parse_config
from dia.core.orchestrator import Orchestrator, TaskActionError
from dia.core.store import TaskRecord
from dia.release import release as release_module
from dia.release.release import Releases


def git(path: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=path, check=True, capture_output=True, text=True,
    )  # fmt: skip
    return done.stdout.strip()


def commit(path: Path, subject: str) -> None:
    (path / f"{abs(hash(subject))}.txt").write_text(subject)
    git(path, "add", ".")
    git(path, "commit", "-qm", subject)


def make(tmp_path: Path, repo: Path, builds: dict | None = None, **extra) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a", "language": "en"},
        "agents": {"a": {"type": "command", "argv": ["echo", "- Players can save again"]}},
        "projects": {"demo": {"path": str(repo)}},
        **({"builds": builds} if builds else {}),
        **extra,
    }
    return Orchestrator(parse_config(raw), use_memory=False)


@pytest.fixture
def releases(tmp_path: Path, repo: Path) -> Releases:
    return Releases(make(tmp_path, repo))


# ---- the changelog --------------------------------------------------------------------------


async def test_the_changelog_lists_commits_since_the_previous_tag(releases, repo) -> None:
    git(repo, "tag", "v1")
    commit(repo, "Fix saving")
    commit(repo, "dia: step 2")  # Dia's own step commits are not news
    commit(repo, "Add co-op")
    text = await releases.changelog("demo")
    assert text.startswith("Since v1:") and "- Add co-op" in text and "- Fix saving" in text
    assert "dia: step" not in text


async def test_the_changelog_of_an_untagged_repository_is_its_recent_history(releases) -> None:
    assert "- init" in await releases.changelog("demo")


async def test_the_previous_tag_skips_the_tag_on_the_commit_itself(releases, repo) -> None:
    git(repo, "tag", "v1")
    commit(repo, "second")
    git(repo, "tag", "v2")
    assert await releases._previous_tag(repo, "HEAD") == "v1"  # not v2, which is HEAD's own
    assert await releases._previous_tag(repo, "v1") is None  # nothing before the first


async def test_no_changes_is_said_plainly(releases, repo) -> None:
    git(repo, "tag", "v1")
    assert await releases.changelog("demo", since="v1") == "(no changes)"


async def test_an_agent_can_word_the_changelog_for_players(releases, repo) -> None:
    git(repo, "tag", "v1")
    commit(repo, "Fix saving")
    text = await releases.changelog("demo", since="v1", write=True, version="1.1")
    assert text == "- Players can save again"


async def test_a_failing_changelog_agent_falls_back_to_the_plain_list(tmp_path, repo) -> None:
    orch = make(tmp_path, repo)
    orch.config.agents["a"] = {"type": "command", "argv": ["sh", "-c", "exit 3"]}
    git(repo, "tag", "v1")
    commit(repo, "Fix saving")
    text = await Releases(orch).changelog("demo", since="v1", write=True)
    assert text == "- Fix saving"


# ---- builds that cannot start ---------------------------------------------------------------


async def test_a_project_nobody_can_build_is_refused(releases) -> None:
    with pytest.raises(TaskActionError, match="doesn't know how to build"):
        await releases.build("demo")


# ---- itch.io --------------------------------------------------------------------------------


def finished_build(orch: Orchestrator, folder: Path, **details) -> TaskRecord:
    exe = folder / "game.x86_64"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("binary")
    task = TaskRecord(
        id="b1",
        project="demo",
        agent="-",
        mode="build",
        prompt="build 1.0",
        status="done",
        details={
            "version": "1.0",
            "builds": [{"preset": "Linux/X11", "files": [str(exe)]}],
            **details,
        },
    )
    orch.store.save(task)
    return task


async def test_publishing_needs_a_finished_build(releases) -> None:
    with pytest.raises(TaskActionError, match="not a finished build"):
        await releases.publish_itch("nope")
    with pytest.raises(TaskActionError, match="not a finished build"):
        await releases.publish_steam("nope")


async def test_itch_needs_a_target_and_butler(tmp_path, repo, monkeypatch) -> None:
    orch = make(tmp_path, repo)
    finished_build(orch, tmp_path / "out")
    with pytest.raises(TaskActionError, match="itch = "):
        await Releases(orch).publish_itch("b1")
    orch.config.raw["builds"] = {"itch": "me/game"}
    monkeypatch.setattr("dia.agents.base.find_executable", lambda name: None)
    with pytest.raises(TaskActionError, match="butler is not installed"):
        await Releases(orch).publish_itch("b1")


def fake_tool(path: Path, output: str, code: int = 0) -> Path:
    path.write_text(f'#!/bin/sh\necho "$@" >> {path}.log\necho "{output}"\nexit {code}\n')
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


async def test_itch_pushes_each_build_on_its_channel(tmp_path, repo, monkeypatch) -> None:
    orch = make(tmp_path, repo, builds={"itch": "me/game", "itch_channels": {"Linux/X11": "linux"}})
    finished_build(orch, tmp_path / "out")
    butler = fake_tool(tmp_path / "butler", "pushed")
    monkeypatch.setattr("dia.agents.base.find_executable", lambda name: str(butler))
    pushed = await Releases(orch).publish_itch("b1")
    assert pushed == ["me/game:linux"]
    log = (tmp_path / "butler.log").read_text()
    assert f"push {tmp_path / 'out'} me/game:linux --userversion 1.0" in log
    task = orch.store.get("b1")
    assert task.details["published"]["itch"] == ["me/game:linux"]
    assert any(e["action"] == "build.publish" for e in orch.store.audit())


async def test_a_failing_butler_is_reported_with_its_output(tmp_path, repo, monkeypatch) -> None:
    orch = make(tmp_path, repo, builds={"itch": "me/game"})
    finished_build(orch, tmp_path / "out")
    butler = fake_tool(tmp_path / "butler", "login required", code=1)
    monkeypatch.setattr("dia.agents.base.find_executable", lambda name: str(butler))
    with pytest.raises(TaskActionError, match="butler push linux-x11 failed: login required"):
        await Releases(orch).publish_itch("b1")


# ---- Steam ----------------------------------------------------------------------------------


STEAM = {"app_id": 480, "depots": {"Linux/X11": 481}, "username": "builder"}


async def test_steam_refuses_incomplete_settings_the_default_branch_and_a_missing_tool(
    tmp_path, repo, monkeypatch
) -> None:
    orch = make(tmp_path, repo)
    finished_build(orch, tmp_path / "out")
    with pytest.raises(TaskActionError, match=r"\[builds.steam\]"):
        await Releases(orch).publish_steam("b1")
    orch.config.raw["builds"] = {"steam": {**STEAM, "branch": "default"}}
    with pytest.raises(TaskActionError, match="default branch"):
        await Releases(orch).publish_steam("b1")
    orch.config.raw["builds"] = {"steam": {**STEAM, "branch": "beta"}}
    monkeypatch.setattr("dia.agents.base.find_executable", lambda name: None)
    with pytest.raises(TaskActionError, match="steamcmd is not installed"):
        await Releases(orch).publish_steam("b1")
    steamcmd = fake_tool(tmp_path / "steamcmd", "ok")
    monkeypatch.setattr("dia.agents.base.find_executable", lambda name: str(steamcmd))
    orch.config.raw["builds"] = {"steam": {**STEAM, "depots": {"Windows": 482}, "branch": "beta"}}
    with pytest.raises(TaskActionError, match="none of the built presets has a depot"):
        await Releases(orch).publish_steam("b1")


async def test_steam_uploads_to_a_named_branch_and_records_the_build(
    tmp_path, repo, monkeypatch
) -> None:
    orch = make(tmp_path, repo, builds={"steam": {**STEAM, "branch": "beta"}})
    finished_build(orch, tmp_path / "out")
    steamcmd = fake_tool(tmp_path / "steamcmd", "Success. BuildID 4242")
    monkeypatch.setattr("dia.agents.base.find_executable", lambda name: str(steamcmd))
    result = await Releases(orch).publish_steam("b1")
    assert result == "steam:480 (beta), build 4242"
    script = (orch.config.data_dir / "steam" / "b1" / "app_build_480.vdf").read_text()
    assert '"setlive" "beta"' in script or "beta" in script
    assert orch.store.get("b1").details["published"]["steam"] == {
        "app_id": 480, "branch": "beta", "build_id": "4242",
    }  # fmt: skip
    failing = fake_tool(tmp_path / "steamcmd", "ERROR! Failed to log in")
    monkeypatch.setattr("dia.agents.base.find_executable", lambda name: str(failing))
    with pytest.raises(TaskActionError, match="steamcmd failed"):
        await Releases(orch).publish_steam("b1")


def test_slugs_are_safe_folder_names() -> None:
    assert release_module._slug("Linux/X11 (64-bit)") == "Linux-X11-64-bit"
    assert release_module._slug("v1.0") == "v1.0" and release_module._slug("///") == "build"
