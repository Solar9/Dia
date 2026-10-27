"""Dia's ring in the terminal: ``dia version`` and the setup wizard show it.

Drawn from the same geometry as ``assets/dia.svg`` (a ring and a disc with the
purple gradient), two pixels per character cell with half blocks in true
colour. Plain text when the output is not a terminal or ``NO_COLOR`` is set.
"""

from __future__ import annotations

import os
import sys

STOPS = [(0.0, (0xF0, 0xB5, 0xFA)), (0.46, (0xA6, 0x22, 0xFA)), (0.72, (0x72, 0x00, 0xE8)),
         (1.0, (0x35, 0x00, 0x7B))]  # fmt: skip


def _gradient(t: float) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, t))
    for (a, ca), (b, cb) in zip(STOPS, STOPS[1:], strict=False):
        if t <= b:
            f = (t - a) / (b - a)
            return tuple(round(x + (y - x) * f) for x, y in zip(ca, cb, strict=True))  # type: ignore[return-value]
    return STOPS[-1][1]


def _pixel(x: float, y: float) -> tuple[int, int, int] | None:
    """The colour at (x, y) in [0, 1]², or None where the icon is transparent."""
    dx, dy = (x - 0.5) * 512, (y - 0.5) * 512
    r = (dx * dx + dy * dy) ** 0.5
    if 181 <= r <= 235 or r <= 112:  # the ring (208 ± 27) and the disc
        return _gradient((x + y) / 2)
    return None


def ring(size: int = 12) -> list[str]:
    """``size`` text rows (``2 * size`` pixels square); true-colour half blocks."""
    width, height = size * 2, size * 2
    rows = []
    for row in range(size):
        cells = []
        for col in range(width):
            x = (col + 0.5) / width
            top = _pixel(x, (2 * row + 0.5) / height)
            bottom = _pixel(x, (2 * row + 1.5) / height)
            if top and bottom:
                cells.append(
                    f"\033[38;2;{top[0]};{top[1]};{top[2]}m\033[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m▀\033[0m"
                )
            elif top:
                cells.append(f"\033[38;2;{top[0]};{top[1]};{top[2]}m▀\033[0m")
            elif bottom:
                cells.append(f"\033[38;2;{bottom[0]};{bottom[1]};{bottom[2]}m▄\033[0m")
            else:
                cells.append(" ")
        rows.append("".join(cells))
    return rows


def colour() -> bool:
    return (
        sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    )


def banner(lines: list[str], size: int = 8) -> str:
    """The ring with text beside it (or just the text without colour)."""
    if not colour():
        return "\n".join(lines)
    art = ring(size)
    pad = max(0, (len(art) - len(lines)) // 2)
    text = [""] * pad + lines + [""] * len(art)
    return "\n".join(f"{a}   {t}".rstrip() for a, t in zip(art, text, strict=False))
