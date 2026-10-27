from pathlib import Path

import pytest

from dia.agents import Mode
from dia.config import ConfigError, parse_config
from dia.memory.markdown import MarkdownMemory
from dia.orchestrator import Orchestrator


def setup(tmp_path: Path, repo: Path, memory: dict | None, argv: list[str]) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "fake"},
        "agents": {"fake": {"type": "command", "argv": argv}},
        "projects": {"nova": {"path": str(repo)}},
    }
    if memory is not None:
        raw["memory"] = memory
    return Orchestrator(parse_config(raw))


def test_memory_is_optional(tmp_path: Path) -> None:
    assert parse_config({}).memory() is None
    assert parse_config({"memory": {"vault": "x", "enabled": False}}).memory() is None
    assert isinstance(parse_config({"memory": {"vault": str(tmp_path)}}).memory(), MarkdownMemory)
    assert isinstance(
        parse_config({"memory": {"type": "obsidian", "vault": str(tmp_path)}}).memory(),
        MarkdownMemory,
    )
    with pytest.raises(ConfigError, match="requires 'vault'"):
        parse_config({"memory": {}}).memory()


async def test_notes_reach_the_agent_and_tasks_are_journaled(tmp_path: Path, repo: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "Dia" / "Projects").mkdir(parents=True)
    (vault / "Dia" / "Profile.md").write_text("---\ntags: [x]\n---\nI prefer small commits.\n")
    (vault / "Dia" / "Projects" / "nova.md").write_text("# Nova\n\nGodot 4 co-op shooter.\n")
    (vault / "Private.md").write_text("secret")

    # The fake agent echoes the prompt it received.
    orch = setup(tmp_path, repo, {"vault": str(vault)}, ["sh", "-c", 'echo "$0"', "{prompt}"])
    report = await orch.run_task("nova", "Describe the game", mode=Mode.READ_ONLY)
    seen = report.task.summary

    assert "I prefer small commits." in seen and "Godot 4 co-op shooter." in seen
    assert "tags:" not in seen and "secret" not in seen
    assert seen.rstrip().endswith("Describe the game")
    assert report.task.prompt == "Describe the game"  # history keeps the user's words

    journal = list((vault / "Dia" / "Journal").glob("*.md"))
    assert len(journal) == 1
    entry = journal[0].read_text()
    assert "[[Dia/Projects/nova|nova]] · Describe the game" in entry
    assert "status: **done**" in entry and report.task.id in entry

    await orch.run_task("nova", "Second task", mode=Mode.READ_ONLY)
    text = journal[0].read_text()
    assert text.count("\n## ") == 2 and text.startswith("# ")  # appended, header once


async def test_missing_project_note_becomes_a_template(tmp_path: Path, repo: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    orch = setup(tmp_path, repo, {"vault": str(vault)}, ["sh", "-c", 'echo "$0"', "{prompt}"])
    report = await orch.run_task("nova", "hi", mode=Mode.READ_ONLY)

    note = vault / "Dia" / "Projects" / "nova.md"
    assert "## Architecture" in note.read_text()
    assert report.task.summary == "hi"  # an unfilled template adds no context

    note.write_text("# Nova\nuser text\n")
    await orch.run_task("nova", "again", mode=Mode.READ_ONLY)
    assert note.read_text() == "# Nova\nuser text\n"  # never overwritten


async def test_broken_memory_only_warns(tmp_path: Path, repo: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Dia").write_text("a file where Dia expects a folder")
    orch = setup(tmp_path, repo, {"vault": str(vault)}, ["echo", "ok"])
    report = await orch.run_task("nova", "x", mode=Mode.READ_ONLY)
    assert report.task.status == "done" and report.task.summary == "ok"
    assert any(w.startswith("memory:") for w in report.warnings)


def make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    files = {
        "Gry/Nova/Ekwipunek.md": "# Ekwipunek\n\nSystem ekwipunku oparty na slotach.\n\nInne.",
        "Gry/Nova/Walka.md": "Walka wręcz i strzelanie.",
        "Przepisy/Pierogi.md": "Ciasto, farsz, ekwipunek kuchenny.",
        "Prywatne/Pamietnik.md": "Mój ekwipunek na wakacje.",
        "Zdrowie.md": "---\ndia: private\n---\nekwipunek apteczki",
        ".obsidian/workspace.md": "ekwipunek",
        "Dia/Projects/nova.md": "# Nova\n\nGodot 4.",
    }
    for rel, text in files.items():
        (vault / rel).parent.mkdir(parents=True, exist_ok=True)
        (vault / rel).write_text(text)
    return vault


def test_vault_search_respects_privacy(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    memory = MarkdownMemory({"vault": str(vault), "search": "vault", "exclude": ["Prywatne/**"]})
    hits = memory.search("dodaj nowe przedmioty do ekwipunku")
    paths = [h.path.as_posix() for h in hits]

    assert paths[0] == "Gry/Nova/Ekwipunek.md"  # inflected form + title match
    assert "Przepisy/Pierogi.md" in paths
    assert not any(p.startswith(("Prywatne/", ".obsidian/")) or p == "Zdrowie.md" for p in paths)
    assert hits[0].snippet == "System ekwipunku oparty na slotach."
    assert hits[0].link == "[[Gry/Nova/Ekwipunek]]"


def test_search_scope_defaults_to_dia_folder(tmp_path: Path) -> None:
    vault = make_vault(tmp_path)
    assert MarkdownMemory({"vault": str(vault)}).search("ekwipunek") == []
    assert MarkdownMemory({"vault": str(vault), "search": "off"}).search("Godot") == []
    with pytest.raises(ValueError):
        MarkdownMemory({"vault": str(vault), "search": "everything"})


async def test_related_notes_reach_the_agent(tmp_path: Path, repo: Path) -> None:
    vault = make_vault(tmp_path)
    memory = {"vault": str(vault), "search": "vault", "exclude": ["Prywatne"]}
    orch = setup(tmp_path, repo, memory, ["sh", "-c", 'echo "$0"', "{prompt}"])
    report = await orch.run_task("nova", "Popraw system ekwipunku", mode=Mode.READ_ONLY)
    seen = report.task.summary
    assert "## Related notes" in seen and "[[Gry/Nova/Ekwipunek]]" in seen
    assert seen.count("Godot 4.") == 1  # the project note isn't repeated as a search hit
    assert "Prywatne" not in seen and "wakacje" not in seen


def test_browsing_and_editing_stays_in_the_dia_folder(tmp_path: Path) -> None:
    from dia.memory.markdown import MarkdownMemory

    vault = tmp_path / "vault"
    (vault / "Dia" / "Projects").mkdir(parents=True)
    (vault / "Dia" / "Projects" / "nova.md").write_text("# Nova\n")
    (vault / "Dia" / "Profile.md").write_text("me\n")
    (vault / "Secret.md").write_text("outside\n")
    memory = MarkdownMemory({"vault": str(vault)})
    kinds = {n["path"]: n["kind"] for n in memory.notes()}
    assert kinds == {"Profile.md": "profile", "Projects/nova.md": "project"}
    memory.write_note("Projects/nova.md", "# Nova\n\nGodot 4.\n")
    assert memory.read_note("Projects/nova.md").endswith("Godot 4.\n")
    for bad in ("../Secret.md", "/etc/passwd", "Projects/nova.txt"):
        with pytest.raises(ValueError):
            memory.read_note(bad)
        with pytest.raises(ValueError):
            memory.write_note(bad, "x")
