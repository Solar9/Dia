import sys
from pathlib import Path

import pytest

from dia import service


@pytest.fixture
def systemd(tmp_path: Path, monkeypatch) -> Path:
    """A fake systemctl that logs its arguments, and a private XDG config home."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "systemctl.log"
    fake = bin_dir / "systemctl"
    fake.write_text(f'#!/bin/sh\necho "$@" >> {log}\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return log


def test_install_writes_unit_and_private_env(systemd: Path, tmp_path: Path) -> None:
    config = tmp_path / "my configs" / "config.toml"
    service.install(config)
    unit = service.unit_path().read_text()
    assert f'ExecStart={sys.executable} -m dia --config "{config}" serve' in unit
    assert f"Environment=PATH={tmp_path / 'bin'}:/usr/bin:/bin" in unit
    assert f"EnvironmentFile=-{service.env_path()}" in unit
    env = service.env_path()
    assert env.stat().st_mode & 0o777 == 0o600 and "DIA_DISCORD_TOKEN" in env.read_text()
    assert systemd.read_text().splitlines() == [
        "--user daemon-reload",
        "--user enable --now dia.service",
    ]


def test_install_keeps_existing_secrets(systemd: Path) -> None:
    service.env_path().parent.mkdir(parents=True)
    service.env_path().write_text("DIA_DISCORD_TOKEN=secret\n")
    service.install(None, start=False)
    assert service.env_path().read_text() == "DIA_DISCORD_TOKEN=secret\n"
    assert systemd.read_text().splitlines()[-1] == "--user enable dia.service"


def test_uninstall(systemd: Path) -> None:
    service.install(None)
    service.uninstall()
    assert not service.unit_path().exists()
    assert "--user disable --now dia.service" in systemd.read_text()


def test_without_systemd(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(RuntimeError, match="systemd is not available"):
        service.install(None)
