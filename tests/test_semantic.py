import hashlib
import os
from pathlib import Path

from dia.memory.markdown import MarkdownMemory
from dia.memory.search import Hit
from dia.memory.semantic import SemanticIndex, chunks, fuse

# Concepts the fake embedder knows: words that mean the same land on one axis.
SYNONYMS = {
    "ekwipunek": "inventory",
    "ekwipunku": "inventory",
    "przedmioty": "items",
    "zapis": "save",
    "zapisie": "save",
    "saving": "save",
}


def fake_embed(texts: list[str]) -> list[list[float]]:
    out = []
    for text in texts:
        vector = [0.0] * 64
        for word in text.lower().split():
            word = SYNONYMS.get(word.strip(".,:#"), word.strip(".,:#"))
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
        out.append(vector)
    return out


def write(vault: Path, rel: str, text: str) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_chunks_keep_headings() -> None:
    body = "# Combat\n\n" + "\n\n".join(f"Paragraph {i} " + "x" * 300 for i in range(6))
    parts = chunks(body)
    assert len(parts) > 1 and all(p.startswith("# Combat") for p in parts)


def test_index_finds_by_meaning_and_stays_fresh(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = write(vault, "Dia/Bugs.md", "Ekwipunek gubi przedmioty po zapisie.")
    write(vault, "Dia/Music.md", "Soundtrack ideas for the menu.")
    write(vault, "Dia/Secret.md", "---\ndia: private\n---\ninventory passwords")
    write(vault, ".obsidian/x.md", "inventory")
    calls = []

    def counting(texts):
        calls.append(len(texts))
        return fake_embed(texts)

    index = SemanticIndex(tmp_path / "i.db", vault, vault / "Dia", [], counting, "fake")
    assert index.update() == 3
    hits = index.search("inventory items lost after saving")
    assert hits[0].path == Path("Dia/Bugs.md")
    assert all(h.path != Path("Dia/Secret.md") for h in hits)

    assert index.update() == 0  # nothing changed: nothing embedded
    note.write_text("Combat parry timing notes.")
    os.utime(note, (note.stat().st_atime + 5, note.stat().st_mtime + 5))
    assert index.update() == 1
    top = index.search("parry timing")[0]
    assert top.path == Path("Dia/Bugs.md") and "parry" in top.snippet
    (vault / "Dia/Music.md").unlink()
    index.update()
    assert all(h.path != Path("Dia/Music.md") for h in index.search("soundtrack menu"))


def test_fuse_prefers_notes_both_searches_found() -> None:
    a = [Hit(Path("x.md"), 1, "x"), Hit(Path("y.md"), 1, "y")]
    b = [Hit(Path("y.md"), 1, "y2"), Hit(Path("z.md"), 1, "z")]
    assert [h.path.name for h in fuse(a, b, limit=3)] == ["y.md", "x.md", "z.md"]


def test_memory_falls_back_to_keywords_when_embeddings_fail(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write(vault, "Dia/Bugs.md", "The inventory loses items.")
    memory = MarkdownMemory(
        {
            "vault": str(vault),
            "semantic": {"base_url": "http://127.0.0.1:9/v1"},
            "index_dir": str(tmp_path),
        }
    )
    hits = memory.search("inventory")
    assert [h.path for h in hits] == [Path("Dia/Bugs.md")]
