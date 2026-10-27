import asyncio
import subprocess
import sys
from pathlib import Path

from dia import computer
from dia.assistant import Assistant
from dia.brains.rules import RulesBrain
from dia.config import parse_config
from dia.orchestrator import Orchestrator


async def test_ending_a_process_needs_a_yes(tmp_path: Path) -> None:
    script = tmp_path / "diatestsleeper"
    script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(60)\n")
    script.chmod(0o755)
    proc = subprocess.Popen([str(script)])
    try:
        dia = Orchestrator(
            parse_config({"dia": {"data_dir": str(tmp_path / "d"), "language": "pl"}}),
            use_memory=False,
        )
        assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
        await asyncio.sleep(0.2)
        ask = (await assistant.handle("Dia, zamknij diatestsleeper")).text
        assert ask.startswith("Zamknąć diatestsleeper") and str(proc.pid) in ask
        assert proc.poll() is None  # nothing happens before the answer
        assert (await assistant.handle("nie")).text == "Dobrze, nie robię tego."
        assert proc.poll() is None
        await assistant.handle("Dia, zamknij diatestsleeper")
        done = (await assistant.handle("tak")).text
        assert done.startswith("Zamknięte")
        assert proc.wait(5) is not None
        assert dia.store.audit(action="process.end")[0]["target"] == str(proc.pid)

        nothing = (await assistant.handle("zamknij niematakiegoprogramu")).text
        assert "Nie widzę" in nothing
    finally:
        proc.kill()


def test_refuses_pid_one() -> None:
    import pytest

    with pytest.raises(ValueError):
        computer.end_process(1)


async def test_updates_parse_checkupdates(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "checkupdates").write_text(
        "#!/bin/sh\necho 'linux 6.1-1 -> 6.2-1'\necho 'godot 4.6 -> 4.7'\n"
    )
    (bin_dir / "checkupdates").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    found = await computer.updates()
    assert found[0].source == "pacman" and found[0].packages == ["linux", "godot"]
    assert found[0].command == "sudo pacman -Syu"
