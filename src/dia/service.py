"""Run ``dia serve`` as a systemd user service, so Discord, voice and the shortcut
work from login, restart on failure and log to the journal."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

UNIT_NAME = "dia.service"


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def unit_path() -> Path:
    return _config_home() / "systemd" / "user" / UNIT_NAME


def env_path() -> Path:
    return _config_home() / "dia" / "env"


def _quote(arg: str) -> str:
    """systemd splits ExecStart on spaces unless the argument is quoted."""
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"' if " " in arg else arg


def render_unit(config: Path | None, path_env: str) -> str:
    serve = [sys.executable, "-m", "dia"]
    if config:
        serve += ["--config", str(config.resolve())]
    serve.append("serve")
    return f"""\
[Unit]
Description=Dia, a personal assistant for coding agents
Documentation=https://github.com/Solar9/Dia
After=network-online.target pipewire.service
Wants=network-online.target

[Service]
ExecStart={" ".join(_quote(part) for part in serve)}
# Secrets such as DIA_DISCORD_TOKEN=... (this file is readable only by you).
EnvironmentFile=-{env_path()}
# Your shell's PATH at install time, so the agents' CLIs are found.
Environment=PATH={path_env}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args], capture_output=True, text=True, check=False
    )


def check() -> str | None:
    if not shutil.which("systemctl"):
        return "systemd is not available here; run `dia serve` another way (e.g. autostart)"
    return None


def install(config: Path | None, start: bool = True, enable: bool = True) -> list[str]:
    """Write the unit and the (empty) secrets file, then enable (and start) the service."""
    if problem := check():
        raise RuntimeError(problem)
    notes = []
    unit = unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(render_unit(config, os.environ.get("PATH", "/usr/bin:/bin")))
    notes.append(f"wrote {unit}")

    env = env_path()
    if not env.exists():
        env.parent.mkdir(parents=True, exist_ok=True)
        env.write_text("# Secrets for `dia serve`, one per line, e.g.\n# DIA_DISCORD_TOKEN=...\n")
        notes.append(f"created {env} (add DIA_DISCORD_TOKEN=... there)")
    env.chmod(0o600)

    commands = [["daemon-reload"]]
    if enable:
        commands.append(["enable", *(["--now"] if start else []), UNIT_NAME])
    elif start:
        commands.append(["start", UNIT_NAME])
    for args in commands:
        result = _systemctl(*args)
        if result.returncode != 0:
            raise RuntimeError(f"systemctl --user {' '.join(args)} failed: {result.stderr.strip()}")
    notes.append("enabled and started" if start else "enabled (starts at next login)")
    return notes


def uninstall() -> list[str]:
    if problem := check():
        raise RuntimeError(problem)
    _systemctl("disable", "--now", UNIT_NAME)
    unit_path().unlink(missing_ok=True)
    _systemctl("daemon-reload")
    return [f"stopped, disabled and removed {unit_path()} (secrets in {env_path()} kept)"]


def status() -> str:
    if problem := check():
        return problem
    return _systemctl("status", "--no-pager", UNIT_NAME).stdout.strip() or "not installed"


def installed() -> bool:
    return unit_path().exists() and check() is None


def start() -> bool:
    """Start the installed service (True when systemd took it)."""
    return installed() and _systemctl("start", UNIT_NAME).returncode == 0
