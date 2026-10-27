import subprocess
from pathlib import Path

from dia import setup
from dia.config import load_config


def repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return path


def test_finds_projects_and_writes_a_working_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo(tmp_path / "Projekty" / "Software" / "Dia")
    repo(tmp_path / "Projekty" / "Games" / "Nova")
    repo(tmp_path / "games" / "nova")  # same name: made unique
    (tmp_path / "Projekty" / "node_modules" / "x").mkdir(parents=True)
    found = setup.find_projects()
    assert set(found) == {"dia", "nova", "nova-2"}
    vault = tmp_path / "Obsidian" / "Main"
    (vault / ".obsidian").mkdir(parents=True)
    assert setup.find_vault() == vault

    answers = setup.answers_from(
        language="pl", user_name='Dawid "Solar"', agents={"claude": "claude-code"},
        default_agent="claude", projects=found, vault=vault, ollama_model="qwen2.5:3b",
    )  # fmt: skip
    target = setup.write(answers, tmp_path / ".config" / "dia" / "config.toml")
    config = load_config(target)
    assert config.default_agent == "claude" and config.language == "pl"
    assert config.projects["nova-2"].path == tmp_path / "games" / "nova"
    assert config.assistant["user_name"] == 'Dawid "Solar"'
    assert [b.name for b in config.brain_chain()] == ["rules", "local", "default-agent"]
    assert '"~/Projekty/Software/Dia"' in target.read_text()  # portable paths
    setup.write(answers, target)
    assert target.with_suffix(".toml.bak").exists()  # the old one kept


def test_scripted_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(setup, "find_agents", lambda: {"claude": "claude-code"})
    monkeypatch.setattr(setup, "find_ollama_model", lambda: None)
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)  # no systemd, no KDE
    monkeypatch.setattr("dia.desktop.desktop_dir", lambda: tmp_path / "Desktop")
    target = tmp_path / "config" / "dia" / "config.toml"
    setup.run(assume=True, target=target)
    assert load_config(target).agents == {"claude": {"type": "claude-code"}}
    assert (tmp_path / "data" / "applications" / "dia.desktop").exists()
