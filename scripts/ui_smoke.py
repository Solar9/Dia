#!/usr/bin/env python
"""Offscreen smoke test of the web UI: every view in QtWebEngine against a live ApiChannel.

    python scripts/ui_smoke.py                      # all views, English and Polish
    python scripts/ui_smoke.py --lang de fr es      # other languages
    python scripts/ui_smoke.py --fail /api/usage    # make requests fail: errors must be visible

For each view it loads ``#view=<name>``, waits, then reports the console messages (there must
be none), how many error and loading states are on screen and how much text was drawn. It is
what docs/test-reports/ call the "offscreen smoke"; it does NOT replace looking at the window
(themes, the phone layout, the tray, a real Plasma shell): see the manual checklist there.
Needs the Qt extras (``pip install -e '.[qt]'``). Exit status 1 when something is wrong.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")

VIEWS = ["inbox", "tasks", "missions", "chat", "cli", "memory", "status", "usage", "settings"]
PROBE = """JSON.stringify({
  error: document.querySelectorAll('.content .state.error').length,
  loading: document.querySelectorAll('.content .state.loading').length,
  chars: (document.querySelector('.content') || {innerText: ''}).innerText.length,
  lang: document.documentElement.lang || null,
})"""


def serve(language: str, fail: list[str]):
    """A live ApiChannel on a free port, in its own thread (SQLite wants one thread)."""
    from aiohttp import web

    from dia.channels.api import ApiChannel
    from dia.core.config import parse_config
    from dia.core.orchestrator import Orchestrator

    tmp = Path(tempfile.mkdtemp())
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (tmp / "dia.toml").write_text("[dia]\n")
    config = parse_config(
        {
            "dia": {
                "data_dir": str(tmp / "data"),
                "default_agent": "fake",
                "language": language,
                "brain": ["rules"],
            },
            "agents": {"fake": {"type": "command", "argv": ["true"]}},
            "projects": {"demo": {"path": str(repo)}},
        },
        tmp / "dia.toml",
    )
    box: dict = {}

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def start() -> None:
            api = ApiChannel("ui", {"port": 0}, Orchestrator(config))
            runner = web.AppRunner(api.app())
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
            api.local_hosts.add(f"127.0.0.1:{port}")
            api.allowed_hosts.add(f"127.0.0.1:{port}")
            box.update(port=port, token=api.token)

        loop.run_until_complete(start())
        loop.run_forever()

    threading.Thread(target=run, daemon=True).start()
    while "port" not in box:
        pass
    return box


def smoke(language: str, views: list[str], fail: list[str]) -> bool:
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    box = serve(language, fail)
    app = QApplication.instance() or QApplication([])
    logs: list[tuple] = []

    class Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
            logs.append((level.name, message, source.rsplit("/", 1)[-1], line))

    view = QWebEngineView()
    page = Page(view)
    view.setPage(page)
    view.resize(1280, 800)
    if fail:  # reject matching fetches in the page itself
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        reject = "const _f=window.fetch;window.fetch=(p,...a)=>{patterns}.some("
        reject += "x=>String(p).includes(x))?Promise.reject(new Error('boom')):_f(p,...a);"
        script.setSourceCode(reject.replace("{patterns}", json.dumps(fail)))
        page.scripts().insert(script)
    results: dict[str, dict] = {}

    def step(i: int = 0) -> None:
        if i >= len(views):
            app.quit()
            return
        page.load(QUrl(f"http://127.0.0.1:{box['port']}/#token={box['token']}&view={views[i]}"))
        QTimer.singleShot(
            3000,
            lambda: page.runJavaScript(
                PROBE, lambda r: (results.__setitem__(views[i], json.loads(r)), step(i + 1))
            ),
        )

    QTimer.singleShot(0, step)
    QTimer.singleShot(90000, app.quit)
    app.exec()
    problems = [m for m in logs if m[0] != "InfoMessageLevel"]
    ok = len(results) == len(views) and not problems
    for name, r in results.items():
        stuck = r["loading"] and not fail
        shown = "ERROR-STATE" if r["error"] else "stuck-loading" if stuck else "ok"
        ok = ok and (fail or shown == "ok")
        print(f"  {name:9} {shown:12} text={r['chars']}")
    print(f"  console: {'clean' if not problems else problems}", flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lang", nargs="+", default=["en", "pl"])
    parser.add_argument("--views", nargs="+", default=VIEWS)
    parser.add_argument("--fail", nargs="*", default=[], help="reject fetches containing these")
    args = parser.parse_args()
    if len(args.lang) > 1:  # QtWebEngine does not survive several runs in one process
        codes = [
            subprocess.run(
                [sys.executable, __file__, "--lang", language, "--views", *args.views]
                + (["--fail", *args.fail] if args.fail else [])
            ).returncode
            for language in args.lang
        ]
        return int(any(codes))
    print(f"{args.lang[0]}:", flush=True)
    good = smoke(args.lang[0], args.views, args.fail)
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
