import json
from pathlib import Path

from dia.agents import AgentRequest, Mode
from dia.agents.claude_code import ClaudeCodeAgent
from dia.agents.codex import CodexAgent
from dia.agents.command import CommandAgent
from dia.agents.cursor import CursorAgent


def req(mode: Mode = Mode.EDIT) -> AgentRequest:
    return AgentRequest(prompt="fix it", cwd=Path("."), mode=mode)


def test_claude_argv_and_parse(tmp_path: Path) -> None:
    agent = ClaudeCodeAgent("c", {"model": "opus"})
    argv = agent.build_argv(req(Mode.READ_ONLY), tmp_path)
    assert argv[0].endswith("claude") and argv[1:3] == ["-p", "fix it"]
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert argv[argv.index("--model") + 1] == "opus"

    out = json.dumps({"result": "done", "session_id": "s1", "is_error": False})
    result = agent.parse(req(), tmp_path, 0, out, "")
    assert result.success and result.summary == "done" and result.session_id == "s1"
    assert not agent.parse(req(), tmp_path, 1, "not json", "boom").success


def test_codex_reads_last_message_file(tmp_path: Path) -> None:
    agent = CodexAgent("x")
    argv = agent.build_argv(req(), tmp_path)
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    Path(argv[argv.index("--output-last-message") + 1]).write_text("final answer\n")
    assert agent.parse(req(), tmp_path, 0, "progress...", "").summary == "final answer"


def test_cursor_only_forces_edits_in_edit_mode(tmp_path: Path) -> None:
    agent = CursorAgent("cu")
    assert "--force" in agent.build_argv(req(Mode.EDIT), tmp_path)
    assert "--force" not in agent.build_argv(req(Mode.READ_ONLY), tmp_path)


def make_exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_cursor_binary_is_detected(tmp_path: Path, monkeypatch) -> None:
    agent_bin = make_exe(tmp_path / "agent")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert CursorAgent("cu").command == str(agent_bin)
    assert CursorAgent("cu", {"command": "my-cursor"}).command == "my-cursor"


def test_binaries_outside_path_are_found_in_local_bin(tmp_path: Path, monkeypatch) -> None:
    # e.g. installed to ~/.local/bin while Dia runs with a PATH that lacks it
    claude_bin = make_exe(tmp_path / ".local" / "bin" / "claude")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/nonexistent")
    assert ClaudeCodeAgent("c").command == str(claude_bin)


def test_cursor_trusts_the_worktree_by_default(tmp_path: Path) -> None:
    assert "--trust" in CursorAgent("cu").build_argv(req(), tmp_path)
    assert "--trust" not in CursorAgent("cu", {"trust": False}).build_argv(req(), tmp_path)


async def test_command_agent_runs_any_cli(tmp_path: Path) -> None:
    agent = CommandAgent("echo", {"argv": ["sh", "-c", "echo got: $0", "{prompt}"]})
    result = await agent.run(AgentRequest(prompt="hi there", cwd=tmp_path))
    assert result.success and result.summary == "got: hi there"
    assert await agent.check() is None


def test_command_template_keeps_literal_braces(tmp_path: Path) -> None:
    agent = CommandAgent("j", {"argv": ["echo", '{"a": 1}', "{prompt}", "{unknown}"]})
    argv = agent.build_argv(AgentRequest(prompt="p {x}", cwd=tmp_path), tmp_path)
    assert argv[1:] == ['{"a": 1}', "p {x}", "{unknown}"]


async def test_missing_binary_is_a_failed_result(tmp_path: Path) -> None:
    agent = ClaudeCodeAgent("c", {"command": "definitely-not-installed-dia"})
    assert await agent.check()
    result = await agent.run(AgentRequest(prompt="x", cwd=tmp_path))
    assert not result.success and "not found" in (result.error or "")


def test_known_models_are_offered_and_auto_adds_no_flag(tmp_path: Path) -> None:
    assert "opus" in ClaudeCodeAgent.models
    req = AgentRequest(prompt="x", cwd=tmp_path)
    assert "--model" not in ClaudeCodeAgent("c", {}).build_argv(req, tmp_path)
    assert "opus" in ClaudeCodeAgent("c", {"model": "opus"}).build_argv(req, tmp_path)


def test_resuming_a_session_adds_the_resume_arguments(tmp_path: Path) -> None:
    req = AgentRequest(prompt="go on", cwd=tmp_path, session_id="sid")
    codex = CodexAgent("x", {}).build_argv(req, tmp_path)
    assert codex[-3:] == ["resume", "sid", "go on"]
    assert "--resume" in CursorAgent("x", {}).build_argv(req, tmp_path)
    assert ["--resume", "sid"] == ClaudeCodeAgent("x", {}).build_argv(req, tmp_path)[3:5] or (
        "--resume" in ClaudeCodeAgent("x", {}).build_argv(req, tmp_path)
    )
