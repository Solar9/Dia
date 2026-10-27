import os
import time
from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.brains.rules import RulesBrain
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.tidy import Tidy, TidyError


def make(tmp_path: Path) -> tuple[Orchestrator, Path]:
    downloads = tmp_path / "Pobrane"
    downloads.mkdir()
    for name in ("zdjęcie.jpg", "faktura.pdf", "gra.AppImage", "notatki.xyz", "film.mp4.part"):
        (downloads / name).write_text(name)
    (downloads / "projekt").mkdir()
    (downloads / ".ukryty.pdf").write_text("x")
    old = downloads / "stary.zip"
    old.write_text("old")
    month_ago = time.time() - 60 * 86400
    os.utime(old, (month_ago, month_ago))
    (downloads / "Obrazy").mkdir()
    (downloads / "Obrazy" / "zdjęcie.jpg").write_text("already there")
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "language": "pl"},
        "tidy": {"folders": [str(downloads)]},
    }
    return Orchestrator(parse_config(raw), use_memory=False), downloads


def test_preview_apply_undo(tmp_path: Path) -> None:
    dia, downloads = make(tmp_path)
    tidy = Tidy(dia)
    plan = tidy.plan()
    moves = {m["from"]: m["to"] for m in plan["moves"]}
    stary = f"Archiwum/{time.strftime('%Y-%m', time.localtime(time.time() - 60 * 86400))}"
    assert moves == {
        "faktura.pdf": "Dokumenty/faktura.pdf",
        "gra.AppImage": "Instalatory/gra.AppImage",
        "stary.zip": f"{stary}/stary.zip",
        "zdjęcie.jpg": "Obrazy/zdjęcie.jpg",
    }
    assert (downloads / "faktura.pdf").exists()  # a preview moves nothing

    applied = tidy.apply(plan["id"])
    assert len(applied["moved"]) == 4
    assert (downloads / "Dokumenty" / "faktura.pdf").exists()
    assert (downloads / "Obrazy" / "zdjęcie (2).jpg").read_text() == "zdjęcie.jpg"  # no overwrite
    assert (downloads / "Obrazy" / "zdjęcie.jpg").read_text() == "already there"
    assert (downloads / "notatki.xyz").exists() and (downloads / "film.mp4.part").exists()
    with pytest.raises(TidyError):
        tidy.apply(plan["id"])  # once

    tidy.undo()
    assert (downloads / "faktura.pdf").exists() and (downloads / "zdjęcie.jpg").exists()
    assert not (downloads / "Dokumenty").exists()
    assert (downloads / "Obrazy" / "zdjęcie.jpg").read_text() == "already there"


def test_only_allowed_folders(tmp_path: Path) -> None:
    dia, _ = make(tmp_path)
    with pytest.raises(TidyError, match="not one of the folders"):
        Tidy(dia).plan(str(tmp_path))
    with pytest.raises(TidyError):
        Tidy(dia).load("../../etc")


async def test_by_voice_it_asks_first(tmp_path: Path) -> None:
    dia, downloads = make(tmp_path)
    assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
    ask = (await assistant.handle("Dia, posprzątaj pobrane")).text
    assert ask.startswith("Przeniosę 4 pliki") and ask.endswith("Przenieść?")
    assert (downloads / "faktura.pdf").exists()
    assert (await assistant.handle("tak")).text.startswith("Gotowe, przeniesione: 4 pliki")
    assert (await assistant.handle("cofnij porządki")).text.endswith("4 pliki.")
    assert (downloads / "faktura.pdf").exists()


def test_polish_plural() -> None:
    from dia.tidy import files_pl

    assert [files_pl(n) for n in (1, 2, 5, 12, 22, 25)] == [
        "1 plik",
        "2 pliki",
        "5 plików",
        "12 plików",
        "22 pliki",
        "25 plików",
    ]
