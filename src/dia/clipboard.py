"""The clipboard, when you ask: "co mam w schowku?", "przetłumacz schowek na
angielski", "popraw tekst w schowku", "skopiuj mi ten link".

Dia reads the clipboard only when a request needs it, never in the
background, and each read is in the audit log. A transformed text goes back
to the clipboard, ready to paste. Works with Wayland (wl-clipboard) and X11
(xclip or xsel); ``[skills.clipboard] read_command`` / ``write_command``
override the tools.
"""

from __future__ import annotations

import asyncio
import shutil

READERS = [
    ["wl-paste", "--no-newline"],
    ["xclip", "-selection", "clipboard", "-o"],
    ["xsel", "--clipboard", "--output"],
]
WRITERS = [
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
]


def _pick(candidates: list[list[str]], configured: list[str] | None) -> list[str]:
    if configured:
        return list(configured)
    for argv in candidates:
        if shutil.which(argv[0]):
            return argv
    raise RuntimeError("no clipboard tool found: install wl-clipboard (Wayland) or xclip")


async def read(configured: list[str] | None = None) -> str:
    proc = await asyncio.create_subprocess_exec(
        *_pick(READERS, configured),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(proc.communicate(), 10)
    if proc.returncode != 0 and not out:
        message = err.decode(errors="replace").strip()
        if "nothing is copied" in message.lower() or "no selection" in message.lower():
            return ""
        raise RuntimeError(f"could not read the clipboard: {message[:200]}")
    return out.decode(errors="replace")


async def write(text: str, configured: list[str] | None = None) -> None:
    proc = await asyncio.create_subprocess_exec(
        *_pick(WRITERS, configured),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,  # wl-copy and xclip stay to serve the selection
    )
    proc.stdin.write(text.encode())
    await proc.stdin.drain()
    proc.stdin.close()
    try:
        await asyncio.wait_for(proc.wait(), 2)
    except TimeoutError:
        pass  # still serving the clipboard in the background: that is how they work
