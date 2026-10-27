"""Secrets (API keys, tokens) live in one file, ``~/.config/dia/env`` (mode 600),
never in the config or the repository.

It is the same file the systemd service reads (``EnvironmentFile``); Dia also
loads it at start, so ``dia serve`` started by hand sees the same keys. Values
can be set but never read back through the CLI or the UI, only their names.
"""

from __future__ import annotations

import os
import re

from dia.service import env_path

_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

# Keys Dia knows what to do with (shown in the UI even before they are set).
KNOWN = {
    "DIA_DISCORD_TOKEN": "Discord bot token",
    "ELEVENLABS_API_KEY": "ElevenLabs (voice)",
    "OPENAI_API_KEY": "OpenAI-compatible brain",
    "DIA_CALENDAR_URL": "Calendar (iCal address)",
    "DIA_MAIL_PASSWORD": "Mail (IMAP / app password)",
    "HA_TOKEN": "Home Assistant (long-lived token)",
    "BUTLER_API_KEY": "itch.io (butler)",
}


def _read() -> list[str]:
    try:
        return env_path().read_text().splitlines()
    except FileNotFoundError:
        return []


def _parse(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    name, value = line.split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return name.strip().removeprefix("export ").strip(), value


def names() -> list[str]:
    return [parsed[0] for line in _read() if (parsed := _parse(line))]


def load_into_environment() -> None:
    """Put the file's values into ``os.environ`` (what is already set wins)."""
    for line in _read():
        if parsed := _parse(line):
            os.environ.setdefault(*parsed)


def _write(lines: list[str]) -> None:
    path = env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text("\n".join(lines) + "\n")


def set_secret(name: str, value: str) -> None:
    if not _NAME.match(name):
        raise ValueError("a secret's name is like ELEVENLABS_API_KEY (A-Z, 0-9, _)")
    if "\n" in value or not value.strip():
        raise ValueError("the value must be one non-empty line")
    lines = [line for line in _read() if (_parse(line) or ("",))[0] != name]
    _write([*lines, f"{name}={value.strip()}"])
    os.environ[name] = value.strip()


def remove_secret(name: str) -> bool:
    lines = _read()
    kept = [line for line in lines if (_parse(line) or ("",))[0] != name]
    if len(kept) == len(lines):
        return False
    _write(kept)
    os.environ.pop(name, None)
    return True


def status() -> list[dict[str, object]]:
    """Name, description and whether it is set: never the value."""
    present = set(names()) | {k for k in KNOWN if os.environ.get(k)}
    every = list(KNOWN) + [n for n in names() if n not in KNOWN]
    return [{"name": n, "label": KNOWN.get(n, ""), "set": n in present} for n in every]
