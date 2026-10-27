"""Dia's desktop window: the web UI in Qt, with Dia's icon and a tray icon.

``dia app`` uses this when PySide6 with QtWebEngine is installed (``pip
install 'dia[qt]'``; on Arch the system ``pyside6`` and ``qt6-webengine``
packages); otherwise pywebview, otherwise a browser app window.

- The window identifies itself as ``dia`` (the menu entry ``dia.desktop``),
  so the taskbar shows Dia's icon and groups it with the launcher.
- A tray icon: a click shows or hides the window, its menu opens a tab
  (Chat, Tasks, ...), talks to Dia, toggles quiet mode or quits.
- ``[app] minimize_to_tray`` and ``close_to_tray`` (both on by default):
  minimizing, or the window's X, hides it to the tray; quit from the tray
  menu. Dia itself (``dia serve``) keeps running either way.
- One window: ``dia app`` again (or the menu icon) shows the existing one;
  ``dia app --view chat`` also switches its tab, ``--task ID`` opens a task.
"""

from __future__ import annotations

import concurrent.futures
import getpass
import json
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ICONS = Path(__file__).resolve().parent / "ui" / "static" / "icons"
VIEWS = ["tasks", "missions", "chat", "cli", "memory", "status", "usage", "settings"]
LABELS = {
    "pl": {
        "open": "Otwórz Dia", "hide": "Ukryj okno", "talk": "Mów do Dia",
        "quiet": "Tryb cichy", "quit": "Zakończ", "views": "Przejdź do",
        "tasks": "Zadania", "missions": "Misje", "chat": "Czat", "cli": "Sesje CLI",
        "memory": "Pamięć",
        "status": "Status", "usage": "Zużycie", "settings": "Ustawienia",
        "in_tray": "Dia działa dalej w zasobniku. Zakończysz ją z menu tej ikony.",
    },
    "en": {
        "open": "Open Dia", "hide": "Hide window", "talk": "Talk to Dia",
        "quiet": "Quiet mode", "quit": "Quit", "views": "Go to",
        "tasks": "Tasks", "missions": "Missions", "chat": "Chat", "cli": "CLI sessions",
        "memory": "Memory",
        "status": "Status", "usage": "Usage", "settings": "Settings",
        "in_tray": "Dia keeps running in the tray. Quit it from this icon's menu.",
    },
}  # fmt: skip
DEFAULTS = {"tray": True, "minimize_to_tray": True, "close_to_tray": True, "custom_titlebar": True,
            "check_updates": True}  # fmt: skip
STATUS_EVERY = 2.0  # seconds between looks at the services
UPDATE_EVERY = 6 * 3600  # seconds between looks for a new release
# The page asks the window for what its own title bar does (console messages: no
# extra libraries, nothing exposed to other pages).
BRIDGE = "dia-window:"
EDGES = ("top", "bottom", "left", "right")
USER_AGENT_MARK = "DiaDesktop/frameless"


def available() -> bool:
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except ImportError:
        return False
    return True


def options(section: dict[str, Any]) -> dict[str, bool]:
    """``[app]`` with its defaults."""
    return {key: bool(section.get(key, default)) for key, default in DEFAULTS.items()}


def on_close(opts: dict[str, bool], tray: bool) -> str:
    """What the window's X does: "hide" to the tray, or "quit"."""
    return "hide" if tray and opts["tray"] and opts["close_to_tray"] else "quit"


def on_minimize(opts: dict[str, bool], tray: bool) -> bool:
    """Whether minimizing hides the window to the tray."""
    return tray and opts["tray"] and opts["minimize_to_tray"]


def window_command(text: str) -> tuple[str, list[str]] | None:
    """``dia-window:resize:top-left`` -> ("resize", ["top", "left"]); None: not for us."""
    if not text.startswith(BRIDGE):
        return None
    action, _, rest = text[len(BRIDGE) :].partition(":")
    if action in ("move", "minimize", "maximize", "close", "start-services"):
        return action, []
    edges = [e for e in rest.split("-") if e in EDGES]
    if action == "resize" and edges:
        return action, edges
    return None


def quiet_label(text: str, on: bool) -> str:
    """A menu item with its box on the right (the column after a tab)."""
    return f"{text}\t{'☑' if on else '☐'}"


def server_name() -> str:
    return f"dia-app-{getpass.getuser()}"


def message(view: str | None, task: str | None = None) -> bytes:
    return (
        " ".join(filter(None, ["show", view or ("tasks" if task else None), task])).encode() + b"\n"
    )


def parse_message(data: bytes) -> tuple[str | None, str | None]:
    """The tab (and task) asked for by another ``dia app``; (None, None): just show."""
    words = data.decode(errors="replace").split()
    if len(words) < 2 or words[0] != "show" or words[1] not in VIEWS:
        return None, None
    task = words[2] if len(words) > 2 and re.fullmatch(r"[\w-]+", words[2]) else None
    return words[1], task


def navigate_js(view: str, task: str | None = None) -> str:
    return f"window.diaNavigate && window.diaNavigate({json.dumps(view)}, {json.dumps(task)})"


def _icon() -> Any:
    from PySide6.QtGui import QIcon

    icon = QIcon()
    for png in sorted(ICONS.glob("dia-*.png")):
        icon.addFile(str(png))
    if (ICONS / "dia.svg").exists():
        icon.addFile(str(ICONS / "dia.svg"))
    return icon


# Dia's own API is on this computer: never through a proxy from the environment, which
# could make every status check wait for its timeout.
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _api(base: str, token: str, path: str, method: str = "GET", body: Any = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})  # fmt: skip
    with _LOCAL.open(req, timeout=2) as resp:
        return json.loads(resp.read() or b"null")


def _send_to_running(view: str | None, task: str | None = None, background: bool = False) -> bool:
    """Hand over to a Dia window that is already open."""
    from PySide6.QtNetwork import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(300):
        return False
    socket.write(b"background\n" if background else message(view, task))
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


def run(base: str, token: str, *, language: str = "en", view: str | None = None,
        task: str | None = None, data_dir: Path | None = None,
        load_options: Callable[[], dict[str, Any]] = dict,
        background: bool = False, config_source: Path | None = None,
        start_services: bool = False) -> int:  # fmt: skip
    """Open Dia's window at ``base`` (the UI's address) and run until it quits."""
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import QAction, QDesktopServices
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QMenu,
        QMessageBox,
        QSystemTrayIcon,
    )

    from dia import runtime, service, update

    app = QApplication.instance() or QApplication([sys.argv[0] or "dia"])
    if _send_to_running(view, task, background):
        # An existing shell already owns the service controls. Login must not
        # unhide it or create another window.
        return 0
    words = LABELS.get(language, LABELS["en"])
    app.setApplicationName("Dia")
    app.setApplicationDisplayName("Dia")
    app.setDesktopFileName("dia")  # Wayland app id: the menu entry, its icon on the taskbar
    icon = _icon()
    app.setWindowIcon(icon)
    opts = options(load_options())
    tray_ok = opts["tray"] and QSystemTrayIcon.isSystemTrayAvailable()
    app.setQuitOnLastWindowClosed(not tray_ok)
    origin = QUrl(base)

    class Page(QWebEnginePage):
        """Dia's pages stay in the window; other links open in the browser."""

        def acceptNavigationRequest(self, url: QUrl, kind: Any, main_frame: bool) -> bool:
            if url.scheme() in ("http", "https") and url.host() != origin.host():
                QDesktopServices.openUrl(url)
                return False
            return super().acceptNavigationRequest(url, kind, main_frame)

        def javaScriptConsoleMessage(self, level: Any, text: str, line: int, source: str) -> None:
            command = window_command(text) if QUrl(source).host() == origin.host() else None
            if command:
                handle(*command)

        def createWindow(self, kind: Any) -> QWebEnginePage:  # target=_blank
            page = QWebEnginePage(self)
            page.urlChanged.connect(lambda url: (QDesktopServices.openUrl(url), page.deleteLater()))
            return page

    profile = QWebEngineProfile("dia", app)  # keeps the sign-in, theme and drafts
    if data_dir:
        profile.setPersistentStoragePath(str(data_dir / "app-profile"))
        profile.setCachePath(str(data_dir / "app-profile" / "cache"))
    frameless = opts["custom_titlebar"]
    if frameless:  # the page draws the title bar: tells it by its user agent
        profile.setHttpUserAgent(f"{profile.httpUserAgent()} {USER_AGENT_MARK}")
    state: dict[str, Any] = {"told": False, "quitting": False}

    class Window(QMainWindow):
        def closeEvent(self, event: Any) -> None:
            fresh = options(load_options())
            if not state["quitting"] and on_close(fresh, tray_ok) == "hide":
                event.ignore()
                self.hide()
                if not state["told"] and tray:
                    tray.showMessage("Dia", words["in_tray"], icon, 4000)
                    state["told"] = True
                return
            event.accept()
            app.quit()

        def changeEvent(self, event: Any) -> None:
            super().changeEvent(event)
            if event.type() == event.Type.WindowStateChange and frameless:
                state_js = "maximized" if self.isMaximized() else "normal"
                web.page().runJavaScript(
                    f"window.diaWindowState && window.diaWindowState('{state_js}')"
                )
            if (event.type() == event.Type.WindowStateChange and self.isMinimized()
                    and on_minimize(options(load_options()), tray_ok)):  # fmt: skip
                # Let Qt/the compositor finish minimizing before hiding. Hiding
                # inside showMinimized() can be undone when that call completes.
                QTimer.singleShot(0, self.hide_if_minimized)

        def hide_if_minimized(self) -> None:
            if self.isMinimized() and on_minimize(options(load_options()), tray_ok):
                self.hide()

    window = Window()
    if frameless:
        window.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    window.setWindowTitle("Dia")
    window.setWindowIcon(icon)
    window.resize(1280, 820)
    window.setMinimumSize(720, 480)
    web = QWebEngineView(window)
    web.setPage(Page(profile, web))
    window.setCentralWidget(web)
    start = f"{base}#token={token}" + (f"&view={view}" if view else "") + (
        f"&task={task}" if task else "")  # fmt: skip
    # Poll in a worker: systemd, authentication and HTTP must never freeze Qt.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    jobs: dict[str, Any] = {}
    online = {"value": None, "active": []}
    found: dict[str, Any] = {"release": None, "checked": -UPDATE_EVERY - 1.0}
    update_action = QAction(app)
    update_action.setVisible(False)
    pl = language == "pl"

    def offline() -> None:
        title = "Dia jest zatrzymana lub uruchamia się" if pl else "Dia is stopped or starting"
        button = "Uruchom Dia" if pl else "Start Dia"
        web.setHtml(
            f"""<html><body style="background:#171823;color:#eee;
            font:18px sans-serif;padding:48px"><h1>{title}</h1>
            <p>{
                "Usługami możesz zarządzać także z traya i widgetu."
                if pl
                else "You can also manage services from the tray and widget."
            }</p>
            <button onclick="console.log('dia-window:start-services')">{button}</button>
            <button onclick="console.log('dia-window:close')">×</button>
            </body></html>""",
            QUrl(base),
        )

    offline()

    def inspect() -> dict:
        result = runtime.status()
        try:
            result["api"] = _api(base, token, "/api/status")
        except (OSError, ValueError):
            result["api"] = None
        return result

    def control(component: str, verb: str, quit_after: bool = False) -> None:
        if "action" in jobs:
            return
        if verb in ("stop", "restart"):
            text = (
                f"Aktywne zadania: {online['active']}. Kontynuować?"
                if pl
                else f"Active tasks: {online['active']}. Continue?"
            )
            if QMessageBox.question(window, "Dia", text) != QMessageBox.StandardButton.Yes:
                return
        jobs["action"] = (pool.submit(runtime.action, component, verb, config_source), quit_after)

    last_inspect = {"at": 0.0}  # polled often, so a finished check shows at once, run rarely

    def poll() -> None:
        if "logs" in jobs and jobs["logs"].done():
            try:
                output = jobs.pop("logs").result()
            except Exception as exc:
                output = str(exc)
            dialog = QMessageBox(window)
            dialog.setWindowTitle("Dia — logi" if pl else "Dia — logs")
            dialog.setText("Ostatnie wpisy dziennika" if pl else "Recent journal entries")
            dialog.setDetailedText(output)
            dialog.exec()
        if "action" in jobs and jobs["action"][0].done():
            future, quit_after = jobs.pop("action")
            try:
                future.result()
                if quit_after:
                    quit_app()
                    return
            except Exception as exc:
                QMessageBox.warning(window, "Dia", str(exc))
        if "status" in jobs and jobs["status"].done():
            future = jobs.pop("status")
            try:
                result = future.result()
                api = result.get("api")
                ready = api is not None
                online["active"] = (api or {}).get("active", [])
                if ready != online["value"]:
                    web.load(QUrl(start)) if ready else offline()
                    online["value"] = ready
                if tray:
                    dia_state = result.get("dia", {}).get("active", "unknown")
                    ollama_state = result.get("ollama", {}).get("active", "unknown")
                    label = f"Dia: {dia_state} · Ollama: {ollama_state}"
                    tray.setToolTip(label)
                    update_service_status(dia_state, ollama_state)
                    talk_action.setEnabled(ready)
                    quiet.setEnabled(ready)
                    quiet_on["value"] = bool((api or {}).get("quiet"))
                    quiet.setText(quiet_label(words["quiet"], quiet_on["value"]))
            except Exception as exc:
                if tray:
                    tray.setToolTip(f"Dia: {exc}")
        if "status" not in jobs and time.monotonic() - last_inspect["at"] >= STATUS_EVERY:
            last_inspect["at"] = time.monotonic()
            jobs["status"] = pool.submit(inspect)
        poll_update()

    qt_edges = {"top": Qt.Edge.TopEdge, "bottom": Qt.Edge.BottomEdge,
                "left": Qt.Edge.LeftEdge, "right": Qt.Edge.RightEdge}  # fmt: skip

    def handle(action: str, edges: list[str]) -> None:
        """The page's title bar: drag, resize from an edge, the three buttons."""
        handle_ = window.windowHandle()
        if action == "start-services":
            control("dia", "start")
        elif action == "move" and handle_:
            handle_.startSystemMove()
        elif action == "resize" and handle_ and not window.isMaximized():
            flags = qt_edges[edges[0]]
            for edge in edges[1:]:
                flags |= qt_edges[edge]
            handle_.startSystemResize(flags)
        elif action == "minimize":
            if on_minimize(options(load_options()), tray_ok):
                window.hide()
            else:
                window.showMinimized()
        elif action == "maximize":
            window.showNormal() if window.isMaximized() else window.showMaximized()
        elif action == "close":
            window.close()

    def show(target: str | None = None, task: str | None = None) -> None:
        if window.isMinimized():
            window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
        window.show()
        window.raise_()
        window.activateWindow()
        if target:
            web.page().runJavaScript(navigate_js(target, task))

    def toggle() -> None:
        if window.isVisible() and not window.isMinimized():
            window.hide()
        else:
            show()

    def call(path: str, body: Any = None) -> None:
        try:
            _api(base, token, path, "POST", body)
        except OSError as exc:
            if tray:
                tray.showMessage("Dia", str(exc), icon, 4000)

    def quit_app() -> None:
        state["quitting"] = True
        window.close()
        app.quit()

    def ask_update() -> None:
        release = found["release"]
        if not release or "update" in jobs:
            return
        text = (
            f"Zainstalować Dia {release['version']}? Dia zostanie uruchomiona ponownie."
            if pl
            else f"Install Dia {release['version']}? Dia will restart."
        )
        if online["active"]:
            text += (
                f"\n\nAktywne zadania: {len(online['active'])}."
                if pl
                else f"\n\nActive tasks: {len(online['active'])}."
            )
        if QMessageBox.question(window, "Dia", text) != QMessageBox.StandardButton.Yes:
            return
        update_action.setEnabled(False)
        update_action.setText("Aktualizuję…" if pl else "Updating…")

        def work() -> None:
            update.install(release["version"])
            if service.installed():
                runtime.action("dia", "restart", config_source)

        jobs["update"] = pool.submit(work)

    def relaunch() -> None:
        # The new code is on disk; start it once this process has let go of the
        # single-instance socket.
        subprocess.Popen(
            ["sh", "-c", 'sleep 2; exec "$@"', "sh", sys.executable, *sys.orig_argv[1:]],
            start_new_session=True,
        )
        quit_app()

    def poll_update() -> None:
        if "update" in jobs and jobs["update"].done():
            future = jobs.pop("update")
            try:
                future.result()
            except Exception as exc:
                update_action.setEnabled(True)
                set_update_text()
                QMessageBox.warning(window, "Dia", str(exc))
            else:
                relaunch()
                return
        if "update_check" in jobs and jobs["update_check"].done():
            try:
                release = jobs.pop("update_check").result()
            except Exception:
                release = found["release"]  # offline or rate limited: try again later
            if release and (found["release"] or {}).get("version") != release["version"]:
                found["release"] = release
                set_update_text()
                if tray:
                    tray.showMessage("Dia", update_action.text(), icon, 6000)
        if time.monotonic() - found["checked"] > UPDATE_EVERY:
            found["checked"] = time.monotonic()
            if (options(load_options())["check_updates"] and "update" not in jobs
                    and not update.editable()):  # fmt: skip
                jobs["update_check"] = pool.submit(update.latest)

    def set_update_text() -> None:
        release = found["release"]
        update_action.setVisible(bool(release))
        if release:
            update_action.setText(
                f"Dostępna aktualizacja {release['version']} — zainstaluj"
                if pl
                else f"Update {release['version']} available — install"
            )

    def update_service_status(dia_state: str, ollama_state: str) -> None:
        # The native tray menu is plain text, so the colour is an emoji dot.
        def dot(status: str) -> str:
            return {"active": "🟢", "inactive": "🔴"}.get(status, "⚪")

        service_status.setText(f"Dia {dot(dia_state)} | Ollama {dot(ollama_state)}")

    tray = None
    if tray_ok:
        tray = QSystemTrayIcon(icon, app)
        tray.setToolTip("Dia")
        menu = QMenu()
        menu.addAction(words["open"], lambda: show())
        go = menu.addMenu(words["views"])
        for name in VIEWS:
            go.addAction(words[name], lambda name=name: show(name))
        menu.addSeparator()
        talk_action = menu.addAction(words["talk"], lambda: call("/api/voice/toggle"))
        # Not a checkable action: Qt would indent every item for a box on the left.
        # The box is drawn in the right-hand column (after the tab) instead.
        quiet_on = {"value": False}
        quiet = QAction(quiet_label(words["quiet"], False), menu)
        quiet.triggered.connect(lambda: call("/api/quiet", {"on": not quiet_on["value"]}))
        menu.addAction(quiet)
        menu.addSeparator()
        service_status = QAction(menu)
        update_service_status("unknown", "unknown")
        menu.addAction(service_status)
        update_action.triggered.connect(ask_update)
        menu.addAction(update_action)
        for component, label in (
            ("dia", "Usługi Dia" if pl else "Dia services"),
            ("ollama", "Ollama"),
        ):
            submenu = menu.addMenu(label)
            for verb, label in (
                ("start", "Uruchom" if pl else "Start"),
                ("stop", "Zatrzymaj" if pl else "Stop"),
                ("restart", "Uruchom ponownie" if pl else "Restart"),
            ):
                submenu.addAction(label, lambda c=component, v=verb: control(c, v))
            submenu.addAction(
                "Logi" if pl else "Logs",
                lambda c=component: jobs.update(logs=pool.submit(runtime.logs, c)),
            )
        menu.addAction(
            "Zatrzymaj Dia i zakończ" if pl else "Stop Dia and quit",
            lambda: control("dia", "stop", True),
        )
        menu.addAction("Zamknij ikonę i okno" if pl else "Close icon and window", quit_app)

        # Plasma only opens the menu it gets over D-Bus, so it must be set as
        # the tray's context menu (the D-Bus export is plain text).
        tray.tray_menu = menu
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: toggle() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        tray.show()

    server = QLocalServer(app)  # the next `dia app` shows this window instead
    QLocalServer.removeServer(server_name())
    server.listen(server_name())

    def incoming() -> None:
        conn = server.nextPendingConnection()

        def read() -> None:
            data = bytes(conn.readAll().data())
            if data.strip() != b"background":
                show(*parse_message(data))
            conn.disconnectFromServer()

        conn.readyRead.connect(read)

    server.newConnection.connect(incoming)
    if not background:
        window.show()
    elif not tray_ok:
        # A widget-only login should not open a window or keep an invisible shell.
        pool.shutdown(wait=False, cancel_futures=True)
        if start_services:
            try:
                runtime.action("dia", "start", config_source)
            except (RuntimeError, OSError) as exc:
                print(str(exc), file=sys.stderr)
                return 1
        return 0
    if start_services:
        control("dia", "start")
    timer = QTimer(app)
    timer.timeout.connect(poll)
    timer.start(500)
    poll()
    result = app.exec()
    timer.stop()
    server.close()
    if tray:
        tray.hide()
    pool.shutdown(wait=False, cancel_futures=True)
    return result
