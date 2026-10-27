"""The computer Dia runs on: resources, temperatures, processes.

Everything is read from ``/proc`` and ``/sys`` (Linux), no extra packages.
``SystemWatcher`` (in `dia serve`) raises alerts when something crosses a
limit, at most once per ``cooldown`` per kind::

    [system]
    cpu_temp = 90          # °C
    disk_used = 90         # % of any real filesystem
    memory_used = 95       # %
    battery_low = 15       # %, while discharging
    check_urls = ["https://my-server.example"]   # alert when one stops answering
    interval = 60
    cooldown_minutes = 60
"""

from __future__ import annotations

import asyncio
import logging
import os
import pwd
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.audit import ACTOR

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.system")

PROC = Path("/proc")
SYS = Path("/sys")
REAL_FS = {"ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "vfat", "exfat", "ntfs", "ntfs3", "zfs"}
PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
TICKS = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


@dataclass
class Snapshot:
    cpu_percent: float
    cores: int
    load: tuple[float, float, float]
    memory: dict[str, float]  # total_gb, used_gb, percent
    swap: dict[str, float]
    disks: list[dict[str, Any]] = field(default_factory=list)  # mount, total_gb, used_gb, percent
    temperatures: list[dict[str, Any]] = field(default_factory=list)  # name, celsius
    battery: dict[str, Any] | None = None  # percent, status
    uptime_hours: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def cpu_temp(self) -> float | None:
        """The hottest CPU sensor (package, Tctl...), else any sensor."""
        cpu = [t["celsius"] for t in self.temperatures if t["cpu"]]
        temps = cpu or [t["celsius"] for t in self.temperatures]
        return max(temps) if temps else None


def _cpu_times() -> tuple[int, int]:
    """(busy, total) jiffies across all CPUs."""
    fields = [int(x) for x in (PROC / "stat").read_text().splitlines()[0].split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    return sum(fields) - idle, sum(fields)


def _meminfo() -> dict[str, int]:
    info = {}
    for line in (PROC / "meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        info[key] = int(rest.split()[0]) * 1024
    return info


def _gb(value: float) -> float:
    return round(value / 1024**3, 1)


def disks() -> list[dict[str, Any]]:
    seen, found = set(), []
    for line in (PROC / "mounts").read_text().splitlines():
        device, mount, fstype = line.split()[:3]
        if fstype not in REAL_FS or device in seen:
            continue
        seen.add(device)
        try:
            st = os.statvfs(mount.replace("\\040", " "))
        except OSError:
            continue
        total = st.f_blocks * st.f_frsize
        if not total:
            continue
        used = total - st.f_bavail * st.f_frsize
        found.append(
            {
                "mount": mount,
                "total_gb": _gb(total),
                "used_gb": _gb(used),
                "percent": round(100 * used / total, 1),
            }
        )
    return found


def temperatures() -> list[dict[str, Any]]:
    found = []
    for hwmon in sorted((SYS / "class" / "hwmon").glob("hwmon*")):
        try:
            chip = (hwmon / "name").read_text().strip()
        except OSError:
            continue
        for sensor in sorted(hwmon.glob("temp*_input")):
            try:
                celsius = int(sensor.read_text()) / 1000
            except (OSError, ValueError):
                continue
            label_file = sensor.with_name(sensor.name.replace("_input", "_label"))
            label = label_file.read_text().strip() if label_file.exists() else chip
            is_cpu = (
                chip in ("coretemp", "k10temp", "zenpower", "cpu_thermal") or "Package" in label
            )
            if 0 < celsius < 150:
                found.append(
                    {"name": f"{chip} {label}".strip(), "celsius": round(celsius, 1), "cpu": is_cpu}
                )
    if not found:
        for zone in sorted((SYS / "class" / "thermal").glob("thermal_zone*")):
            try:
                celsius = int((zone / "temp").read_text()) / 1000
                kind = (zone / "type").read_text().strip()
            except (OSError, ValueError):
                continue
            if 0 < celsius < 150:
                found.append(
                    {
                        "name": kind,
                        "celsius": round(celsius, 1),
                        "cpu": "x86_pkg" in kind or "cpu" in kind.lower(),
                    }
                )
    return found


def battery() -> dict[str, Any] | None:
    for supply in sorted((SYS / "class" / "power_supply").glob("BAT*")):
        try:
            return {
                "percent": int((supply / "capacity").read_text()),
                "status": (supply / "status").read_text().strip(),
            }
        except (OSError, ValueError):
            continue
    return None


async def snapshot(sample: float = 0.5) -> Snapshot:
    busy1, total1 = _cpu_times()
    await asyncio.sleep(sample)
    busy2, total2 = _cpu_times()
    cpu = 100 * (busy2 - busy1) / max(total2 - total1, 1)
    mem = _meminfo()
    used = mem["MemTotal"] - mem.get("MemAvailable", mem.get("MemFree", 0))
    swap_used = mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)
    load = tuple(float(x) for x in (PROC / "loadavg").read_text().split()[:3])
    return Snapshot(
        cpu_percent=round(cpu, 1),
        cores=os.cpu_count() or 1,
        load=load,  # type: ignore[arg-type]
        memory={
            "total_gb": _gb(mem["MemTotal"]),
            "used_gb": _gb(used),
            "percent": round(100 * used / mem["MemTotal"], 1),
        },
        swap={
            "total_gb": _gb(mem.get("SwapTotal", 0)),
            "used_gb": _gb(swap_used),
            "percent": round(100 * swap_used / mem["SwapTotal"], 1) if mem.get("SwapTotal") else 0,
        },
        disks=disks(),
        temperatures=temperatures(),
        battery=battery(),
        uptime_hours=round(float((PROC / "uptime").read_text().split()[0]) / 3600, 1),
    )


# ------------------------------------------------------------- processes ---


@dataclass
class Process:
    pid: int
    name: str
    user: str
    cpu_percent: float
    memory_mb: float
    command: str


def _proc_ticks() -> dict[int, tuple[int, str]]:
    found = {}
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        name = stat[stat.index("(") + 1 : stat.rindex(")")]
        rest = stat[stat.rindex(")") + 2 :].split()
        found[int(entry.name)] = (int(rest[11]) + int(rest[12]), name)
    return found


async def processes(limit: int = 15, sample: float = 0.5, sort: str = "cpu") -> list[Process]:
    """The busiest processes (CPU over ``sample`` seconds, or memory)."""
    before = _proc_ticks()
    await asyncio.sleep(sample)
    after = _proc_ticks()
    users: dict[int, str] = {}
    result = []
    for pid, (ticks, name) in after.items():
        cpu = 100 * (ticks - before.get(pid, (ticks, ""))[0]) / TICKS / sample
        try:
            rss = int((PROC / str(pid) / "statm").read_text().split()[1]) * PAGE
            uid = (PROC / str(pid)).stat().st_uid
            raw = (PROC / str(pid) / "cmdline").read_bytes()
        except (OSError, ValueError, IndexError):
            continue
        if uid not in users:
            try:
                users[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                users[uid] = str(uid)
        command = raw.replace(b"\0", b" ").decode(errors="replace").strip() or f"[{name}]"
        result.append(
            Process(pid, name, users[uid], round(cpu, 1), round(rss / 1024**2, 1), command[:300])
        )
    key = (lambda p: p.cpu_percent) if sort == "cpu" else (lambda p: p.memory_mb)
    return sorted(result, key=key, reverse=True)[:limit]


def find_processes(name: str) -> list[tuple[int, str, str]]:
    """(pid, name, command) of the current user's processes whose name or program matches."""
    me, needle, found = os.getuid(), name.lower(), []
    for pid, (_, pname) in _proc_ticks().items():
        try:
            if (PROC / str(pid)).stat().st_uid != me or pid == os.getpid():
                continue
            command = (
                (PROC / str(pid) / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode(errors="replace")
            )
        except OSError:
            continue
        if needle in pname.lower() or needle in os.path.basename(command.split(" ")[0]).lower():
            found.append((pid, pname, command.strip()[:200] or pname))
    return found


# ---------------------------------------------------------------- alerts ---


def check_limits(snap: Snapshot, options: dict[str, Any]) -> list[tuple[str, str]]:
    """(kind, message) for every limit the snapshot crosses."""
    alerts = []
    if (temp := snap.cpu_temp) is not None and temp >= float(options.get("cpu_temp", 90)):
        alerts.append(("cpu_temp", f"CPU temperature {temp:.0f}°C"))
    limit = float(options.get("disk_used", 90))
    for disk in snap.disks:
        if disk["percent"] >= limit:
            free = disk["total_gb"] - disk["used_gb"]
            alerts.append(
                (
                    f"disk:{disk['mount']}",
                    f"disk {disk['mount']} {disk['percent']:.0f}% full ({free:.1f} GB free)",
                )
            )
    if snap.memory["percent"] >= float(options.get("memory_used", 95)):
        alerts.append(("memory", f"memory {snap.memory['percent']:.0f}% used"))
    bat = snap.battery
    if (
        bat
        and bat["status"] == "Discharging"
        and bat["percent"] <= int(options.get("battery_low", 15))
    ):
        alerts.append(("battery", f"battery at {bat['percent']}%"))
    return alerts


def url_down(url: str, timeout: float = 10) -> str | None:
    """Why ``url`` doesn't answer, or None when it does (any HTTP status below 500)."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Dia"})
        with urllib.request.urlopen(req, timeout=timeout):
            return None
    except urllib.error.HTTPError as exc:
        return None if exc.code < 500 else f"HTTP {exc.code}"
    except (OSError, ValueError) as exc:
        return str(getattr(exc, "reason", exc))


class SystemWatcher:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self._last: dict[str, float] = {}
        self._down: set[str] = set()

    @property
    def options(self) -> dict[str, Any]:
        return self.dia.config.section("system")

    async def run(self) -> None:
        ACTOR.set("system")
        while True:
            try:
                await self.poll()
            except Exception:
                log.exception("system check failed")
            await asyncio.sleep(float(self.options.get("interval", 60)))

    async def poll(self) -> list[str]:
        cooldown = float(self.options.get("cooldown_minutes", 60)) * 60
        now, raised = time.monotonic(), []
        alerts = check_limits(await snapshot(), self.options)
        for url in self.options.get("check_urls", []):
            reason = await asyncio.to_thread(url_down, url)
            if reason and url not in self._down:
                self._down.add(url)
                alerts.append((f"url:{url}", f"{url} is not answering ({reason})"))
            elif not reason and url in self._down:
                self._down.discard(url)
                await self.dia.emit("system", None, f"{url} answers again", {"kind": f"url:{url}"})
        if self.options.get("watch_ports", True):
            from dia.security import listening, new_exposed_ports

            for sock in new_exposed_ports(self.dia, listening()):
                who = f" ({sock['process']})" if sock["process"] else ""
                alerts.append(
                    (f"port:{sock['port']}", f"new port open to the network: {sock['port']}{who}")
                )
        for kind, message in alerts:
            if now - self._last.get(kind, -cooldown) < cooldown:
                continue
            self._last[kind] = now
            raised.append(message)
            await self.dia.emit("system", None, message, {"kind": kind})
        return raised
