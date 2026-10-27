"""Start Dia with one click: a menu entry, a desktop icon, start at login.

``dia shortcut install`` (the setup wizard does it for you) adds:

- **Linux**: ``Dia`` in the application menu (``~/.local/share/applications``),
  optionally on the desktop and in autostart, with Dia's icon installed into
  the icon theme (``hicolor``). KDE, GNOME and the rest pick it up.
- **Windows**: a Start menu shortcut (and optionally one on the desktop, and
  in Startup).
- **macOS**: ``~/Applications/Dia.command`` (and optionally on the desktop).

Every shortcut runs ``dia app``: it starts everything Dia needs in the
background (``dia serve``: the UI, voice, Discord, schedules, watchers; or
the systemd service when installed) if it is not running yet, then opens
Dia's window. ``dia up`` does the same from a terminal.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ICONS = Path(__file__).resolve().parent / "ui" / "static" / "icons"
NAME = "Dia"
# The icon's name in the icon theme. Not "dia": that is the Dia diagram editor's, and
# themes such as Papirus ship their own icon for it, which would win over ours.
ICON_NAME = "io.github.solar9.dia"
COMMENT = "Your assistant for coding agents, games and the computer"


def launch_command(config: Path | None = None) -> list[str]:
    """How a shortcut starts this very installation of Dia (whatever PATH it has)."""
    argv = [sys.executable, "-m", "dia"]
    if config:
        argv += ["--config", str(Path(config).resolve())]
    return [*argv, "app"]


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def desktop_dir() -> Path:
    """The user's desktop folder (localised: "Pulpit", "Schreibtisch"...)."""
    if shutil.which("xdg-user-dir"):
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    return Path.home() / "Desktop"


def desktop_entry(command: list[str], autostart: bool = False) -> str:
    exec_line = " ".join(shlex.quote(part) for part in command)
    if autostart:  # at login: start Dia in the background, no window
        exec_line = exec_line.removesuffix(" app") + " app --background"
    return f"""\
[Desktop Entry]
Type=Application
Name={NAME}
GenericName=AI assistant
Comment={COMMENT}
Exec={exec_line}
Icon={ICON_NAME}
Terminal=false
Categories=Utility;Development;
Keywords=AI;assistant;agents;claude;codex;
StartupNotify=true
StartupWMClass=Dia
"""


def install_icons() -> list[Path]:
    """Dia's icon in the user's icon theme, so its ``Icon=`` resolves everywhere."""
    written = []
    theme = _data_home() / "icons" / "hicolor"
    for png in sorted(ICONS.glob("dia-*.png")):
        size = png.stem.split("-")[1]
        target = theme / f"{size}x{size}" / "apps" / f"{ICON_NAME}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(png, target)
        written.append(target)
    svg = theme / "scalable" / "apps" / f"{ICON_NAME}.svg"
    svg.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICONS / "dia.svg", svg)
    written.append(svg)
    # Dia 0.2.0 installed them as "dia" (the diagram editor's name): remove those
    # copies, only where they are ours byte for byte.
    for old in theme.glob("*/apps/dia.*"):
        size = old.parent.parent.name.split("x")[0]
        ours = ICONS / ("dia.svg" if old.suffix == ".svg" else f"dia-{size}.png")
        if ours.exists() and old.read_bytes() == ours.read_bytes():
            old.unlink()
    if shutil.which("gtk-update-icon-cache"):
        subprocess.run(["gtk-update-icon-cache", "-q", "-t", str(theme)], capture_output=True)
    return written


def _linux(command: list[str], desktop: bool, autostart: bool) -> list[str]:
    install_icons()
    done = []
    entry = desktop_entry(command)
    menu = _data_home() / "applications" / "dia.desktop"
    menu.parent.mkdir(parents=True, exist_ok=True)
    menu.write_text(entry)
    menu.chmod(0o755)
    done.append(f"menu: {menu}")
    if desktop:
        target = desktop_dir() / "dia.desktop"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry)
        target.chmod(0o755)  # KDE and GNOME run only executable (trusted) launchers
        if shutil.which("gio"):
            subprocess.run(["gio", "set", str(target), "metadata::trusted", "true"],
                           capture_output=True)  # fmt: skip
        done.append(f"desktop: {target}")
    if autostart:
        target = _config_home() / "autostart" / "dia.desktop"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(desktop_entry(command, autostart=True))
        done.append(f"start at login: {target}")
    else:
        (_config_home() / "autostart" / "dia.desktop").unlink(missing_ok=True)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", "-q", str(menu.parent)], capture_output=True)
    return done


def _windows_shortcut(path: Path, command: list[str]) -> None:
    pythonw = Path(command[0]).with_name("pythonw.exe")  # no console window
    target = str(pythonw if pythonw.exists() else command[0])
    arguments = subprocess.list2cmdline(command[1:])
    icon = ICONS / "dia.ico"
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:DIA_LNK);"
        "$s.TargetPath=$env:DIA_TARGET;$s.Arguments=$env:DIA_ARGS;"
        "$s.Description='Dia';"
        + ("$s.IconLocation=$env:DIA_ICON;" if icon.exists() else "")
        + "$s.Save()"
    )
    env = {**os.environ, "DIA_LNK": str(path), "DIA_TARGET": target, "DIA_ARGS": arguments,
           "DIA_ICON": str(icon)}  # fmt: skip
    subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, check=True)


def _windows(command: list[str], desktop: bool, autostart: bool) -> list[str]:
    appdata = Path(os.environ["APPDATA"])
    programs = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    done = []
    _windows_shortcut(programs / "Dia.lnk", command)
    done.append(f"Start menu: {programs / 'Dia.lnk'}")
    if desktop:
        target = Path.home() / "Desktop" / "Dia.lnk"
        _windows_shortcut(target, command)
        done.append(f"desktop: {target}")
    if autostart:
        target = programs / "Startup" / "Dia.lnk"
        _windows_shortcut(target, [*command, "--background"])
        done.append(f"start at login: {target}")
    else:
        (programs / "Startup" / "Dia.lnk").unlink(missing_ok=True)
    return done


def _macos(command: list[str], desktop: bool) -> list[str]:
    script = "#!/bin/sh\nexec " + " ".join(shlex.quote(p) for p in command) + "\n"
    done = []
    targets = [Path.home() / "Applications" / "Dia.command"]
    if desktop:
        targets.append(Path.home() / "Desktop" / "Dia.command")
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script)
        target.chmod(0o755)
        done.append(str(target))
    return done


def install(config: Path | None = None, desktop: bool = True, autostart: bool = False) -> list[str]:
    command = launch_command(config)
    if sys.platform.startswith("win"):
        return _windows(command, desktop, autostart)
    if sys.platform == "darwin":
        return _macos(command, desktop)
    return _linux(command, desktop, autostart)


def state() -> dict[str, bool]:
    """Which shortcuts are there: in the menu, on the desktop, at login."""
    if appdata := os.environ.get("APPDATA"):
        programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        return {"menu": (programs / "Dia.lnk").exists(),
                "desktop": (Path.home() / "Desktop" / "Dia.lnk").exists(),
                "autostart": (programs / "Startup" / "Dia.lnk").exists()}  # fmt: skip
    if sys.platform == "darwin":
        return {"menu": (Path.home() / "Applications" / "Dia.command").exists(),
                "desktop": (Path.home() / "Desktop" / "Dia.command").exists(),
                "autostart": False}  # fmt: skip
    return {
        "menu": (_data_home() / "applications" / "dia.desktop").exists(),
        "desktop": (desktop_dir() / "dia.desktop").exists(),
        "autostart": (_config_home() / "autostart" / "dia.desktop").exists(),
    }


def uninstall() -> list[str]:
    removed = []
    candidates = [
        _data_home() / "applications" / "dia.desktop",
        desktop_dir() / "dia.desktop",
        _config_home() / "autostart" / "dia.desktop",
        Path.home() / "Applications" / "Dia.command",
        Path.home() / "Desktop" / "Dia.command",
    ]
    if appdata := os.environ.get("APPDATA"):
        programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        candidates += [programs / "Dia.lnk", programs / "Startup" / "Dia.lnk",
                       Path.home() / "Desktop" / "Dia.lnk"]  # fmt: skip
    for path in candidates:
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return removed


def set_autostart(config: Path | None, enabled: bool) -> None:
    """Change only the login entry, preserving menu and desktop shortcuts."""
    target = _config_home() / "autostart" / "dia.desktop"
    if enabled:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(desktop_entry(launch_command(config), autostart=True))
    else:
        target.unlink(missing_ok=True)
