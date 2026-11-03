import re
from pathlib import Path

import pytest

from dia.desktop import appwindow, labels, offline, runtime
from dia.desktop.labels import LABELS, VIEWS, update_line


def test_every_language_has_every_key_and_the_same_placeholders():
    english = LABELS["en"]
    assert set(LABELS) == set(offline.WORDS) == {"en", "pl", "de", "fr", "es", "it", "pt"}
    for language, words in LABELS.items():
        assert set(words) == set(english), (language, set(english) ^ set(words))
        for key, text in words.items():
            assert text.strip(), (language, key)
            holes = sorted(re.findall(r"\{\w+\}", text))
            assert holes == sorted(re.findall(r"\{\w+\}", english[key])), (language, key)
    for words in LABELS.values():
        assert all(view in words for view in VIEWS)
    assert appwindow.LABELS is LABELS and appwindow.VIEWS is VIEWS


def test_the_two_ways_out_are_told_apart():
    # DIA-62: one leaves Dia running, the other stops her.
    for language, words in LABELS.items():
        assert words["quit_window"] != words["quit_all"], language
    assert "keeps running" in LABELS["en"]["quit_window"]
    assert "działa dalej" in LABELS["pl"]["quit_window"]


def test_no_text_of_the_window_is_chosen_by_language_in_the_code():
    source = Path(appwindow.__file__).read_text()
    assert not re.search(r"\bif pl\b|\bpl = ", source)  # "x" if pl else "y": use LABELS
    assert "Zamknij ikonę" not in source and "Usługi Dia" not in source


@pytest.mark.parametrize("language", sorted(LABELS))
def test_the_update_item_tells_the_last_result(language):
    words = LABELS[language]
    assert update_line(words, None) == words["check_updates"]  # nothing checked yet
    assert update_line(words, "up_to_date", "14:05") == f"{words['check_updates']} — " + words[
        "up_to_date"
    ].format(time="14:05")
    failed = update_line(words, "failed", "14:06")
    assert words["check_updates"] in failed and "14:06" in failed
    found = update_line(words, "found", "14:07", "0.1.9")
    assert "0.1.9" in found and words["check_updates"] in found
    assert update_line(words, "checking") == words["checking"]
    assert words["check_source"] in update_line(words, "source")


def test_the_service_words_of_the_tray_exist_in_every_menu_language():
    for language in LABELS:
        for table in (runtime.STATE_LABELS, runtime.VERB_LABELS, runtime.RESULT_LABELS):
            assert all(language in words for words in table.values()), language
    assert labels.LABELS["en"]["ollama"] == "Ollama"


def test_check_for_updates_in_the_tray_shows_each_result(tmp_path: Path):
    """A real tray menu (fresh Qt process): the item checks now and keeps the last result."""
    import json
    import os
    import subprocess
    import sys

    if not appwindow.available():
        pytest.skip("QtWebEngine is not installed")
    script = f"""
import os, json
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from dia.desktop import appwindow, runtime
from dia.release import update
runtime.status = lambda: {{"available": False}}
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
appwindow.server_name = lambda: "dia-labels-test-" + str(os.getpid())
update.editable = lambda: False
update.system_package = lambda: False
outcome = {{"value": None}}
def latest():
    if outcome["value"] == "error":
        raise OSError("offline")
    return outcome["value"]
update.latest = latest
app = QApplication(["test"])
seen = {{}}
def menu():
    return next(t for t in app.findChildren(QSystemTrayIcon)).tray_menu
check = {{}}
def installs():
    return [a.text() for a in menu().actions() if a.isVisible() and a.text().startswith("Dostępna")]
def step(name, value, then, wait=1800):
    outcome["value"] = value
    check["action"].trigger()
    seen[name + "_checking"] = check["action"].text()
    def read():
        seen[name] = check["action"].text()
        seen[name + "_install"] = installs()
        then()
    QTimer.singleShot(wait, read)
def quit_all():
    Path({str(tmp_path / "seen.json")!r}).write_text(json.dumps(seen))
    menu().actions()[-1].trigger()
def third():
    step("found", {{"version": "9.9.9", "url": "", "notes": ""}}, quit_all)
def second():
    step("failed", "error", third)
def start():
    found = [a for a in menu().actions() if a.text().startswith("Sprawdź aktualizacje")]
    check["action"] = found[0]
    seen["first_text"] = check["action"].text()
    step("current", None, second)
QTimer.singleShot(2500, start)
QTimer.singleShot(30000, app.quit)
appwindow.run("http://127.0.0.1:9/", "t", language="pl", data_dir=Path({str(tmp_path)!r}),
              load_options=lambda: {{"check_updates": False}})
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox",
        },
    )
    assert result.returncode == 0, result.stderr[-2000:]
    seen = json.loads((tmp_path / "seen.json").read_text())
    assert seen["first_text"] == "Sprawdź aktualizacje"  # nothing checked yet
    assert seen["current_checking"] == "Sprawdzam aktualizacje…"
    assert "aktualna, sprawdzono" in seen["current"] and seen["current_install"] == []
    assert "nie udało się sprawdzić" in seen["failed"]
    assert "dostępna 9.9.9" in seen["found"]
    assert seen["found_install"] == ["Dostępna aktualizacja 9.9.9 — zainstaluj"]
