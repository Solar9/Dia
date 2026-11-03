import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dia.desktop import appwindow, geometry

SCREEN = (0, 0, 1920, 1080)


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    geometry.save(tmp_path, (10, 20, 1000, 700), True)
    assert geometry.load(tmp_path) == {"x": 10, "y": 20, "w": 1000, "h": 700, "maximized": True}
    assert json.loads((tmp_path / "window.json").read_text())["w"] == 1000
    assert not list(tmp_path.glob("*.tmp"))  # an atomic write leaves nothing behind
    geometry.save(None, (1, 2, 3, 4), False)  # no data folder: nothing to do
    assert geometry.load(None) is None


@pytest.mark.parametrize(
    "content",
    ["", "not json", "[]", '{"x": 1}', '{"x":1,"y":2,"w":0,"h":5}', '{"x":"1","y":2,"w":9,"h":9}',
     '{"x":true,"y":2,"w":9,"h":9}'],
)  # fmt: skip
def test_a_damaged_file_is_ignored(tmp_path: Path, content: str) -> None:
    (tmp_path / "window.json").write_text(content)
    assert geometry.load(tmp_path) is None


def test_a_missing_file_is_ignored(tmp_path: Path) -> None:
    assert geometry.load(tmp_path) is None


def test_a_window_that_fits_stays_where_it_was() -> None:
    assert geometry.fit((100, 80, 1280, 820), [SCREEN]) == (100, 80, 1280, 820)


def test_a_position_off_screen_is_pulled_back() -> None:
    assert geometry.fit((5000, 4000, 1280, 820), [SCREEN]) == (640, 260, 1280, 820)
    assert geometry.fit((-900, -600, 1280, 820), [SCREEN]) == (0, 0, 1280, 820)
    assert geometry.fit((1500, 900, 1280, 820), [SCREEN]) == (640, 260, 1280, 820)  # half out


def test_a_window_bigger_than_the_screen_is_shrunk() -> None:
    assert geometry.fit((0, 0, 4000, 3000), [(0, 0, 1366, 768)]) == (0, 0, 1366, 768)
    # ...but never below the minimum the window is built for
    assert geometry.fit((0, 0, 100, 100), [SCREEN]) == (0, 0, 720, 480)


def test_a_window_from_an_unplugged_monitor_goes_to_the_nearest_screen() -> None:
    left, right = (0, 0, 1920, 1080), (1920, 0, 1920, 1080)
    # it was on a third monitor to the right of both
    assert geometry.fit((4200, 100, 1000, 700), [left, right]) == (2840, 100, 1000, 700)
    # on a second monitor that is there: kept
    assert geometry.fit((2000, 50, 1000, 700), [left, right]) == (2000, 50, 1000, 700)
    assert geometry.fit((7, 7, 900, 600), []) == (7, 7, 900, 600)  # no screens known: unchanged


def run_window(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = f"""
import os, tempfile
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from dia.desktop import appwindow, runtime
runtime.status = lambda: {{"available": False}}
appwindow.server_name = lambda: "dia-geometry-test-" + str(os.getpid())
app = QApplication(["test"])
data = Path({str(tmp_path)!r})
def window():
    return next(w for w in app.topLevelWidgets() if w.windowTitle() == "Dia")
seen = {{}}
def done():
    (data / "seen.json").write_text(__import__("json").dumps(seen))
{body}
QTimer.singleShot(25000, app.quit)
rc = appwindow.run("http://127.0.0.1:9/", "t", language="pl", data_dir=data,
                   load_options=lambda: {{"tray": False}})
assert rc == 0
done()
"""
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=40,
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox",
        },
    )


def test_the_window_comes_back_as_it_was_and_remembers_the_new_place(tmp_path: Path) -> None:
    if not appwindow.available():
        pytest.skip("QtWebEngine is not installed")
    geometry.save(tmp_path, (40, 30, 760, 520), False)  # the offscreen screen is 800x600
    body = """
def check():
    w = window()
    seen["restored"] = [w.width(), w.height()]
    w.resize(740, 500)  # the user drags the edge...
    QTimer.singleShot(200, w.close)  # ...and quits: no tray, so the window's X ends Dia
QTimer.singleShot(2000, check)
"""
    result = run_window(tmp_path, body)
    assert result.returncode == 0, result.stderr[-2000:]
    saved = geometry.load(tmp_path)
    assert saved and (saved["w"], saved["h"], saved["maximized"]) == (740, 500, False)
    assert json.loads((tmp_path / "seen.json").read_text())["restored"] == [760, 520]


def test_a_maximised_window_comes_back_maximised_with_its_normal_size(tmp_path: Path) -> None:
    if not appwindow.available():
        pytest.skip("QtWebEngine is not installed")
    geometry.save(tmp_path, (40, 30, 740, 500), True)
    body = """
def check():
    w = window()
    seen["maximized"] = w.isMaximized()
    QTimer.singleShot(100, w.close)
QTimer.singleShot(2000, check)
"""
    result = run_window(tmp_path, body)
    assert result.returncode == 0, result.stderr[-2000:]
    saved = geometry.load(tmp_path)
    assert saved and saved["maximized"] is True
    assert (saved["w"], saved["h"]) == (740, 500)  # the normal size, not the screen's
    assert json.loads((tmp_path / "seen.json").read_text())["maximized"] is True


def test_an_off_screen_position_is_fitted_when_the_window_opens(tmp_path: Path) -> None:
    if not appwindow.available():
        pytest.skip("QtWebEngine is not installed")
    geometry.save(tmp_path, (90000, 90000, 900, 600), False)
    body = """
def check():
    w = window()
    r = w.geometry()
    screens = [s.availableGeometry() for s in app.screens()]
    seen["on_screen"] = any(s.contains(r.topLeft()) for s in screens)
    QTimer.singleShot(100, w.close)
QTimer.singleShot(2000, check)
"""
    result = run_window(tmp_path, body)
    assert result.returncode == 0, result.stderr[-2000:]
    saved = geometry.load(tmp_path)
    assert saved and saved["x"] < 90000 and saved["y"] < 90000
    assert json.loads((tmp_path / "seen.json").read_text())["on_screen"] is True
