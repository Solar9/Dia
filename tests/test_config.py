from pathlib import Path

import pytest

from dia.agents.claude_code import ClaudeCodeAgent
from dia.agents.command import CommandAgent
from dia.config import ConfigError, parse_config


def test_agents_are_resolved_through_plugins(tmp_path: Path) -> None:
    config = parse_config(
        {
            "dia": {"default_agent": "main", "data_dir": "data"},
            "agents": {
                "main": {"type": "claude-code", "model": "sonnet"},
                "script": {"type": "command", "argv": ["echo", "{prompt}"]},
            },
            "projects": {"p": {"path": "repo", "default_agent": "script"}},
        },
        tmp_path / "dia.toml",
    )
    assert config.data_dir == tmp_path / "data"
    assert config.projects["p"].path == tmp_path / "repo"

    main = config.agent()
    assert isinstance(main, ClaudeCodeAgent) and main.options == {"model": "sonnet"}
    assert isinstance(config.agent(project=config.project("p")), CommandAgent)


def test_unknown_agent_and_plugin_are_reported() -> None:
    config = parse_config({"agents": {"x": {"type": "nope"}}})
    with pytest.raises(ConfigError):
        config.agent("missing")
    with pytest.raises(LookupError, match="no plugin 'nope'"):
        config.agent("x")


def test_project_requires_path() -> None:
    with pytest.raises(ConfigError, match="needs a 'path'"):
        parse_config({"projects": {"p": {}}})


def test_shadowed_config_is_reported(tmp_path: Path, monkeypatch) -> None:
    from dia.config import load_config

    (tmp_path / "dia.toml").write_text("[dia]\n")
    user = tmp_path / "xdg" / "dia" / "config.toml"
    user.parent.mkdir(parents=True)
    user.write_text("[dia]\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DIA_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    config = load_config()
    assert config.source == tmp_path / "dia.toml" and config.shadowed == [user]


def test_an_agent_spec_carries_a_model_for_one_use() -> None:
    config = parse_config({"agents": {"claude": {"type": "claude-code", "model": "sonnet"}}})
    assert config.split_agent("claude:opus") == ("claude", "opus")
    assert config.split_agent("claude") == ("claude", None)
    assert config.agent("claude:opus").options["model"] == "opus"
    assert config.agent("claude").options["model"] == "sonnet"  # the setting is untouched
    assert config.agent("claude:opus").name == "claude"
