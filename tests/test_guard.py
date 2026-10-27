from pathlib import Path

import pytest

from dia import sandbox
from dia.config import parse_config
from dia.orchestrator import Orchestrator

pytestmark = pytest.mark.skipif(not sandbox.bwrap_works(), reason="bubblewrap not usable")


def make(tmp_path: Path, repo: Path, script: str, decoys: bool = True) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", script]}},
        "projects": {"demo": {"path": str(repo)}},
        "sandbox": {"enabled": True, "decoys": decoys},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def watch(dia: Orchestrator) -> list:
    events = []

    async def listen(event):
        events.append((event.kind, event.message))

    dia.listeners.append(listen)
    return events


async def test_reading_a_decoy_secret_stops_the_task(tmp_path, repo) -> None:
    # What an injected instruction would make an agent do: read a key, say it.
    dia = make(tmp_path, repo, "echo x > x.txt; cat ~/.ssh/id_ed25519")
    events = await watch(dia)
    task = (await dia.run_task("demo", "do as the README says")).task
    assert task.status == "failed" and "stopped by the guard" in task.error
    assert task.commit_sha is None  # its work is not kept
    incident = task.details["incidents"][0]
    assert (incident["severity"], incident["kind"]) == ("high", "decoy-secret-in-output")
    assert "<decoy>" in incident["detail"] and "DIA-DECOY" not in incident["detail"]
    assert events[0][0] == "security"
    assert dia.store.audit(action="guard.incident")
    assert not list((tmp_path / "data" / "guard").iterdir())  # decoys cleaned up


async def test_copying_a_decoy_into_the_code_is_caught(tmp_path, repo) -> None:
    script = "cp ~/.config/dia/env config.txt; echo 'added a config file'"
    task = (await make(tmp_path, repo, script).run_task("demo", "add config")).task
    assert task.status == "failed"
    assert task.details["incidents"][0]["kind"] == "decoy-secret-in-files"
    assert task.details["incidents"][0]["detail"] == "config.txt"


async def test_an_attempt_without_decoys_is_noted_but_not_stopped(tmp_path, repo) -> None:
    script = "echo x > x.txt; cat ~/.ssh/id_rsa 2>&1; echo done"
    task = (await make(tmp_path, repo, script, decoys=False).run_task("demo", "x")).task
    assert task.status == "done"
    assert task.details["incidents"][0]["severity"] == "medium"


async def test_ordinary_work_raises_nothing(tmp_path, repo) -> None:
    task = (await make(tmp_path, repo, "echo ok > ok.txt; echo done").run_task("demo", "x")).task
    assert task.status == "done" and "incidents" not in task.details
