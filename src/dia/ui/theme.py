"""The UI's theme, kept by Dia for every place she is shown (docs/UI.md, Themes).

``ui-theme.json`` in Dia's data folder holds the app's theme (Dia's window and the
browser) and, for the phone and the KDE widget, either their own theme or None:
the same as the app. The colours are the theme's CSS variables."""

from __future__ import annotations

import os
import re
from pathlib import Path

from dia.core.jsonfile import read_json, write_json

STATIC_THEMES = Path(__file__).resolve().parent / "static" / "themes"
DEFAULT = "dark"
# Not a file: the app and the phone may follow the system's light/dark setting. The page
# decides (prefers-color-scheme); where only the server knows the name, it counts as dark.
SYSTEM = "system"
NAME = re.compile(r"[\w-]{1,64}")
VARIABLE = re.compile(r"^\s*--([\w-]+)\s*:\s*([^;]+);", re.MULTILINE)
HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
RGBA = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)")


def user_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "dia" / "themes"


def path_of(name: str) -> Path | None:
    """The theme's CSS file: yours first, then the built-in ones; None if there is none."""
    if not NAME.fullmatch(name):
        return None
    for folder in (user_dir(), STATIC_THEMES):
        path = folder / f"{name}.css"
        if path.is_file() and path.resolve().parent == folder.resolve():
            return path
    return None


SURFACES = ("phone", "widget")  # may have their own theme; None: the app's
FOLLOW_SYSTEM = ("name", "phone")  # the KDE widget is drawn by Plasma, not by a web page


def valid(key: str, value: object) -> bool:
    """Whether ``value`` is a theme that ``key`` ("name", "phone", "widget") can have."""
    if not isinstance(value, str):
        return False
    return (value == SYSTEM and key in FOLLOW_SYSTEM) or path_of(value) is not None


def concrete(name: str, dark: bool = True) -> str:
    """The theme file behind ``name``: "system" is dark or light, the rest is itself."""
    return ("dark" if dark else "light") if name == SYSTEM else name


def settings(data_dir: Path) -> dict[str, str | None]:
    """{"name": the app's theme, "phone": ..., "widget": ...}, unknown themes dropped."""
    raw = read_json(data_dir / "ui-theme.json", {})
    raw = raw if isinstance(raw, dict) else {}
    pick = lambda k, v: v if valid(k, v) else None  # noqa: E731
    return {
        "name": pick("name", raw.get("name")) or DEFAULT,
        **{k: pick(k, raw.get(k)) for k in SURFACES},
    }


def current(data_dir: Path, surface: str | None = None) -> str:
    """The theme of the app, or of the phone / the widget (their own, else the app's)."""
    chosen = settings(data_dir)
    return (chosen.get(surface) if surface in SURFACES else None) or chosen["name"] or DEFAULT


def update(data_dir: Path, changes: dict) -> dict[str, str | None]:
    """Change some of the settings: ``name`` a theme, ``phone`` / ``widget`` a theme or None."""
    chosen = settings(data_dir)
    for key, value in changes.items():
        if key not in ("name", *SURFACES):
            raise ValueError(f"unknown theme setting {key!r}")
        if value is None and key in SURFACES:
            chosen[key] = None
        elif valid(key, value):
            chosen[key] = value
        elif value == SYSTEM:
            raise ValueError("the KDE widget cannot follow the system's light/dark setting")
        else:
            raise ValueError(f"no theme {value!r}")
    write_json(data_dir / "ui-theme.json", chosen, indent=None, newline=True)
    return chosen


def variables(name: str, dark: bool = True) -> dict[str, str]:
    path = path_of(concrete(name, dark))
    return dict(VARIABLE.findall(path.read_text())) if path else {}


def qml_color(value: str) -> str | None:
    """A CSS colour as Qt reads it: #RRGGBB, or #AARRGGBB when it is see-through."""
    value = value.strip()
    if match := HEX.fullmatch(value):
        digits = match.group(1)
        return "#" + ("".join(c * 2 for c in digits) if len(digits) == 3 else digits).lower()
    if match := RGBA.fullmatch(value):
        r, g, b = (max(0, min(255, round(float(v)))) for v in match.group(1, 2, 3))
        alpha = match.group(4)
        rgb = f"{r:02x}{g:02x}{b:02x}"
        if alpha is None or float(alpha) >= 1:
            return f"#{rgb}"
        return f"#{round(max(0.0, float(alpha)) * 255):02x}{rgb}"
    return None


def colors(name: str, dark: bool = True) -> dict[str, str]:
    """The theme's colour variables, for the KDE widget (fonts, sizes... left out)."""
    return {
        key: color for key, value in variables(name, dark).items() if (color := qml_color(value))
    }
