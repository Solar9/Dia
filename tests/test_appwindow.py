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


def test_window_hides_to_the_tray(monkeypatch, tmp_path):
    """The real window, offscreen: X and minimize hide it, the tray menu has every tab."""
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
        "quick_restore",
    ):
        assert seen[key], key
    assert seen["menu"][0] == "Otwórz Dia" and seen["menu"][-1] == "Zamknij ikonę i okno"
    assert seen["tabs"] == [
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
