"""`dia serve` commands."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from typing import Any

from dia.core.config import Config, ConfigError, load_config
from dia.core.orchestrator import Orchestrator


async def cmd_serve(config: Config, args: argparse.Namespace) -> int:
    """Run all configured channels (Discord, ...) until interrupted."""
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    dia = Orchestrator(config)
    channels = [config.channel(name, dia) for name in config.channels]
    if config.ui.get("enabled", True):
        try:
            from dia.channels.api import ApiChannel
        except ImportError:
            print("UI disabled: install it with pip install 'dia[ui]'", file=sys.stderr)
        else:
            channels.append(ApiChannel("ui", config.ui, dia))
    if not channels:
        print("nothing to serve: add e.g. [channels.discord] or enable [ui]", file=sys.stderr)
        return 2
    for channel in channels:
        if problem := channel.check():
            print(f"channel {channel.name}: {problem}", file=sys.stderr)
            return 2
    print(f"serving: {', '.join(c.name for c in channels)} (Ctrl+C to stop)", file=sys.stderr)
    from dia.core import sandbox
    from dia.desktop.health import interrupted, supervise

    if not sandbox.enabled(config):
        why = (
            "bubblewrap is missing or unusable"
            if not sandbox.bwrap_works()
            else "[sandbox] enabled = false"
        )
        print(
            f"WARNING: agents will run WITHOUT a sandbox ({why}). "
            "Install bubblewrap or set [sandbox] enabled = true.",
            file=sys.stderr,
        )
    if stuck := interrupted(dia):
        print(f"{len(stuck)} task(s) were interrupted by the restart", file=sys.stderr)
    # (name, how to start it): each runs supervised, restarted if it crashes.
    jobs: list[tuple[str, Any]] = [(channel.name, channel.run) for channel in channels]
    if config.ci.get("watch", True):
        from dia.quality.ci import CIWatcher

        jobs.append(("ci", CIWatcher(dia).run))
    from dia.work.schedule import Scheduler

    jobs.append(("scheduler", Scheduler(dia).run))
    from dia.work.goals import GoalWatcher

    jobs.append(("goals", GoalWatcher(dia).run))
    from dia.knowledge.suggestions import SuggestionWatcher

    jobs.append(("suggestions", SuggestionWatcher(dia).run))
    if config.section("system").get("watch", True):
        from dia.desktop.system import SystemWatcher

        jobs.append(("system", SystemWatcher(dia).run))
    if dia.memory and getattr(dia.memory, "semantic_index", lambda: None)():
        jobs.append(("memory index", lambda: _keep_index_fresh(dia)))
    from dia.desktop.push import Push
    from dia.desktop.push import available as push_available

    if push_available():
        push = Push(dia)
        dia.listeners.append(push.on_event)
        dia.store.listeners.append(push.on_task_saved)
    if config.section("issues").get("enabled", bool(config.section("issues"))):
        from dia.work.issues import IssueWatcher

        jobs.append(("issues", IssueWatcher(dia).run))
    if config.watch.get("enabled", bool(config.watch)):
        from dia.work.watch import ProjectWatcher

        jobs.append(("watch", ProjectWatcher(dia).run))
    try:
        await asyncio.gather(*(supervise(dia, name, start) for name, start in jobs))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


async def _keep_index_fresh(dia: Orchestrator) -> None:
    """Refresh the semantic index in the background while `dia serve` runs."""
    while True:
        semantic = getattr(dia.memory, "semantic_index", None)  # not every memory has one
        index = semantic() if semantic else None
        if index:
            try:
                await asyncio.to_thread(index.update)
            except Exception as exc:
                print(f"memory index: {exc}", file=sys.stderr)
        await asyncio.sleep(1800)


def _ui_url(config: Config) -> tuple[str, str]:
    from dia.channels.api import DEFAULT_PORT, api_token

    port = int(config.ui.get("port", DEFAULT_PORT))
    return f"http://127.0.0.1:{port}/", api_token(config.data_dir)


def _ui_running(url: str) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=1):
            return True
    except OSError:
        return False


async def cmd_ui(config: Config, args: argparse.Namespace) -> int:
    """Print (or open) the address of the web UI, with the token to sign in."""
    url, token = _ui_url(config)
    if args.token:
        print(token)
        return 0
    full = f"{url}#token={token}"
    if not _ui_running(url):
        print(
            "note: the UI is not running; start `dia serve` (or `dia service install`)",
            file=sys.stderr,
        )
    print(full)
    if args.open:
        import webbrowser

        webbrowser.open(full)
    return 0


async def cmd_mobile(config: Config, args: argparse.Namespace) -> int:
    """Pair, list and revoke devices (phones) that may use Dia remotely."""
    from dia.channels.api import DEFAULT_PORT
    from dia.core.devices import Devices, public_url

    devices = Devices(config.data_dir)
    if args.action == "list":
        for device in devices.list():
            seen = device.last_seen or "never used"
            print(f"  {device.id}  {device.name:<16} paired {device.created_at}  last {seen}")
        if not devices.list():
            print("no paired devices (dia mobile pair --name phone)")
        return 0
    if args.action == "revoke":
        if not args.device:
            print("error: which device? (id or name, see dia mobile list)", file=sys.stderr)
            return 1
        gone = devices.revoke(args.device)
        print(f"revoked {gone.name}" if gone else f"no device {args.device}")
        return 0 if gone else 1

    if not config.ui.get("remote"):
        print(
            "note: remote access is off; set [ui] remote = true (docs/MOBILE.md) and restart",
            file=sys.stderr,
        )
    device, token = devices.pair(args.name)
    url = public_url(config.ui, int(config.ui.get("port", DEFAULT_PORT)))
    print(f"paired '{device.name}' (id {device.id}); shown only now, revoke it if it leaks")
    if not url:
        print(f"token: {token}\nset [ui] public_url to get a link and a QR code")
        return 0
    link = f"{url}#token={token}"
    try:
        import qrcode

        qr = qrcode.QRCode(border=2)
        qr.add_data(link)
        qr.print_ascii(invert=True)
    except ImportError:
        print("(pip install 'dia[mobile]' to show a QR code here)", file=sys.stderr)
    print(f"open on the phone: {link}")
    return 0


async def cmd_app(config: Config, args: argparse.Namespace) -> int:
    """Open Dia in its own window, starting `dia serve` in the background if needed."""
    import shutil
    import subprocess

    from dia.desktop import appwindow, runtime, service

    url, token = _ui_url(config)
    background = getattr(args, "background", False)
    native = appwindow.available() and not args.browser
    # The native shell remains usable with a stopped backend. A login launch
    # explicitly starts services; an ordinary open preserves a stopped service.
    managed = (service.unit_path().parent / runtime.TARGET).exists()
    start_native = (
        native
        and service.check() is None
        and (background or (not managed and not _ui_running(url)))
    )
    if not (native and service.check() is None) and (
        background or (not managed and not _ui_running(url))
    ):
        if service.check() is None and (managed or service.installed()):
            try:
                await asyncio.to_thread(runtime.action, "dia", "start", config.source)
            except (RuntimeError, OSError) as exc:
                print(f"Could not start Dia: {exc}", file=sys.stderr)
                if not native:
                    return 1
        elif not _ui_running(url):
            log_file = config.data_dir / "serve.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            argv = [sys.executable, "-m", "dia"]
            if config.source:
                argv += ["--config", str(config.source)]
            with log_file.open("a") as out:
                subprocess.Popen(
                    [*argv, "serve"],
                    stdout=out,
                    stderr=out,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
    view, task = getattr(args, "view", None), getattr(args, "task", None)
    full = (
        f"{url}#token={token}"
        + (f"&view={view}" if view else "")
        + (f"&task={task}" if task else "")
    )
    if native:
        source = config.source

        def app_options() -> dict:
            try:
                return (load_config(source) if source else config).section("app")
            except ConfigError:
                return config.section("app")

        return appwindow.run(
            url,
            token,
            language=config.language,
            view=view,
            task=task,
            data_dir=config.data_dir,
            load_options=app_options,
            background=background,
            config_source=source,
            start_services=start_native,
        )
    if background:
        return 0
    for _ in range(50):
        if _ui_running(url):
            break
        await asyncio.sleep(0.2)
    else:
        print("Dia is stopped. Start it with: dia runtime start", file=sys.stderr)
        return 1
    webview: Any = None
    with contextlib.suppress(ImportError):
        import webview as pywebview

        webview = pywebview
    if webview and not args.browser:
        webview.create_window("Dia", full, width=1280, height=820, min_size=(720, 480))
        try:
            webview.start(icon=str(appwindow.ICONS / "dia-256.png"))
        except TypeError:  # pywebview before 5 has no window icon
            webview.start()
        return 0
    for browser in (
        "chromium",
        "google-chrome",
        "google-chrome-stable",
        "brave",
        "brave-browser",
        "microsoft-edge",
        "vivaldi",
    ):
        if shutil.which(browser):  # an app window without tabs or address bar
            subprocess.Popen(
                [browser, f"--app={full}"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return 0
    import webbrowser

    webbrowser.open(full)
    return 0


def add_ui(sub: argparse._SubParsersAction) -> None:
    ui = sub.add_parser("ui", help="address of the web UI (with the sign-in token)")
    ui.add_argument("--open", action="store_true", help="open it in the browser")
    ui.add_argument("--token", action="store_true", help="print only the API token")
    ui.set_defaults(fn=cmd_ui)


def add_mobile(sub: argparse._SubParsersAction) -> None:
    mobile = sub.add_parser("mobile", help="pair your phone with Dia (see docs/MOBILE.md)")
    mobile.add_argument("action", choices=["pair", "list", "revoke"])
    mobile.add_argument("device", nargs="?", help="revoke: the device's id or name")
    mobile.add_argument("--name", default="phone", help="pair: a name for the device")
    mobile.set_defaults(fn=cmd_mobile)


def add_app(sub: argparse._SubParsersAction) -> None:
    for name, help_text in (
        ("app", "start everything Dia needs (if not running) and open its window"),
        ("up", "the same as `dia app`: one command to start Dia"),
    ):
        app = sub.add_parser(name, help=help_text)
        app.add_argument("--browser", action="store_true", help="a browser window, not Dia's own")
        app.add_argument("--background", action="store_true", help="start Dia, open no window")
        app.add_argument("--view", help="open this tab",
                         choices=["inbox", "tasks", "missions", "chat", "cli", "memory",
                                  "status", "usage", "settings"])  # fmt: skip
        app.add_argument("--task", metavar="ID", help="open this task")
        app.set_defaults(fn=cmd_app)


def add_serve(sub: argparse._SubParsersAction) -> None:
    sub.add_parser("serve", help="run the configured channels (e.g. Discord bot)").set_defaults(
        fn=cmd_serve
    )


COMMANDS = {
    "ui": add_ui,
    "mobile": add_mobile,
    "app": add_app,
    "serve": add_serve,
}
