from pathlib import Path

from dia.assistant import Assistant
from dia.brains.rules import RulesBrain
from dia.config import parse_config
from dia.orchestrator import Orchestrator


def make(tmp_path: Path) -> Orchestrator:
    board = tmp_path / "board.txt"
    board.write_text("Cześć, co słychać?")
    translator = ["sh", "-c", "echo 'Hi, how are you?'"]
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "language": "pl", "default_agent": "t"},
        "agents": {"t": {"type": "command", "argv": translator}},
        "skills": {
            "clipboard": {
                "read_command": ["cat", str(board)],
                "write_command": ["sh", "-c", f'cat > "{board}"'],
            }
        },
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_read_transform_copy(tmp_path: Path) -> None:
    dia = make(tmp_path)
    board = tmp_path / "board.txt"
    assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
    assert (await assistant.handle("Dia, co mam w schowku?")).text == "Cześć, co słychać?"
    assert dia.store.audit(action="clipboard.read")[0]["detail"] == "read"

    answer = await assistant.run_skill(
        "clipboard", {"action": "transform", "instruction": "translate to English"}
    )
    assert answer == "Gotowe, wynik jest w schowku:\nHi, how are you?"
    assert board.read_text() == "Hi, how are you?"

    await assistant.run_skill("clipboard", {"action": "copy", "text": "https://example.com"})
    assert board.read_text() == "https://example.com"
    board.write_text("")
    assert await assistant.run_skill("clipboard") == "Schowek jest pusty."
