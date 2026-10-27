"""Acting on the computer: processes, services, containers, updates.

Reading is free; changing anything (ending a process, restarting a service)
is only ever done after you confirm it, and only for your own user: Dia never
runs ``sudo``. Updates are reported, with the command to install them, never
installed.
"""

from __future__ import annotations

import json
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path

from dia.agents.base import find_executable
from dia.workspace import run

HOME = Path.home()


async def _out(argv: list[str], timeout: float = 120) -> tuple[int, str]:
    return await run(argv, HOME, timeout)


def end_process(pid: int, force: bool = False) -> None:
    """SIGTERM (or SIGKILL) one of the current user's processes."""
    if pid <= 1 or pid == os.getpid():
        raise ValueError("that process can't be ended")
    if Path(f"/proc/{pid}").stat().st_uid != os.getuid():
        raise PermissionError("that process belongs to another user")
    os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)


# -------------------------------------------------------------- services ---


async def failed_units() -> list[dict[str, str]]:
    """systemd units in the failed state, system-wide and the user's own."""
    if not find_executable("systemctl"):
        return []
    units = []
    for scope in ("system", "user"):
        argv = [
            "systemctl",
            *(["--user"] if scope == "user" else []),
            "--failed",
            "--no-legend",
            "--plain",
            "--output=json",
        ]
        code, out = await _out(argv, 20)
        if code != 0:
            continue
        try:
            for unit in json.loads(out or "[]"):
                units.append(
                    {
                        "unit": unit.get("unit", ""),
                        "scope": scope,
                        "description": unit.get("description", ""),
                    }
                )
        except ValueError:  # older systemd without JSON output
            for line in out.splitlines():
                if line.strip():
                    units.append({"unit": line.split()[0], "scope": scope, "description": ""})
    return units


async def containers() -> list[dict[str, str]]:
    """Docker/Podman containers that are not running fine (exited, unhealthy...)."""
    for tool in ("docker", "podman"):
        if not find_executable(tool):
            continue
        code, out = await _out([tool, "ps", "-a", "--format", "{{json .}}"], 20)
        if code != 0:
            continue
        found = []
        for line in out.splitlines():
            try:
                c = json.loads(line)
            except ValueError:
                continue
            status = c.get("Status") or c.get("State") or ""
            if "unhealthy" in status or status.lower().startswith(("exited", "dead", "restarting")):
                found.append(
                    {"name": c.get("Names") or c.get("Name", ""), "status": status, "tool": tool}
                )
        return found
    return []


async def restart_user_unit(unit: str) -> str:
    if not unit.replace("-", "").replace("_", "").replace("@", "").replace(".", "").isalnum():
        raise ValueError(f"not a unit name: {unit}")
    code, out = await _out(["systemctl", "--user", "restart", unit], 60)
    if code != 0:
        raise RuntimeError(out.strip() or f"systemctl --user restart {unit} failed")
    return f"restarted {unit}"


# --------------------------------------------------------------- updates ---


@dataclass
class Updates:
    source: str  # pacman, aur, flatpak, apt, dnf
    packages: list[str] = field(default_factory=list)
    command: str = ""  # how to install them (for you to run)


async def updates() -> list[Updates]:
    """Pending updates from every package manager that is installed."""
    found: list[Updates] = []
    if find_executable("checkupdates"):  # pacman-contrib: a safe, separate sync
        code, out = await _out(["checkupdates"])
        if code in (0, 2):  # 2: no updates
            found.append(
                Updates(
                    "pacman",
                    [line.split()[0] for line in out.splitlines() if line.strip()],
                    "sudo pacman -Syu",
                )
            )
    for helper in ("paru", "yay"):
        if find_executable(helper):
            code, out = await _out([helper, "-Qua"])
            found.append(
                Updates(
                    "aur",
                    [line.split()[0] for line in out.splitlines() if line.strip()],
                    f"{helper} -Sua",
                )
            )
            break
    if find_executable("flatpak"):
        code, out = await _out(["flatpak", "remote-ls", "--updates", "--columns=application"])
        if code == 0:
            found.append(
                Updates(
                    "flatpak",
                    [line.strip() for line in out.splitlines() if line.strip()],
                    "flatpak update",
                )
            )
    if not found and find_executable("apt"):
        code, out = await _out(["apt", "list", "--upgradable"])
        names = [line.split("/")[0] for line in out.splitlines() if "/" in line]
        found.append(Updates("apt", names, "sudo apt upgrade"))
    if not found and find_executable("dnf"):
        code, out = await _out(["dnf", "-q", "check-update"])
        names = [
            line.split()[0]
            for line in out.splitlines()
            if line.strip() and not line.startswith(" ")
        ]
        found.append(Updates("dnf", names, "sudo dnf upgrade"))
    return found
