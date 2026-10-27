"""The camera, only when you switch it on: "Dia, co widzisz w kamerze?",
"czy wyglądam dobrze na call?", "co to za część?" (you hold it up).

Off by default, like screen access. Switch it on in the app (📷), with
``POST /api/camera``, or by saying "włącz kamerę"; "wyłącz kamerę" switches it
off. While it is on, Dia takes a single photo only when you ask, shows a
notification each time, hands the photo to an agent that can read images and
deletes it afterwards (``keep = true`` keeps it). Nothing is recorded or
watched in the background, and every photo is in the audit log.

    [camera]
    device = "/dev/video0"
    agent = "claude"          # an agent that can read images (default agent)
    # command = ["ffmpeg", "-f", "v4l2", "-i", "{device}", "-frames:v", "1", "{output}"]
    keep = false
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dia.agents import AgentRequest, Mode
from dia.workspace import run

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

# One frame, a second in: the first frames of many webcams are still dark.
COMMAND = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel",
    "error",
    "-f",
    "v4l2",
    "-i",
    "{device}",
    "-ss",
    "1",
    "-frames:v",
    "1",
    "-y",
    "{output}",
]

PROMPT = """\
The file photo.jpg in the current directory is a photo the user just took with
their camera, to ask you about it. Look at it (read the image) and answer in
{language}:

{question}

Be brief and concrete. Do not describe the person's body or guess their
identity, age or mood beyond what the question needs.
"""


async def capture(output: Path, device: str, configured: list[str] | None = None) -> None:
    argv = list(configured or COMMAND)
    if not shutil.which(argv[0]):
        raise RuntimeError(f"{argv[0]} is not installed")
    argv = [a.replace("{device}", device).replace("{output}", str(output)) for a in argv]
    code, out = await run(argv, output.parent, 30)
    for _ in range(10):
        if output.exists() and output.stat().st_size:
            return
        await asyncio.sleep(0.1)
    raise RuntimeError(f"the camera did not take a photo: {out.strip()[-300:] or code}")


async def look(dia: Orchestrator, question: str) -> str:
    """Take one photo and have an agent answer ``question`` about it."""
    if not dia.camera_enabled:
        raise PermissionError("camera access is off")
    options = dia.config.section("camera")
    root = dia.config.data_dir / "camera"
    folder = root / datetime.now().strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    photo = folder / "photo.jpg"
    await dia.emit("camera", None, "looking", {"state": "looking"})
    if shutil.which("notify-send"):
        sign = ["notify-send", "--app-name=Dia", "-u", "low", "Dia", "📷 Dia robi zdjęcie"]
        await run(sign, folder, 5)
    dia.audit("camera.look", None, question[:200])
    try:
        await capture(photo, str(options.get("device", "/dev/video0")), options.get("command"))
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
            purpose="camera",
        )
        if not result.success:
            raise RuntimeError(f"{agent.name} could not look at the photo: {result.error}")
        return result.summary.strip()
    finally:
        if not options.get("keep"):
            shutil.rmtree(folder, ignore_errors=True)
        await dia.emit("camera", None, "done", {"state": "done"})
