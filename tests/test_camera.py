from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.brains.rules import RulesBrain
from dia.camera import look
from dia.config import parse_config
from dia.orchestrator import Orchestrator


def make(tmp_path: Path) -> Orchestrator:
    # The "camera" writes a fake JPEG; the "agent" answers from the photo it sees.
    camera = ["sh", "-c", 'printf JPG > "$0"', "{output}"]
    viewer = ["sh", "-c", "test -f photo.jpg && echo 'To rezystor 220 Ω'"]
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "d"), "language": "pl", "default_agent": "v"},
            "agents": {"v": {"type": "command", "argv": viewer}},
            "camera": {"command": camera},
        }
    )
    return Orchestrator(config, use_memory=False)


async def test_the_camera_is_off_until_switched_on(tmp_path: Path) -> None:
    dia = make(tmp_path)
    assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
    assert "wyłączona" in (await assistant.handle("co widzisz w kamerze?")).text
    with pytest.raises(PermissionError):
        await look(dia, "x")

    assert "włączona" in (await assistant.handle("Dia, włącz kamerę")).text
    assert dia.camera_enabled
    assert (await assistant.handle("co widzisz w kamerze?")).text == "To rezystor 220 Ω"
    assert not any((tmp_path / "d" / "camera").iterdir())  # the photo is deleted
    actions = [r["action"] for r in dia.store.audit(action="camera")]
    assert actions[:2] == ["camera.look", "camera.access"]

    await assistant.handle("wyłącz kamerę")
    assert not dia.camera_enabled
