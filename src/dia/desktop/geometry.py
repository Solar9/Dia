"""Where Dia's window was last (DIA-54): size, position and whether it was maximised.

Kept in ``window.json`` in Dia's data folder (an atomic write, like every state file). A
saved position can be wrong later (a monitor unplugged, a smaller resolution), so it is
always fitted to the screens that exist now. Qt-free: the window only passes screens in."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dia.core.jsonfile import read_json, write_json

FILE = "window.json"
Rect = tuple[int, int, int, int]  # x, y, width, height


def load(data_dir: Path | None) -> dict[str, Any] | None:
    """The saved window, or None when there is none or it is unusable."""
    if data_dir is None:
        return None
    raw = read_json(data_dir / FILE, None)
    if not isinstance(raw, dict):
        return None
    numbers = {}
    for key in ("x", "y", "w", "h"):
        value = raw.get(key)
        if type(value) is not int:  # bool is an int too: not a coordinate
            return None
        numbers[key] = value
    if numbers["w"] <= 0 or numbers["h"] <= 0:
        return None
    return {**numbers, "maximized": raw.get("maximized") is True}


def save(data_dir: Path | None, rect: Rect, maximized: bool) -> None:
    if data_dir is None:
        return
    x, y, w, h = rect
    write_json(
        data_dir / FILE,
        {"x": x, "y": y, "w": w, "h": h, "maximized": maximized},
        indent=None,
        newline=True,
    )


def _overlap(a: Rect, b: Rect) -> int:
    width = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    height = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0, width) * max(0, height)


def fit(rect: Rect, screens: list[Rect], minimum: tuple[int, int] = (720, 480)) -> Rect:
    """``rect`` moved and shrunk to lie fully inside one of ``screens`` (their usable areas).

    The screen it mostly sits on is kept; one it sits on not at all (it was on a monitor that is
    gone) gives way to the nearest. Never smaller than ``minimum`` unless the screen is."""
    if not screens:
        return rect
    x, y, w, h = rect
    centre = (x + w // 2, y + h // 2)

    def distance(screen: Rect) -> int:
        sx, sy, sw, sh = screen
        dx = max(sx - centre[0], 0, centre[0] - (sx + sw))
        dy = max(sy - centre[1], 0, centre[1] - (sy + sh))
        return dx * dx + dy * dy

    best = max(screens, key=lambda s: _overlap(rect, s))
    if _overlap(rect, best) == 0:
        best = min(screens, key=distance)
    sx, sy, sw, sh = best
    w = min(max(w, min(minimum[0], sw)), sw)
    h = min(max(h, min(minimum[1], sh)), sh)
    x = min(max(x, sx), sx + sw - w)
    y = min(max(y, sy), sy + sh - h)
    return x, y, w, h
