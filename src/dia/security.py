"""Security checks of your own computer, network and projects.

Passive checks (what listens on this computer, devices your computer has
seen on the network, failed logins in the journal, vulnerable dependencies)
need no setup. Active checks (port scans) only ever touch hosts you list as
yours; anything else is refused::

    [security]
    hosts = ["192.168.1.10", "nas.local"]   # yours, may be scanned (localhost always)
    ports = [22, 80, 443, 8080]             # extra ports to try without nmap
    nmap = true                             # use nmap -sV when installed
    networks = ["192.168.1.0/24"]           # yours: Dia may look for devices on them

Dia never changes firewall rules or system settings; findings come with
proposed fixes, and fixing a project's dependencies is an ordinary task.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import socket
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.agents.base import find_executable
from dia.workspace import run

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.security")

PROC = Path("/proc")
COMMON_PORTS = [
    21,
    22,
    23,
    25,
    53,
    80,
    110,
    111,
    135,
    139,
    143,
    443,
    445,
    631,
    993,
    995,
    1433,
    1883,
    2049,
    3000,
    3306,
    3389,
    5000,
    5432,
    5900,
    6379,
    8000,
    8080,
    8443,
    8765,
    9000,
    9090,
    11434,
    27017,
]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class NotAuthorized(PermissionError):
    pass


# ------------------------------------------------------------- listening ---


def _hex_address(text: str) -> str:
    raw = bytes.fromhex(text)
    if len(raw) == 4:
        return socket.inet_ntop(socket.AF_INET, raw[::-1])
    words = [raw[i : i + 4][::-1] for i in range(0, 16, 4)]
    return socket.inet_ntop(socket.AF_INET6, b"".join(words))


def _socket_owners() -> dict[int, str]:
    """inode -> process name, for the processes we may look into."""
    owners = {}
    for proc in PROC.iterdir():
        if not proc.name.isdigit():
            continue
        try:
            name = (proc / "comm").read_text().strip()
            for fd in (proc / "fd").iterdir():
                target = str(fd.readlink())
                if target.startswith("socket:["):
                    owners[int(target[8:-1])] = f"{name} ({proc.name})"
        except OSError:
            continue
    return owners


def listening() -> list[dict[str, Any]]:
    """TCP ports listening on this computer; ``exposed`` when reachable from outside."""
    owners = _socket_owners()
    found, seen = [], set()
    for table in ("tcp", "tcp6"):
        try:
            lines = (PROC / "net" / table).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 10 or parts[3] != "0A":  # 0A = LISTEN
                continue
            address, port_hex = parts[1].rsplit(":", 1)
            ip, port = _hex_address(address), int(port_hex, 16)
            if (ip, port) in seen:
                continue
            seen.add((ip, port))
            exposed = ip not in ("127.0.0.1", "::1") and not ip.startswith("127.")
            found.append(
                {
                    "address": ip,
                    "port": port,
                    "exposed": exposed,
                    "process": owners.get(int(parts[9]), ""),
                }
            )
    return sorted(found, key=lambda s: (not s["exposed"], s["port"]))


# ----------------------------------------------------------------- scans ---


def authorized(host: str, options: dict[str, Any]) -> bool:
    return host in LOCAL_HOSTS or host in options.get("hosts", [])


async def _connect(host: str, port: int, timeout: float) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, TimeoutError):
        return False
    writer.close()
    return True


async def scan(host: str, options: dict[str, Any]) -> list[dict[str, Any]]:
    """Open TCP ports of one of YOUR hosts (nmap -sV if installed, else a connect scan)."""
    if not authorized(host, options):
        raise NotAuthorized(
            f"{host} is not listed as yours in [security] hosts; Dia only scans your own hosts"
        )
    if options.get("nmap", True) and find_executable("nmap"):
        code, out = await run(
            [
                "nmap",
                "-Pn",
                "-sV",
                "--top-ports",
                str(options.get("top_ports", 200)),
                "-oG",
                "-",
                host,
            ],
            Path.home(),
            600,
        )
        found = []
        for line in out.splitlines():
            if "Ports:" not in line:
                continue
            for entry in line.split("Ports:", 1)[1].split("\t")[0].split(","):
                fields = entry.strip().split("/")
                if len(fields) >= 5 and fields[1] == "open":
                    found.append(
                        {
                            "port": int(fields[0]),
                            "service": fields[4],
                            "version": fields[6] if len(fields) > 6 else "",
                        }
                    )
        return found
    ports = sorted(set(COMMON_PORTS) | set(options.get("ports", [])))
    results = await asyncio.gather(*(_connect(host, p, 0.7) for p in ports))
    return [
        {"port": p, "service": "", "version": ""}
        for p, ok in zip(ports, results, strict=True)
        if ok
    ]


def devices() -> list[dict[str, str]]:
    """Devices this computer has talked to on the local network (ARP table; passive)."""
    found = []
    try:
        lines = (PROC / "net" / "arp").read_text().splitlines()[1:]
    except OSError:
        return []
    for line in lines:
        parts = line.split()
        if len(parts) >= 6 and parts[3] != "00:00:00:00:00:00":
            name = ""
            try:
                name = socket.gethostbyaddr(parts[0])[0]
            except OSError:
                pass
            found.append({"ip": parts[0], "mac": parts[3], "interface": parts[5], "name": name})
    return found


def network_of(network: str, options: dict[str, Any]) -> ipaddress.IPv4Network:
    """One of YOUR networks (``[security] networks``), private and at most a /22."""
    if network not in options.get("networks", []):
        raise NotAuthorized(
            f"{network} is not listed as yours in [security] networks; "
            "Dia only looks for devices on your own networks"
        )
    net = ipaddress.ip_network(network, strict=False)
    if not isinstance(net, ipaddress.IPv4Network) or not net.is_private:
        raise NotAuthorized(f"{network} is not a private IPv4 network")
    if net.num_addresses > 1024:
        raise NotAuthorized(f"{network} is too large to sweep (at most a /22)")
    return net


def parse_nmap_hosts(xml_text: str) -> list[dict[str, str]]:
    found = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    for host in root.iter("host"):
        status = host.find("status")
        if status is not None and status.get("state") != "up":
            continue
        entry = {"ip": "", "mac": "", "vendor": "", "name": ""}
        for address in host.findall("address"):
            if address.get("addrtype") == "ipv4":
                entry["ip"] = address.get("addr", "")
            elif address.get("addrtype") == "mac":
                entry["mac"] = address.get("addr", "").lower()
                entry["vendor"] = address.get("vendor", "")
        name = host.find("hostnames/hostname")
        if name is not None:
            entry["name"] = name.get("name", "")
        if entry["ip"]:
            found.append(entry)
    return found


async def _ping(ip: str, gate: asyncio.Semaphore) -> bool:
    async with gate:
        code, _ = await run(["ping", "-c", "1", "-W", "1", "-n", ip], Path.home(), 5)
        return code == 0


async def discover(network: str, options: dict[str, Any]) -> list[dict[str, str]]:
    """Devices that answer on one of YOUR networks: ``nmap -sn`` (a ping sweep, no
    port scan) when installed, else ``ping``; MAC addresses from the ARP table."""
    net = network_of(network, options)
    if options.get("nmap", True) and find_executable("nmap"):
        _, out = await run(["nmap", "-sn", "-oX", "-", str(net)], Path.home(), 600)
        found = parse_nmap_hosts(out)
    else:
        hosts = [str(ip) for ip in net.hosts()]
        gate = asyncio.Semaphore(64)
        alive = await asyncio.gather(*(_ping(ip, gate) for ip in hosts))
        found = [
            {"ip": ip, "mac": "", "vendor": "", "name": ""}
            for ip, up in zip(hosts, alive, strict=True)
            if up
        ]
    arp = {d["ip"]: d for d in devices()}
    for entry in found:
        known = arp.get(entry["ip"], {})
        entry["mac"] = entry["mac"] or known.get("mac", "")
        if not entry["name"]:
            entry["name"] = known.get("name", "")
    return found


# ------------------------------------------------------------------ logs ---


async def log_findings(hours: int = 24) -> dict[str, Any]:
    """Failed logins (ssh, sudo, login) and error counts from the systemd journal."""
    if not find_executable("journalctl"):
        return {"available": False}
    since = f"-{hours}h"
    code, out = await run(
        [
            "journalctl",
            "-q",
            "--no-pager",
            "--since",
            since,
            "-o",
            "cat",
            "--grep",
            "Failed password|Invalid user|authentication failure|incorrect password attempt",
        ],
        Path.home(),
        60,
    )
    failed = [line for line in out.splitlines() if line.strip()] if code in (0, 1) else []
    sources: dict[str, int] = {}
    for line in failed:
        if " from " in line:
            ip = line.split(" from ", 1)[1].split()[0]
            sources[ip] = sources.get(ip, 0) + 1
    _, errors = await run(
        ["journalctl", "-q", "--no-pager", "--since", since, "-p", "3", "-o", "cat"],
        Path.home(),
        60,
    )
    error_lines = [line for line in errors.splitlines() if line.strip()]
    readable = not ("No journal files" in out or "insufficient permissions" in errors.lower())
    return {
        "available": True,
        "readable": readable,
        "failed_logins": len(failed),
        "sources": dict(sorted(sources.items(), key=lambda kv: -kv[1])[:10]),
        "errors": len(error_lines),
        "error_samples": list(dict.fromkeys(error_lines))[:5],
    }


async def firewall() -> str:
    """Which firewall service is active (Dia never changes its rules)."""
    if not find_executable("systemctl"):
        return "unknown"
    for unit in ("firewalld", "ufw", "nftables", "iptables"):
        code, out = await run(["systemctl", "is-active", unit], Path.home(), 10)
        if out.strip() == "active":
            return unit
    return "none"


# ---------------------------------------------------------- dependencies ---


@dataclass
class Vulnerability:
    package: str
    version: str
    id: str
    severity: str = ""
    fixed: str = ""
    summary: str = ""


async def audit_dependencies(path: Path) -> tuple[str, list[Vulnerability]]:
    """(tool used, vulnerabilities) for a project; tool "" when none applies."""
    if find_executable("osv-scanner"):
        code, out = await run(
            ["osv-scanner", "scan", "source", "--format", "json", "-r", str(path)], path, 600
        )
        if code not in (0, 1) or not out.lstrip().startswith("{"):
            code, out = await run(["osv-scanner", "--format", "json", "-r", str(path)], path, 600)
        try:
            data = json.loads(out[out.index("{") :])
        except ValueError:
            data = {}
        vulns = []
        for result in data.get("results", []):
            for pkg in result.get("packages", []):
                info = pkg.get("package", {})
                for v in pkg.get("vulnerabilities", []):
                    severity = (v.get("database_specific") or {}).get("severity", "")
                    vulns.append(
                        Vulnerability(
                            info.get("name", ""),
                            info.get("version", ""),
                            v.get("id", ""),
                            severity,
                            summary=v.get("summary", "")[:200],
                        )
                    )
        return "osv-scanner", vulns
    if (path / "package-lock.json").exists() and find_executable("npm"):
        _, out = await run(["npm", "audit", "--json"], path, 300)
        try:
            data = json.loads(out)
        except ValueError:
            return "npm audit", []
        vulns = [
            Vulnerability(
                name,
                str(v.get("range", "")),
                str(v.get("via", [{}])[0].get("source", ""))
                if isinstance(v.get("via", [None])[0], dict)
                else "",
                v.get("severity", ""),
                "yes" if v.get("fixAvailable") else "",
            )
            for name, v in data.get("vulnerabilities", {}).items()
        ]
        return "npm audit", vulns
    if (path / "Cargo.lock").exists() and find_executable("cargo-audit"):
        _, out = await run(["cargo", "audit", "--json"], path, 300)
        try:
            data = json.loads(out)
        except ValueError:
            return "cargo audit", []
        return "cargo audit", [
            Vulnerability(
                v["package"]["name"],
                v["package"]["version"],
                v["advisory"]["id"],
                fixed=", ".join(v.get("versions", {}).get("patched", [])),
                summary=v["advisory"].get("title", ""),
            )
            for v in data.get("vulnerabilities", {}).get("list", [])
        ]
    requirements = path / "requirements.txt"
    if (requirements.exists() or (path / "pyproject.toml").exists()) and find_executable(
        "pip-audit"
    ):
        argv = ["pip-audit", "-f", "json"] + (
            ["-r", str(requirements)] if requirements.exists() else [str(path)]
        )
        _, out = await run(argv, path, 600)
        try:
            data = json.loads(out[out.index("{") :] if "{" in out else out)
        except ValueError:
            return "pip-audit", []
        deps = data.get("dependencies", data if isinstance(data, list) else [])
        return "pip-audit", [
            Vulnerability(
                d["name"],
                d.get("version", ""),
                v["id"],
                fixed=", ".join(v.get("fix_versions", [])),
                summary=v.get("description", "")[:200],
            )
            for d in deps
            for v in d.get("vulns", [])
        ]
    return "", []


def fix_prompt(tool: str, vulns: list[Vulnerability]) -> str:
    listing = "\n".join(
        f"- {v.package} {v.version}: {v.id}"
        + (f" (fixed in {v.fixed})" if v.fixed else "")
        + (f" {v.summary}" if v.summary else "")
        for v in vulns[:40]
    )
    return (
        f"{tool} reports these vulnerable dependencies. Update them to fixed versions, "
        "keeping the project working (adjust code if an update needs it), and run the "
        f"tests.\n\n{listing}"
    )


# ---------------------------------------------------------------- report ---


@dataclass
class Report:
    listening: list[dict[str, Any]] = field(default_factory=list)
    new_exposed: list[dict[str, Any]] = field(default_factory=list)
    firewall: str = ""
    logs: dict[str, Any] = field(default_factory=dict)
    devices: list[dict[str, str]] = field(default_factory=list)
    discovered: dict[str, list[dict[str, str]]] = field(default_factory=dict)  # network -> hosts
    new_devices: list[dict[str, str]] = field(default_factory=list)
    projects: dict[str, dict[str, Any]] = field(default_factory=dict)  # name -> tool, vulns

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _baseline_path(dia: Orchestrator) -> Path:
    return dia.config.data_dir / "security.json"


def new_exposed_ports(dia: Orchestrator, current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exposed ports not seen before (the first look only records the baseline)."""
    path = _baseline_path(dia)
    exposed = {f"{s['address']}:{s['port']}" for s in current if s["exposed"]}
    data = _baseline(path)
    first = "exposed" not in data
    known = set(data.get("exposed", []))
    data["exposed"] = sorted(known | exposed)
    _save_baseline(path, data)
    if first:
        return []
    return [s for s in current if s["exposed"] and f"{s['address']}:{s['port']}" not in known]


def _baseline(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _save_baseline(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def new_devices(dia: Orchestrator, found: list[dict[str, str]]) -> list[dict[str, str]]:
    """Devices not seen on your network before (the first sweep records the baseline)."""
    path = _baseline_path(dia)
    data = _baseline(path)
    first = "devices" not in data
    known = set(data.get("devices", []))
    data["devices"] = sorted(known | {d["mac"] or d["ip"] for d in found})
    _save_baseline(path, data)
    return [] if first else [d for d in found if (d["mac"] or d["ip"]) not in known]


async def report(dia: Orchestrator, projects: bool = True) -> Report:
    current = listening()
    result = Report(
        listening=current,
        new_exposed=new_exposed_ports(dia, current),
        firewall=await firewall(),
        logs=await log_findings(int(dia.config.section("security").get("log_hours", 24))),
        devices=devices(),
    )
    options = dia.config.section("security")
    if options.get("discover", True):
        for network in options.get("networks", []):
            try:
                result.discovered[network] = await discover(network, options)
            except (NotAuthorized, ValueError) as exc:
                log.warning("network %s: %s", network, exc)
        if result.discovered:
            found = [d for hosts in result.discovered.values() for d in hosts]
            result.new_devices = new_devices(dia, found)
        if result.new_devices:
            listing = ", ".join(d["name"] or d["ip"] for d in result.new_devices)
            await dia.emit("security", None, f"new devices on your network: {listing}")
    if projects:
        for name, project in dia.config.projects.items():
            if project.path.is_dir():
                tool, vulns = await audit_dependencies(project.path)
                if tool:
                    result.projects[name] = {"tool": tool, "vulns": [asdict(v) for v in vulns]}
    return result


def describe(rep: Report, language: str) -> str:
    pl = language == "pl"
    exposed = [s for s in rep.listening if s["exposed"]]
    lines = []
    if exposed:
        ports = ", ".join(
            f"{s['port']}" + (f" ({s['process'].split(' ')[0]})" if s["process"] else "")
            for s in exposed[:10]
        )
        lines.append(
            ("Otwarte na zewnątrz porty: " if pl else "Ports open to the network: ") + ports
        )
    else:
        lines.append("Nic nie nasłuchuje na zewnątrz." if pl else "Nothing listens to the network.")
    if rep.new_exposed:
        lines.append(
            ("NOWE od ostatniego razu: " if pl else "NEW since last time: ")
            + ", ".join(str(s["port"]) for s in rep.new_exposed)
        )
    lines.append(
        ("Zapora: " if pl else "Firewall: ")
        + (rep.firewall if rep.firewall != "none" else ("brak aktywnej" if pl else "none active"))
    )
    logs = rep.logs
    if logs.get("available"):
        if not logs.get("readable", True):
            lines.append(
                "Brak dostępu do dziennika systemu (grupa wheel/systemd-journal)."
                if pl
                else "No access to the system journal (wheel/systemd-journal group)."
            )
        else:
            text = (
                f"Nieudane logowania (24 h): {logs['failed_logins']}"
                if pl
                else f"Failed logins (24 h): {logs['failed_logins']}"
            )
            if logs["sources"]:
                text += " — " + ", ".join(
                    f"{ip} ×{n}" for ip, n in list(logs["sources"].items())[:3]
                )
            lines.append(
                text
                + (
                    f"; błędy systemu: {logs['errors']}"
                    if pl
                    else f"; system errors: {logs['errors']}"
                )
            )
    for network, hosts in rep.discovered.items():
        lines.append(
            f"Sieć {network}: {len(hosts)} urządzeń"
            if pl
            else f"Network {network}: {len(hosts)} devices"
        )
    if rep.new_devices:
        listing = ", ".join(
            (d["name"] or d["ip"]) + (f" ({d['vendor']})" if d.get("vendor") else "")
            for d in rep.new_devices[:10]
        )
        lines.append(
            ("NOWE urządzenia w sieci: " if pl else "NEW devices on the network: ") + listing
        )
    for name, info in rep.projects.items():
        count = len(info["vulns"])
        if count:
            lines.append(
                f"{name}: {count} podatnych zależności ({info['tool']})"
                if pl
                else f"{name}: {count} vulnerable dependencies ({info['tool']})"
            )
    return "\n".join(lines)
