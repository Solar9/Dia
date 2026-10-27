"""Install the KDE Plasma 6 widget (``dia plasmoid install``)."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent / "plasmoid"
PLUGIN_ID = "org.dia.plasmoid"


def dia_command() -> str:
    """How the widget calls Dia: this very installation, whatever PATH Plasma has."""
    return f"{shlex.quote(sys.executable)} -m dia"


def _kpackagetool() -> str:
    tool = shutil.which("kpackagetool6")
    if not tool:
        raise RuntimeError("kpackagetool6 not found: this needs KDE Plasma 6")
    return tool


def installed() -> bool | None:
    """Whether the widget is installed (None: this is not KDE Plasma 6)."""
    tool = shutil.which("kpackagetool6")
    if not tool:
        return None
    show = subprocess.run([tool, "-t", "Plasma/Applet", "--show", PLUGIN_ID], capture_output=True)
    return show.returncode == 0


def install() -> str:
    tool = _kpackagetool()
    from dia.desktop import install_icons

    install_icons()  # the widget's own icon in the panel's list and buttons
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / PLUGIN_ID
        shutil.copytree(PACKAGE, package)
        config = package / "contents" / "config" / "main.xml"
        config.write_text(config.read_text().replace("@DIA_COMMAND@", dia_command()))
        installed = (
            subprocess.run(
                [tool, "-t", "Plasma/Applet", "--show", PLUGIN_ID], capture_output=True
            ).returncode
            == 0
        )
        action = "--upgrade" if installed else "--install"
        result = subprocess.run(
            [tool, "-t", "Plasma/Applet", action, str(package)], capture_output=True, text=True
        )
    if result.returncode != 0:
        raise RuntimeError(f"kpackagetool6 failed: {(result.stderr or result.stdout).strip()}")
    return (
        f"{'updated' if installed else 'installed'} the Dia widget; add it with right-click on "
        "the panel → Add or Manage Widgets → Dia"
        + (" (restart plasmashell to see the update)" if installed else "")
    )


def uninstall() -> str:
    tool = _kpackagetool()
    result = subprocess.run(
        [tool, "-t", "Plasma/Applet", "--remove", PLUGIN_ID], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"kpackagetool6 failed: {(result.stderr or result.stdout).strip()}")
    return "removed the Dia widget"
