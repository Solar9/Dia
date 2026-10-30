"""Who Dia is: author, links, license, and versions of the bits it runs on."""

from __future__ import annotations

import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import TYPE_CHECKING, Any

from dia import __version__
from dia.agents.base import find_executable

if TYPE_CHECKING:
    from dia.config import Config

AUTHOR = "Solar"
WEBSITE = "https://solar9.me"
GITHUB = "https://github.com/Solar9/Dia"
EMAIL = "solar@solar9.me"
LICENSE = "PolyForm Noncommercial 1.0.0"
LICENSE_URL = "https://polyformproject.org/licenses/noncommercial/1.0.0/"

_PACKAGES = (
    "aiohttp",
    "PySide6",
    "discord.py",
    "faster-whisper",
    "piper-tts",
    "anthropic",
    "onnxruntime",
)
_CLIS = ("ollama", "gh", "glab")


def identity() -> dict[str, str]:
    return {
        "name": "Dia",
        "version": __version__,
        "author": AUTHOR,
        "website": WEBSITE,
        "github": GITHUB,
        "email": EMAIL,
        "license": LICENSE,
        "license_url": LICENSE_URL,
    }


def snapshot(config: Config | None = None) -> dict[str, Any]:
    """Identity plus the versions of libraries, agent CLIs and this copy's paths."""
    info: dict[str, Any] = identity()
    if config is not None:
        info["config"] = str(config.source or "")
        info["data_dir"] = str(config.data_dir)
    info["components"] = components(config)
    return info


def components(config: Config | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = [
        {"name": "Dia", "version": __version__},
        {"name": "Python", "version": platform.python_version(), "detail": sys.executable},
        {"name": "OS", "version": f"{platform.system()} {platform.release()}"},
    ]
    if qt := _qt_version():
        rows.append({"name": "Qt", "version": qt})
    for package in _PACKAGES:
        if ver := _pkg(package):
            rows.append({"name": package, "version": ver})
    seen: set[str] = set()
    if config is not None:
        for name in config.agents:
            try:
                agent = config.agent(name)
            except Exception:
                continue
            command = getattr(agent, "command", None)
            if not command or command in seen:
                continue
            seen.add(command)
            ver, path = _cli_version(command)
            rows.append({"name": name, "version": ver or "—", "detail": path or command})
    for name in _CLIS:
        if name in seen:
            continue
        ver, path = _cli_version(name)
        if ver or path:
            seen.add(path or name)
            rows.append({"name": name, "version": ver or "—", "detail": path or ""})
    return rows


def _pkg(name: str) -> str | None:
    try:
        return pkg_version(name)
    except PackageNotFoundError:
        return None


def _qt_version() -> str | None:
    try:
        from PySide6.QtCore import qVersion
    except Exception:
        return None
    try:
        return str(qVersion())
    except Exception:
        return None


def _cli_version(command: str) -> tuple[str | None, str | None]:
    path = find_executable(command)
    if not path:
        return None, None
    try:
        proc = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=1.5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, path
    text = (proc.stdout or proc.stderr or "").strip()
    line = None
    for raw in text.splitlines():
        candidate = raw.strip()
        if not candidate or candidate.lower().startswith(("warning", "error", "fatal")):
            continue
        line = candidate
        break
    if line and len(line) > 80:
        line = line[:77] + "…"
    return line or None, path
