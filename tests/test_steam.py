from pathlib import Path

import pytest

from dia.config import parse_config
from dia.orchestrator import Orchestrator, TaskActionError
from dia.release import Releases
from dia.store import TaskRecord


def make(tmp_path: Path, monkeypatch, steam: dict) -> tuple[Releases, TaskRecord, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "steamcmd.log"
    fake = bin_dir / "steamcmd"
    fake.write_text(f'#!/bin/sh\necho "$@" > {log}\ncat "$4" >> {log}\necho "BuildID 4242"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    linux = tmp_path / "builds" / "Linux"
    linux.mkdir(parents=True)
    (linux / "nova.x86_64").write_text("bin")
    dia = Orchestrator(
        parse_config({"dia": {"data_dir": str(tmp_path / "d")}, "builds": {"steam": steam}}),
        use_memory=False,
    )
    task = TaskRecord(
        id="b1",
        project="nova",
        agent="-",
        mode="build",
        prompt="build",
        status="done",
        details={
            "version": "v0.3",
            "builds": [{"preset": "Linux", "files": [str(linux / "nova.x86_64")], "mb": 0.1}],
        },
    )
    dia.store.save(task)
    return Releases(dia), task, log


STEAM = {"app_id": 480, "depots": {"Linux": 481}, "username": "builder", "branch": "beta"}


async def test_publish_to_steam(tmp_path, monkeypatch) -> None:
    releases, task, log = make(tmp_path, monkeypatch, STEAM)
    assert await releases.publish_steam(task.id) == "steam:480 (beta), build 4242"
    text = log.read_text()
    assert text.startswith("+login builder +run_app_build ")
    assert '"SetLive" "beta"' in text and '"481"' in text and "builds/Linux" in text
    saved = releases.dia.store.get(task.id)
    assert saved.details["published"]["steam"]["build_id"] == "4242"
    assert releases.dia.store.audit(action="build.publish")[0]["detail"].startswith("steam:480")


async def test_never_live_on_the_default_branch(tmp_path, monkeypatch) -> None:
    releases, task, _ = make(tmp_path, monkeypatch, {**STEAM, "branch": "default"})
    with pytest.raises(TaskActionError, match="default branch"):
        await releases.publish_steam(task.id)


async def test_needs_configuration_and_a_matching_depot(tmp_path, monkeypatch) -> None:
    releases, task, _ = make(tmp_path, monkeypatch, {"app_id": 480})
    with pytest.raises(TaskActionError, match="depots and username"):
        await releases.publish_steam(task.id)
    releases.options["steam"] = {**STEAM, "depots": {"Windows Desktop": 482}}
    with pytest.raises(TaskActionError, match="no.*depot|none of the built"):
        await releases.publish_steam(task.id)
