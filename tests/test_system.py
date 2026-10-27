from pathlib import Path

import pytest

from dia import system
from dia.config import parse_config
from dia.orchestrator import Orchestrator


@pytest.fixture
def fake_sys(tmp_path: Path, monkeypatch) -> Path:
    hw = tmp_path / "sys" / "class" / "hwmon" / "hwmon0"
    hw.mkdir(parents=True)
    (hw / "name").write_text("coretemp\n")
    (hw / "temp1_input").write_text("93000\n")
    (hw / "temp1_label").write_text("Package id 0\n")
    (hw / "temp2_input").write_text("61000\n")
    (hw / "temp2_label").write_text("Core 0\n")
    bat = tmp_path / "sys" / "class" / "power_supply" / "BAT0"
    bat.mkdir(parents=True)
    (bat / "capacity").write_text("12\n")
    (bat / "status").write_text("Discharging\n")
    monkeypatch.setattr(system, "SYS", tmp_path / "sys")
    return tmp_path


def test_sensors_and_battery(fake_sys: Path) -> None:
    temps = system.temperatures()
    assert {"name": "coretemp Package id 0", "celsius": 93.0, "cpu": True} in temps
    assert system.battery() == {"percent": 12, "status": "Discharging"}


async def test_snapshot_and_limits(fake_sys: Path) -> None:
    snap = await system.snapshot(0.05)
    assert 0 <= snap.cpu_percent <= 100 and snap.memory["total_gb"] > 0
    assert snap.cpu_temp == 93.0
    kinds = [k for k, _ in system.check_limits(snap, {"cpu_temp": 90, "disk_used": 101})]
    assert "cpu_temp" in kinds and "battery" in kinds


async def test_watcher_alerts_once_per_cooldown(fake_sys: Path, tmp_path: Path) -> None:
    dia = Orchestrator(
        parse_config({"dia": {"data_dir": str(tmp_path / "d")}, "system": {"disk_used": 101}}),
        use_memory=False,
    )
    events = []

    async def listen(event):
        events.append(event)

    dia.listeners.append(listen)
    watcher = system.SystemWatcher(dia)
    first = await watcher.poll()
    assert any("93°C" in m for m in first) and any("12%" in m for m in first)
    assert await watcher.poll() == []  # still hot, but already said
    assert {e.data["kind"] for e in events} == {"cpu_temp", "battery"}


async def test_processes_lists_this_one() -> None:
    import os

    procs = await system.processes(limit=10_000, sample=0.05, sort="memory")
    assert any(p.pid == os.getpid() for p in procs)
