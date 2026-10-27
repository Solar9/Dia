import os
from pathlib import Path

import pytest

from dia import sandbox
from dia.agents import Mode
from dia.config import parse_config
from dia.orchestrator import Orchestrator

needs_bwrap = pytest.mark.skipif(not sandbox.bwrap_works(), reason="bubblewrap not usable")


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """A fake home with things an agent must not see."""
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "id_ed25519").write_text("PRIVATE KEY")
    (home / ".config" / "dia").mkdir(parents=True)
    (home / ".config" / "dia" / "env").write_text("HA_TOKEN=secret-ha\n")
    (home / "other-project").mkdir()
    (home / "other-project" / "notes.txt").write_text("someone else's work")
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)  # CI runners set it
    monkeypatch.setenv("HA_TOKEN", "secret-ha")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "agent-key")
    return home


def make(tmp_path: Path, repo: Path, script: str, **sandbox_options) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", script]}},
        "projects": {"demo": {"path": str(repo)}},
        "sandbox": {"enabled": True, "decoys": False, **sandbox_options},  # see test_guard
    }
    return Orchestrator(parse_config(raw), use_memory=False)


@needs_bwrap
async def test_the_agent_sees_its_worktree_and_nothing_private(tmp_path, repo, home) -> None:
    script = (
        "cat ~/.ssh/id_ed25519 2>&1; cat ~/.config/dia/env 2>&1; ls ~/other-project 2>&1; "
        'echo "HA=$HA_TOKEN KEY=$ANTHROPIC_API_KEY"; cat README.md; '
        "echo change > feature.txt; echo leak > ~/planted.txt 2>&1; git status --short"
    )
    task = (await make(tmp_path, repo, script).run_task("demo", "look around")).task
    out = task.summary
    assert "PRIVATE KEY" not in out and "secret-ha" not in out
    assert "someone else's work" not in out
    assert "HA= KEY=agent-key" in out  # Dia's secrets gone, the agent's own key kept
    assert "hello" in out  # its own repository is there
    assert "?? feature.txt" in out  # git works in the worktree
    assert task.status == "done" and task.commit_sha  # its change was committed
    assert not (home / "planted.txt").exists()  # nothing written into the real home


@needs_bwrap
async def test_the_data_directory_stays_hidden(tmp_path, repo, home) -> None:
    script = 'ls "$0" 2>&1 || echo HIDDEN'
    dia = make(tmp_path, repo, script.replace("$0", str(tmp_path / "data")))
    (tmp_path / "data" / "secret-marker").write_text("x")
    task = (await dia.run_task("demo", "peek", mode=Mode.READ_ONLY)).task
    assert "secret-marker" not in task.summary


@needs_bwrap
async def test_agent_dirs_and_extra_reads_are_allowed(tmp_path, repo, home) -> None:
    shared = home / "shared-assets"
    shared.mkdir()
    (shared / "logo.txt").write_text("LOGO")
    script = (
        "cat ~/shared-assets/logo.txt; cat ~/.claude/settings.json; echo x > ~/shared-assets/w 2>&1"
    )
    dia = make(tmp_path, repo, script, allow_read=[str(shared)])
    dia.config.agents["a"]["type"] = "command"
    request_sandbox = sandbox.for_agent(dia.config, "claude-code", {}, None)
    assert any(p.name == ".claude" for p in request_sandbox.write)
    task = (await dia.run_task("demo", "read", mode=Mode.READ_ONLY)).task
    assert "LOGO" in task.summary
    assert not (shared / "w").exists()  # read-only


def test_settings(tmp_path, monkeypatch) -> None:
    off = parse_config({"dia": {"data_dir": str(tmp_path)}, "sandbox": {"enabled": False}})
    assert sandbox.for_agent(off, "codex", {}) is None
    monkeypatch.setattr(sandbox, "bwrap_works", lambda: False)
    auto = parse_config({"dia": {"data_dir": str(tmp_path)}})
    assert sandbox.for_agent(auto, "codex", {}) is None  # "auto" without bwrap: off
    required = parse_config({"dia": {"data_dir": str(tmp_path)}, "sandbox": {"enabled": True}})
    with pytest.raises(RuntimeError, match="bubblewrap"):
        sandbox.for_agent(required, "codex", {})


def test_the_command_line(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    worktree = tmp_path / "wt"
    worktree.mkdir()
    box = sandbox.Sandbox(network=False, hide=[tmp_path / "data"])
    (tmp_path / "data").mkdir()
    argv = box.wrap(["codex", "exec"], worktree)
    assert argv[:2] == ["bwrap", "--die-with-parent"] and "--unshare-net" in argv
    assert argv[argv.index("--tmpfs") + 1] == str(tmp_path / "home")
    assert argv[-8:] == [
        "--bind",
        str(worktree),
        str(worktree),
        "--chdir",
        str(worktree),
        "--",
        "codex",
        "exec",
    ]
    hidden = argv.index(str(tmp_path / "data"))
    assert argv[hidden - 1] == "--tmpfs"
    assert os.environ.get("HOME") == str(tmp_path / "home")
