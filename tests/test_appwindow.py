import os

import pytest

from dia import appwindow


def test_options_defaults_and_overrides():
    assert appwindow.options({}) == {
        "tray": True,
        "minimize_to_tray": True,
        "close_to_tray": True,
        "custom_titlebar": True,
        "check_updates": True,
    }
    assert appwindow.options({"close_to_tray": False})["close_to_tray"] is False


def test_close_and_minimize_follow_the_options_and_the_tray():
    opts = appwindow.options({})
    assert appwindow.on_close(opts, tray=True) == "hide"
    assert appwindow.on_close(opts, tray=False) == "quit"  # no tray: X really closes
    assert appwindow.on_close({**opts, "close_to_tray": False}, tray=True) == "quit"
    assert appwindow.on_close({**opts, "tray": False}, tray=True) == "quit"
    assert appwindow.on_minimize(opts, tray=True)
    assert not appwindow.on_minimize({**opts, "minimize_to_tray": False}, tray=True)
    assert not appwindow.on_minimize(opts, tray=False)


def test_messages_between_instances():
    assert appwindow.parse_message(appwindow.message("chat")) == ("chat", None)
    assert appwindow.parse_message(appwindow.message(None, "t-12")) == ("tasks", "t-12")
    assert appwindow.parse_message(appwindow.message(None)) == (None, None)
    assert appwindow.parse_message(b"show nonsense\n") == (None, None)
    assert appwindow.parse_message(b"show tasks ';alert(1)\n") == ("tasks", None)
    assert appwindow.navigate_js("chat") == 'window.diaNavigate && window.diaNavigate("chat", null)'


def test_window_commands_from_the_page():
    assert appwindow.window_command("dia-window:move") == ("move", [])
    assert appwindow.window_command("dia-window:resize:top-left") == ("resize", ["top", "left"])
    assert appwindow.window_command("dia-window:resize:sideways") is None
    assert appwindow.window_command("dia-window:explode") is None
    assert appwindow.window_command("hello") is None


def test_quiet_box_sits_on_the_right():
    assert appwindow.quiet_label("Tryb cichy", True) == "Tryb cichy\t☑"
    assert appwindow.quiet_label("Tryb cichy", False) == "Tryb cichy\t☐"


def test_labels_cover_every_view():
    for words in appwindow.LABELS.values():
        assert all(view in words for view in appwindow.VIEWS)


def test_qt_offscreen_window_hides_to_the_tray(monkeypatch, tmp_path):
    """Qt offscreen (timing-sensitive on CI): X/minimize hide; tray menu has every tab."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    except ImportError:
        pytest.skip("PySide6 (with its system libraries) is not installed")
    if not appwindow.available():
        pytest.skip("QtWebEngine is not installed")
    from dia import runtime

    monkeypatch.setattr(
        runtime,
        "status",
        lambda: {"available": True, "dia": {"active": "active"}, "ollama": {"active": "inactive"}},
    )
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    monkeypatch.setattr(appwindow, "server_name", lambda: f"dia-app-test-{os.getpid()}")
    app = QApplication.instance() or QApplication(["dia"])
    seen = {}
    opts = {}

    def check():
        window = next(w for w in app.topLevelWidgets() if w.windowTitle() == "Dia")
        tray = next(t for t in app.findChildren(QSystemTrayIcon))
        statuses = [a for a in tray.tray_menu.actions() if a.text() == "Dia 🟢 | Ollama 🔴"]
        seen["status_count"] = len(statuses)
        seen["no_status_icons"] = all(a.icon().isNull() for a in statuses)
        seen["registered_context_menu"] = tray.contextMenu() is tray.tray_menu
        open_window = tray.tray_menu.actions()[0].trigger

        def minimize_button():
            window.centralWidget().page().javaScriptConsoleMessage(
                None, "dia-window:minimize", 1, "http://127.0.0.1:9/"
            )

        # Exercise the actual title-bar command, not just setWindowState().
        minimize_button()
        seen["button_hidden"] = not window.isVisible() and not window.isMinimized()
        open_window()
        seen["button_restored"] = window.isVisible() and not window.isMinimized()
        opts["minimize_to_tray"] = False
        minimize_button()
        app.processEvents()
        seen["ordinary_minimize"] = window.isVisible() and window.isMinimized()
        open_window()
        opts["minimize_to_tray"] = True
        window.close()
        seen["after_close"] = window.isVisible()
        window.show()
        window.showMinimized()
        app.processEvents()
        seen["after_minimize"] = window.isVisible()
        open_window()
        seen["native_restored"] = window.isVisible() and not window.isMinimized()
        window.showMaximized()
        window.showMinimized()
        app.processEvents()
        seen["maximized_hidden"] = not window.isVisible()
        open_window()
        seen["maximized_restored"] = window.isVisible() and window.isMaximized()
        # The page's maximize button toggles; the page hears the new state.
        window.centralWidget().page().javaScriptConsoleMessage(
            None, "dia-window:maximize", 1, "http://127.0.0.1:9/static/app.js"
        )
        seen["button_unmaximized"] = window.isVisible() and not window.isMaximized()
        window.centralWidget().page().javaScriptConsoleMessage(
            None, "dia-window:maximize", 1, "http://127.0.0.1:9/static/app.js"
        )
        seen["button_maximized"] = window.isMaximized()
        # Another site's page can't drive the window.
        window.centralWidget().page().javaScriptConsoleMessage(
            None, "dia-window:maximize", 1, "https://example.com/"
        )
        seen["foreign_ignored"] = window.isMaximized()
        # The page's theme accent recolours the window's and the tray's icon, and is kept.
        before = window.windowIcon().cacheKey()
        window.centralWidget().page().javaScriptConsoleMessage(
            None, "dia-window:accent:22d3ee", 1, "http://127.0.0.1:9/static/app.js"
        )
        seen["accent_icon"] = window.windowIcon().cacheKey() != before and not tray.icon().isNull()
        seen["accent_saved"] = (tmp_path / "app-accent").read_text() == "22d3ee"
        # A queued hide must not hide a window restored before the timer runs.
        window.showMinimized()
        open_window()
        app.processEvents()
        seen["quick_restore"] = window.isVisible() and not window.isMinimized()
        seen["menu"] = [a.text() for a in tray.tray_menu.actions()]
        seen["tabs"] = [a.text() for a in tray.tray_menu.actions()[1].menu().actions()]
        tray.tray_menu.actions()[-1].trigger()  # Quit

    QTimer.singleShot(2500, check)
    QTimer.singleShot(8000, app.quit)  # never hang the suite
    rc = appwindow.run(
        "http://127.0.0.1:9/", "t", language="pl", data_dir=tmp_path, load_options=lambda: opts
    )
    assert rc == 0
    assert seen["status_count"] == 1
    assert seen["no_status_icons"] and seen["registered_context_menu"]
    assert seen["after_close"] is False and seen["after_minimize"] is False
    for key in (
        "button_hidden",
        "button_restored",
        "ordinary_minimize",
        "native_restored",
        "maximized_hidden",
        "maximized_restored",
        "button_unmaximized",
        "button_maximized",
        "foreign_ignored",
        "accent_icon",
        "accent_saved",
        "quick_restore",
    ):
        assert seen[key], key
    assert seen["menu"][0] == "Otwórz Dia" and seen["menu"][-1] == "Zamknij ikonę i okno"
    assert seen["tabs"] == [
        "Skrzynka",
        "Zadania",
        "Misje",
        "Czat",
        "Sesje CLI",
        "Pamięć",
        "Status",
        "Zużycie",
        "Ustawienia",
    ]


def test_login_shows_only_tray_and_left_click_toggles(tmp_path):
    """Use a fresh Qt process to test the login lifecycle and duplicate launches."""
    import subprocess
    import sys

    if not appwindow.available():
        pytest.skip("QtWebEngine is not installed")
    script = """
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from dia import appwindow, runtime
import os, threading
release = threading.Event()
started = []
def starting(*args):
    started.append(True)
    release.wait(3)
runtime.action = starting
runtime.status = lambda: {"available": False}
appwindow.server_name = lambda: "dia-login-test-" + str(os.getpid())
QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
app = QApplication(["test"])
seen = []
def check():
    window = next(w for w in app.topLevelWidgets() if w.windowTitle() == "Dia")
    tray = app.findChildren(QSystemTrayIcon)[0]
    seen.append(not window.isVisible() and bool(started))
    release.set()
    appwindow._send_to_running(None, background=True)
    app.processEvents()
    seen.append(not window.isVisible())
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    seen.append(window.isVisible())
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    seen.append(not window.isVisible())
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    seen.append(window.isVisible() and not window.isMinimized())
    window.showMaximized()
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    seen.append(not window.isVisible())
    tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
    seen.append(window.isVisible() and window.isMaximized())
    # Explicit Open remains idempotent, unlike clicking the tray icon.
    tray.tray_menu.actions()[0].trigger()
    seen.append(window.isVisible())
    tray.tray_menu.actions()[-1].trigger()
QTimer.singleShot(300, check)
QTimer.singleShot(5000, app.quit)
appwindow.run("http://127.0.0.1:9/", "t", background=True, start_services=True)
assert seen == [True] * 8, seen
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "offscreen",
            "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox",
        },
    )
    assert result.returncode == 0, result.stderr


def test_offline_page_is_the_title_bar_too() -> None:
    page = appwindow.offline_page(True, True)
    assert "Uruchom Dia" in page and "dia-window:start-services" in page
    for action in ("minimize", "maximize", "close"):
        assert f"call(\\'{action}\\')" in page or f"call('{action}')" in page
    assert page.count("data-edge=") == 8 and "data-drag" in page and "__" not in page
    assert 'src="data:image/svg+xml;base64,' in page  # Dia's icon, served by nobody
    # With the system's own title bar the page draws none.
    plain = appwindow.offline_page(False, False)
    assert "Start Dia" in plain and "call('minimize')" not in plain and 'data-edge="' not in plain


def test_offline_page_buttons_drive_the_real_window(tmp_path):
    """Dia stopped: the window's only page must still maximize, minimize and close it.

    The buttons are clicked in the page; their messages reach Qt a little later, so
    the script waits for each result. A fresh Qt process, like the login test."""
    import subprocess
    import sys

    if not appwindow.available():
        pytest.skip("QtWebEngine is not installed")
    script = """
import os, tempfile
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from dia import appwindow, runtime
runtime.status = lambda: {"available": False}
appwindow.server_name = lambda: "dia-offline-test-" + str(os.getpid())
app = QApplication(["test"])
seen = {}
def window():
    return next(w for w in app.topLevelWidgets() if w.windowTitle() == "Dia")
def click(index):
    window().centralWidget().page().runJavaScript(
        "document.querySelectorAll('.win')[%d].click()" % index)
def wait(key, done, then, left=80):
    if done() or left == 0:
        seen[key] = done()
        then()
    else:
        QTimer.singleShot(100, lambda: wait(key, done, then, left - 1))
def close():
    window().showNormal()
    click(2)  # no tray: closing the window quits Dia's app
def minimize():
    click(0)
    wait("minimized", lambda: window().isMinimized(), close)
def start():
    click(1)
    wait("maximized", lambda: window().isMaximized(), minimize)
QTimer.singleShot(2500, start)
QTimer.singleShot(25000, app.quit)
rc = appwindow.run("http://127.0.0.1:9/", "t", language="pl",
                   data_dir=Path(tempfile.mkdtemp()), load_options=lambda: {"tray": False})
assert rc == 0 and seen == {"maximized": True, "minimized": True}, seen
"""
    result = subprocess.run(
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
    assert result.returncode == 0, result.stderr[-2000:]


def test_dias_icon_takes_the_themes_accent(tmp_path) -> None:
    assert appwindow.window_command("dia-window:accent:B4A2FF") == ("accent", ["b4a2ff"])
    for bad in ("dia-window:accent:#b4a2ff", "dia-window:accent:b4a2", "dia-window:accent:zzzzzz"):
        assert appwindow.window_command(bad) is None
    svg = appwindow.tinted_svg("b4a2ff").decode()
    import xml.etree.ElementTree as ET

    stops = [
        s.get("stop-color") for s in ET.fromstring(svg).iter("{http://www.w3.org/2000/svg}stop")
    ]
    assert stops[1] == "#b4a2ff" and stops[0] > stops[1] > stops[2] > stops[3]  # light to dark
    assert appwindow.saved_accent(tmp_path) is None
    (tmp_path / "app-accent").write_text("22d3ee\n")
    assert appwindow.saved_accent(tmp_path) == "22d3ee"
    (tmp_path / "app-accent").write_text("url(evil)")
    assert appwindow.saved_accent(tmp_path) is None
    import base64

    tinted = base64.b64encode(appwindow.tinted_svg("22d3ee")).decode()
    assert tinted in appwindow.offline_page(True, True, "22d3ee")
