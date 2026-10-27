import asyncio
from pathlib import Path

import pytest

from dia import security
from dia.config import parse_config
from dia.orchestrator import Orchestrator


def test_hex_addresses() -> None:
    assert security._hex_address("0100007F") == "127.0.0.1"
    assert security._hex_address("00000000") == "0.0.0.0"
    assert security._hex_address("00000000000000000000000001000000") == "::1"


async def test_listening_sees_an_open_port_and_scan_finds_it() -> None:
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        assert any(s["port"] == port and not s["exposed"] for s in security.listening())
        # The connect scan (nmap -sV, when a machine has it, takes minutes).
        found = await security.scan("localhost", {"ports": [port], "nmap": False})
        assert any(p["port"] == port for p in found)
    finally:
        server.close()


async def test_scans_only_your_hosts() -> None:
    with pytest.raises(security.NotAuthorized):
        await security.scan("example.com", {"hosts": ["192.168.1.10"]})
    assert security.authorized("192.168.1.10", {"hosts": ["192.168.1.10"]})


def test_new_exposed_ports_after_the_baseline(tmp_path: Path) -> None:
    dia = Orchestrator(parse_config({"dia": {"data_dir": str(tmp_path)}}), use_memory=False)
    ssh = {"address": "0.0.0.0", "port": 22, "exposed": True, "process": "sshd"}
    web = {"address": "0.0.0.0", "port": 8080, "exposed": True, "process": "python"}
    assert security.new_exposed_ports(dia, [ssh]) == []  # first look: baseline
    assert security.new_exposed_ports(dia, [ssh, web]) == [web]
    assert security.new_exposed_ports(dia, [ssh, web]) == []


async def test_dependency_audit_with_osv_scanner(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    report = (
        '{"results": [{"packages": [{"package": {"name": "requests", "version": "2.19.0"},'
        ' "vulnerabilities": [{"id": "GHSA-x", "summary": "Leaks auth",'
        ' "database_specific": {"severity": "HIGH"}}]}]}]}'
    )
    (bin_dir / "osv-scanner").write_text(f"#!/bin/sh\necho '{report}'\nexit 1\n")
    (bin_dir / "osv-scanner").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    tool, vulns = await security.audit_dependencies(tmp_path)
    assert tool == "osv-scanner"
    assert (vulns[0].package, vulns[0].id, vulns[0].severity) == ("requests", "GHSA-x", "HIGH")
    assert "requests 2.19.0: GHSA-x" in security.fix_prompt(tool, vulns)


def test_report_text() -> None:
    rep = security.Report(
        listening=[{"address": "0.0.0.0", "port": 22, "exposed": True, "process": "sshd (1)"}],
        firewall="none",
        logs={
            "available": True,
            "readable": True,
            "failed_logins": 3,
            "sources": {"203.0.113.9": 3},
            "errors": 0,
        },
        projects={"nova": {"tool": "osv-scanner", "vulns": [{}, {}]}},
    )
    text = security.describe(rep, "pl")
    assert "22 (sshd)" in text and "Zapora: brak aktywnej" in text
    assert "203.0.113.9 ×3" in text and "nova: 2 podatnych" in text


NMAP_XML = """<?xml version="1.0"?>
<nmaprun>
<host><status state="up"/><address addr="192.168.1.1" addrtype="ipv4"/>
<address addr="AA:BB:CC:00:11:22" addrtype="mac" vendor="TP-Link"/>
<hostnames><hostname name="router.lan"/></hostnames></host>
<host><status state="up"/><address addr="192.168.1.50" addrtype="ipv4"/></host>
<host><status state="down"/><address addr="192.168.1.99" addrtype="ipv4"/></host>
</nmaprun>"""


def test_parse_nmap_hosts() -> None:
    hosts = security.parse_nmap_hosts(NMAP_XML)
    assert hosts == [
        {
            "ip": "192.168.1.1",
            "mac": "aa:bb:cc:00:11:22",
            "vendor": "TP-Link",
            "name": "router.lan",
        },
        {"ip": "192.168.1.50", "mac": "", "vendor": "", "name": ""},
    ]
    assert security.parse_nmap_hosts("not xml") == []


async def test_discovery_only_on_your_own_private_networks() -> None:
    options = {"networks": ["192.168.1.0/24", "8.8.8.0/24", "10.0.0.0/8"]}
    with pytest.raises(security.NotAuthorized, match="not listed"):
        await security.discover("192.168.2.0/24", options)
    with pytest.raises(security.NotAuthorized, match="private"):
        await security.discover("8.8.8.0/24", options)
    with pytest.raises(security.NotAuthorized, match="too large"):
        await security.discover("10.0.0.0/8", options)


async def test_discovery_with_nmap(monkeypatch) -> None:
    calls = []

    async def fake_run(argv, cwd, timeout, **kw):
        calls.append(argv)
        return 0, NMAP_XML

    monkeypatch.setattr(security, "run", fake_run)
    monkeypatch.setattr(security, "find_executable", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(security, "devices", lambda: [])
    found = await security.discover("192.168.1.0/24", {"networks": ["192.168.1.0/24"]})
    assert calls == [["nmap", "-sn", "-oX", "-", "192.168.1.0/24"]]  # a ping sweep, no ports
    assert [d["ip"] for d in found] == ["192.168.1.1", "192.168.1.50"]


def test_new_devices_after_the_first_sweep(tmp_path: Path) -> None:
    dia = Orchestrator(parse_config({"dia": {"data_dir": str(tmp_path)}}), use_memory=False)
    router = {"ip": "192.168.1.1", "mac": "aa:bb", "vendor": "", "name": "router"}
    phone = {"ip": "192.168.1.7", "mac": "cc:dd", "vendor": "", "name": ""}
    assert security.new_devices(dia, [router]) == []  # the baseline
    assert security.new_devices(dia, [router, phone]) == [phone]
    assert security.new_devices(dia, [router, phone]) == []
    # The exposed-port baseline lives in the same file and survives.
    assert security.new_exposed_ports(dia, []) == []
    assert security.new_devices(dia, [router]) == []
