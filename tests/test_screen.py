from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.brains.rules import RulesBrain
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.screen import look


def make(tmp_path: Path) -> Orchestrator:
    # The "screenshot tool" writes a fake PNG; the "agent" answers from the file it sees.
    capture = ["sh", "-c", 'printf PNG > "$0"', "{output}"]
    viewer = ["sh", "-c", "test -f screenshot.png && echo 'Błąd w player.gd, linia 12'"]
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "d"), "language": "pl", "default_agent": "v"},
            "agents": {"v": {"type": "command", "argv": viewer}},
            "screen": {"command": capture},
        }
    )
    return Orchestrator(config, use_memory=False)


async def test_screen_is_off_until_switched_on(tmp_path: Path) -> None:
    dia = make(tmp_path)
    assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
    refused = (await assistant.handle("co jest na ekranie?")).text
    assert "wyłączony" in refused
    with pytest.raises(PermissionError):
        await look(dia, "x")

    await assistant.handle("możesz patrzeć na ekran")
    assert dia.screen_enabled
    events = []

    async def listen(event):
        events.append(event.message)

    dia.listeners.append(listen)
    answer = (await assistant.handle("co jest na ekranie?")).text
    assert answer == "Błąd w player.gd, linia 12"
    assert events[:1] == ["looking"] and "done" in events
    assert not any((tmp_path / "d" / "screen").iterdir())  # screenshot deleted
    assert [r["action"] for r in dia.store.audit(action="screen")][:2] == [
        "screen.look",
        "screen.access",
    ]

    await assistant.handle("nie patrz na ekran")
    assert not dia.screen_enabled


def test_configured_command_as_text_gets_the_file_name() -> None:
    from dia.screen import capture_command

    assert capture_command("import -window 0x2a") == ["import", "-window", "0x2a", "{output}"]
    assert capture_command(["grim", "{output}"]) == ["grim", "{output}"]
