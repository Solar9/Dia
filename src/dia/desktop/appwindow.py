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
import contextlib
import getpass
import json
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from dia.desktop import geometry
from dia.desktop import offline as offline_ui
from dia.desktop.labels import LABELS, VIEWS, update_line
from dia.ui import theme

ICONS = Path(__file__).resolve().parent.parent / "ui" / "static" / "icons"
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


def offline_page(
    language: str,
    frameless: bool,
    accent: str | None = None,
    variables: dict[str, str] | None = None,
    state: str = "starting",
) -> str:
    """The page shown while Dia does not answer (see dia.desktop.offline)."""
    svg = tinted_svg(accent) if accent else (ICONS / "dia.svg").read_bytes()
    return offline_ui.render(language, frameless, svg, variables, state)


def window_command(text: str) -> tuple[str, list[str]] | None:
    """``dia-window:resize:top-left`` -> ("resize", ["top", "left"]); None: not for us."""
    if not text.startswith(BRIDGE):
        return None
    action, _, rest = text[len(BRIDGE) :].partition(":")
    if action in ("move", "minimize", "maximize", "close", "start-services", "show-logs"):
        return action, []
    if action == "accent" and re.fullmatch(r"[0-9a-fA-F]{6}", rest):
        return action, [rest.lower()]  # the theme's accent: Dia's icon takes its colour
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


# Dia's icon in a theme's accent: the stops of icons/dia.svg, from lighter to darkest
# (offset, the accent's share, mixed with white 255 or black 0); the page does the same.
LOGO_MIX = ((0, 0.45, 255), (0.46, 1.0, 0), (0.72, 0.7, 0), (1, 0.35, 0))


def tinted_svg(accent: str) -> bytes:
    """icons/dia.svg with its gradient made from ``accent`` (6 hex digits)."""
    rgb = [int(accent[i : i + 2], 16) for i in (0, 2, 4)]
    stops = "".join(
        '<stop offset="{}" stop-color="#{}"/>'.format(
            offset, "".join(f"{round(v * share + other * (1 - share)):02x}" for v in rgb)
        )
        for offset, share, other in LOGO_MIX
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
        f'<defs><linearGradient id="dia" x1="0" y1="0" x2="1" y2="1">{stops}</linearGradient>'
        '</defs><circle cx="256" cy="256" r="208" fill="none" stroke="url(#dia)" '
        'stroke-width="54"/><circle cx="256" cy="256" r="112" fill="url(#dia)"/></svg>'
    ).encode()


def saved_accent(data_dir: Path | None) -> str | None:
    """The accent the window last saw (``app-accent``), so the next start matches it."""
    try:
        value = (data_dir / "app-accent").read_text().strip() if data_dir else ""
    except OSError:
        return None
    return value if re.fullmatch(r"[0-9a-f]{6}", value) else None


def _icon(accent: str | None = None) -> Any:
    from PySide6.QtGui import QIcon, QPixmap

    icon = QIcon()
    if accent:
        for size in (16, 24, 32, 48, 64, 128, 256):
            pixmap = QPixmap(size, size)
            if pixmap.loadFromData(tinted_svg(accent), "SVG"):
                icon.addPixmap(pixmap.scaled(size, size))
        if not icon.isNull():
            return icon
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

    from dia.desktop import runtime, service
    from dia.release import update

    app = QApplication.instance() or QApplication([sys.argv[0] or "dia"])
    if _send_to_running(view, task, background):
        # An existing shell already owns the service controls. Login must not
        # unhide it or create another window.
        return 0
    words = LABELS.get(language, LABELS["en"])
    app.setApplicationName("Dia")
    app.setApplicationDisplayName("Dia")
    app.setDesktopFileName("dia")  # Wayland app id: the menu entry, its icon on the taskbar
    accent = {"value": saved_accent(data_dir)}
    icon = _icon(accent["value"])
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
    # The page learns it is in Dia's window (and whether it draws the title bar) by its
    # user agent: it then reports its theme's accent for the window's icon.
    mark = USER_AGENT_MARK if frameless else USER_AGENT_MARK.split("/")[0]
    profile.setHttpUserAgent(f"{profile.httpUserAgent()} {mark}")
    state: dict[str, Any] = {"told": False, "quitting": False, "remember": lambda: None}

    class Window(QMainWindow):
        def resizeEvent(self, event: Any) -> None:
            super().resizeEvent(event)
            state["remember"]()

        def moveEvent(self, event: Any) -> None:
            super().moveEvent(event)
            state["remember"]()

        def closeEvent(self, event: Any) -> None:
            save_geometry()
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
    if saved := geometry.load(data_dir):  # where the window was last (DIA-54)
        screens = [
            (r.x(), r.y(), r.width(), r.height())
            for r in (screen.availableGeometry() for screen in app.screens())
        ]
        window.setGeometry(*geometry.fit((saved["x"], saved["y"], saved["w"], saved["h"]), screens))

    def save_geometry() -> None:
        # Maximised or not, the size to come back to is the normal one.
        r = window.normalGeometry()
        geometry.save(data_dir, (r.x(), r.y(), r.width(), r.height()), window.isMaximized())

    remember = QTimer(window)  # moving and resizing fire many events: write once they stop
    remember.setSingleShot(True)
    remember.setInterval(500)
    remember.timeout.connect(save_geometry)
    state["remember"] = remember.start
    web = QWebEngineView(window)
    web.setPage(Page(profile, web))
    window.setCentralWidget(web)
    if saved and saved["maximized"]:  # after the page exists: the state change tells it
        window.setWindowState(window.windowState() | Qt.WindowState.WindowMaximized)
    start = f"{base}#token={token}" + (f"&view={view}" if view else "") + (
        f"&task={task}" if task else "")  # fmt: skip
    # Poll in a worker: systemd, authentication and HTTP must never freeze Qt.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    jobs: dict[str, Any] = {}
    online: dict[str, Any] = {"value": None, "active": []}
    found: dict[str, Any] = {
        "release": None, "checked": -UPDATE_EVERY - 1.0, "manual": False, "at": "",
        "outcome": "source" if update.editable() else None,  # a checkout updates with git
    }  # fmt: skip
    update_action = QAction(app)
    update_action.setVisible(False)
    check_action = QAction(update_line(words, found["outcome"]), app)  # with the last result
    check_action.setEnabled(found["outcome"] != "source")

    shown = {"state": "starting"}  # what the offline page says (dia.desktop.offline.STATES)

    def offline() -> None:
        # The theme is read each time, so a theme chosen meanwhile shows up.
        try:  # Qt 6.5+: the system's light/dark setting, for a theme that follows it
            dark = app.styleHints().colorScheme() != Qt.ColorScheme.Light
        except AttributeError:
            dark = True
        colors = theme.variables(theme.current(data_dir), dark) if data_dir else {}
        page_language = language if language in offline_ui.WORDS else "en"
        web.setHtml(
            offline_page(page_language, frameless, accent["value"], colors, shown["state"]),
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

    done_action: dict[str, tuple[str, str]] = {"what": ("dia", "start")}
    # The tray menu has Polish and English texts; service words exist in more languages.
    language_key = language if language in runtime.STATE_LABELS["active"] else "en"

    def action_result(component: str, verb: str, ok: bool) -> str:
        name = "Dia" if component == "dia" else "Ollama"
        result = runtime.RESULT_LABELS["done" if ok else "failed"][language_key]
        return f"{name}: {runtime.VERB_LABELS[verb][language_key]} · {result}"

    def control(component: str, verb: str, quit_after: bool = False) -> None:
        if "action" in jobs:
            return
        if verb in ("stop", "restart"):
            text = words["active_tasks"].format(tasks=online["active"])
            if QMessageBox.question(window, "Dia", text) != QMessageBox.StandardButton.Yes:
                return
        done_action["what"] = (component, verb)
        jobs["action"] = (pool.submit(runtime.action, component, verb, config_source), quit_after)

    last_inspect = {"at": 0.0}  # polled often, so a finished check shows at once, run rarely

    def poll() -> None:
        if "logs" in jobs and jobs["logs"].done():
            try:
                output = jobs.pop("logs").result()
            except Exception as exc:
                output = str(exc)
            dialog = QMessageBox(window)
            dialog.setWindowTitle(words["logs_title"])
            dialog.setText(words["logs_text"])
            dialog.setDetailedText(output)
            dialog.exec()
        if "action" in jobs and jobs["action"][0].done():
            future, quit_after = jobs.pop("action")
            try:
                future.result()
                if quit_after:
                    quit_app()
                    return
                if tray:
                    tray.showMessage("Dia", action_result(*done_action["what"], ok=True))
            except Exception as exc:
                QMessageBox.warning(window, "Dia", str(exc))
        if "status" in jobs and jobs["status"].done():
            future = jobs.pop("status")
            try:
                result = future.result()
                api = result.get("api")
                ready = api is not None
                online["active"] = (api or {}).get("active", [])
                if not ready:
                    # The page is updated in place; setHtml only when it first appears.
                    state = offline_ui.offline_state(result.get("dia"))
                    if state != shown["state"]:
                        shown["state"] = state
                        if online["value"] is False:
                            call = f"window.diaOfflineState({json.dumps(state)})"
                            web.page().runJavaScript(f"window.diaOfflineState && {call}")
                if ready != online["value"]:
                    web.load(QUrl(start)) if ready else offline()
                    online["value"] = ready
                if tray:
                    dia_state = result.get("dia", {})
                    ollama_state = result.get("ollama", {})
                    tray.setToolTip(
                        f"Dia: {service_word(dia_state)} · Ollama: {service_word(ollama_state)}"
                    )
                    update_service_status(dia_state, ollama_state)
                    counts = (api or {}).get("counts") or {"running": 0, "waiting_for_you": 0}
                    counts_action.setText(
                        words["counts"].format(
                            running=counts["running"], waiting=counts["waiting_for_you"]
                        )
                    )
                    counts_action.setVisible(ready)
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
        if action == "accent":
            if edges[0] != accent["value"]:
                accent["value"] = edges[0]
                tinted = _icon(edges[0])
                app.setWindowIcon(tinted)
                window.setWindowIcon(tinted)
                if tray:
                    tray.setIcon(tinted)
                if data_dir:
                    with contextlib.suppress(OSError):
                        (data_dir / "app-accent").write_text(edges[0])
        elif action == "start-services":
            control("dia", "start")
        elif action == "show-logs":
            jobs.update(logs=pool.submit(runtime.logs, "dia"))
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
        if update.system_package():
            hint = update.package_update_hint()
            QMessageBox.information(
                window,
                "Dia",
                words["update_pm_text"].format(version=release["version"], hint=hint),
            )
            return
        text = words["update_ask"].format(version=release["version"])
        if online["active"]:
            text += "\n\n" + words["active_n"].format(n=len(online["active"]))
        if QMessageBox.question(window, "Dia", text) != QMessageBox.StandardButton.Yes:
            return
        update_action.setEnabled(False)
        update_action.setText(words["updating"])

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
            stamp = datetime.now().strftime("%H:%M")
            try:
                release = jobs.pop("update_check").result()
            except Exception:
                release = found["release"]  # offline or rate limited: try again later
                found["outcome"], found["at"] = "failed", stamp
            else:
                found["outcome"], found["at"] = ("found" if release else "up_to_date"), stamp
                if release is None:
                    found["release"] = None  # what was offered is no longer newer
            announce = (
                bool(release) and (found["release"] or {}).get("version") != release["version"]
            )
            if release:
                found["release"] = release
            set_update_text()  # the item says how the check went
            if tray and (announce or found["manual"]):
                shown = update_action.text() if found["release"] else check_action.text()
                tray.showMessage("Dia", shown, icon, 6000)
            found["manual"] = False
        if time.monotonic() - found["checked"] > UPDATE_EVERY:
            found["checked"] = time.monotonic()
            if (options(load_options())["check_updates"] and "update" not in jobs
                    and not update.editable()):  # fmt: skip
                jobs["update_check"] = pool.submit(update.latest)

    def set_update_text() -> None:
        release = found["release"]
        update_action.setVisible(bool(release))
        if release:
            key = "update_pm" if update.system_package() else "update_install"
            update_action.setText(words[key].format(version=release["version"]))
        version = (release or {}).get("version", "")
        check_action.setText(update_line(words, found["outcome"], found["at"], version))

    def check_now() -> None:
        """ "Check for updates" in the menu: look now, and say how it went."""
        if "update_check" in jobs or "update" in jobs:
            return
        if update.editable():
            found["outcome"] = "source"
        else:
            found["manual"], found["outcome"] = True, "checking"
            jobs["update_check"] = pool.submit(update.latest)
        set_update_text()

    def service_word(unit: dict) -> str:
        return runtime.state_label(
            unit.get("load", "loaded"), unit.get("active", "unknown"), language_key
        )

    verb_actions: dict = {}

    def update_service_status(dia_state: dict, ollama_state: dict) -> None:
        # Only the verbs that make sense in the unit's state are enabled (DIA-49).
        for component, unit in (("dia", dia_state), ("ollama", ollama_state)):
            allowed = unit.get("actions")
            for verb in runtime.VERB_LABELS:
                if (entry := verb_actions.get((component, verb))) is not None:
                    entry.setEnabled(allowed is None or verb in allowed)

        # The native tray menu is plain text, so the colour is an emoji dot.
        def dot(unit: dict) -> str:
            key = runtime.state_key(unit.get("load", "loaded"), unit.get("active", "unknown"))
            return {"active": "🟢", "failed": "🔴", "inactive": "🔴"}.get(key, "⚪")

        service_status.setText(
            f"Dia {dot(dia_state)} {service_word(dia_state)} | "
            f"Ollama {dot(ollama_state)} {service_word(ollama_state)}"
        )

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
        update_service_status({}, {})
        menu.addAction(service_status)
        # The same counts as the web UI and the widget (the API's `counts`).
        counts_action = QAction(menu)
        counts_action.setEnabled(False)
        counts_action.setVisible(False)
        menu.addAction(counts_action)
        check_action.triggered.connect(check_now)
        menu.addAction(check_action)
        update_action.triggered.connect(ask_update)
        menu.addAction(update_action)
        for component, label in (
            ("dia", words["services"]),
            ("ollama", words["ollama"]),
        ):
            submenu = menu.addMenu(label)
            for verb, words_ in runtime.VERB_LABELS.items():
                entry = submenu.addAction(
                    words_[language_key], lambda c=component, v=verb: control(c, v)
                )
                verb_actions[(component, verb)] = entry
            submenu.addAction(
                words["logs"],
                lambda c=component: jobs.update(logs=pool.submit(runtime.logs, c)),
            )
        menu.addAction(
            words["quit_all"],
            lambda: control("dia", "stop", True),
        )
        menu.addAction(words["quit_window"], quit_app)

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
