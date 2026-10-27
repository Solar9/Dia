"""Screen awareness, opt-in: "Dia, dlaczego ten kod nie działa?" with the editor
open, and Dia looks at the screen instead of you copying the error.

Off until you switch it on (Settings, the eye switch in the sidebar,
"możesz patrzeć na ekran", ``dia screen on``) and off again with one click or
"nie patrz na ekran". Every look shows a notification ("Dia patrzy na
ekran") and an event in the app; the screenshot is given to one agent,
read-only, and deleted right after (``keep = true`` keeps it in
``<data_dir>/screen``, mode 700).

    [screen]
    agent = "claude"          # one that can read images (Claude Code does)
    command = ["spectacle", "-b", "-n", "-f", "-o", "{output}"]   # default: detected
"""

from __future__ import annotations

import asyncio
import shlex
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dia.agents import AgentRequest, Mode
from dia.workspace import run

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

# Tried in order: KDE (also Wayland), wlroots compositors, GNOME, X11.
CAPTURE_COMMANDS = [
    ["spectacle", "-b", "-n", "-f", "-o", "{output}"],
    ["grim", "{output}"],
    ["gnome-screenshot", "-f", "{output}"],
    ["scrot", "-o", "{output}"],
    ["import", "-window", "root", "{output}"],
]

PROMPT = """\
The file screenshot.png in the current directory is a screenshot of the
user's screen right now. Look at it (read the image) and answer in {language}:

{question}

If it shows code, an error, a log or a game, say what you see that matters:
which program or file, the exact error, and what to do about it. Be brief.
"""


def capture_command(configured: list[str] | str | None = None) -> list[str] | None:
    if configured:
        argv = shlex.split(configured) if isinstance(configured, str) else list(configured)
        if not any("{output}" in a for a in argv):
            argv.append("{output}")  # every tool here takes the file name last
        return argv
    for argv in CAPTURE_COMMANDS:
        if shutil.which(argv[0]):
            return argv
    return None


async def capture(output: Path, configured: list[str] | None = None) -> None:
    argv = capture_command(configured)
    if not argv:
        raise RuntimeError(
            "no screenshot tool found (spectacle, grim, gnome-screenshot, scrot or ImageMagick)"
        )
    code, out = await run([a.replace("{output}", str(output)) for a in argv], output.parent, 30)
    for _ in range(20):  # some tools write the file a moment after they exit
        if output.exists() and output.stat().st_size:
            return
        await asyncio.sleep(0.1)
    raise RuntimeError(f"the screenshot failed: {out.strip()[-300:] or f'exit code {code}'}")


async def look(dia: Orchestrator, question: str) -> str:
    """Take a screenshot and have an agent answer ``question`` about it."""
    if not dia.screen_enabled:
        raise PermissionError("screen access is off")
    options = dia.config.section("screen")
    folder = dia.config.data_dir / "screen" / datetime.now().strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, mode=0o700)
    (dia.config.data_dir / "screen").chmod(0o700)
    shot = folder / "screenshot.png"
    await dia.emit("screen", None, "looking", {"state": "looking"})
    if shutil.which("notify-send"):  # the visible sign, whatever channels are running
        sign = ["notify-send", "--app-name=Dia", "-u", "low", "Dia", "👁 Dia patrzy na ekran"]
        await run(sign, folder, 5)
    dia.audit("screen.look", None, question[:200])
    try:
        await capture(shot, options.get("command"))
        agent = dia.config.agent(options.get("agent"))
        language = {"pl": "Polish", "en": "English"}.get(dia.config.language, "English")
        _, result = await dia.call_agent(
            agent,
            AgentRequest(
                prompt=PROMPT.format(language=language, question=question or "What do you see?"),
                cwd=folder,
                mode=Mode.READ_ONLY,
                timeout=int(options.get("timeout", 180)),
            ),
            purpose="screen",
        )
        if not result.success:
            raise RuntimeError(f"{agent.name} could not look at the screen: {result.error}")
        return result.summary.strip()
    finally:
        if not options.get("keep"):
            shutil.rmtree(folder, ignore_errors=True)
        await dia.emit("screen", None, "done", {"state": "done"})
