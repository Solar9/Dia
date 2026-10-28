"""Updating Dia itself from its GitHub releases.

``latest()`` asks GitHub for the newest release and says whether it is newer
than the installed version. ``install()`` downloads that release's wheel,
checks it against the release's ``SHA256SUMS`` and installs it into the
environment Dia runs from. Nothing is installed without the user's click, and
a development checkout (an editable install) is never touched.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from importlib import metadata
from pathlib import Path
from typing import Any

import dia

REPO = "Solar9/Dia"
EXTRAS = "ui,mobile,chat"  # what scripts/install.sh installs
TIMEOUT = 15
# Private builds before the 27.10.2026 version reset kept numbers 0.1.0–0.2.3.
# Their tags are now v0.0.1–v0.0.5; installs that still report those numbers must
# treat every post-reset 0.1.x (≥ 0.1.1) as newer (DIA-47, choice a).
_PRE_RESET = {
    tuple(int(p) for p in v.split(".")) for v in ("0.1.0", "0.2.0", "0.2.1", "0.2.2", "0.2.3")
}
_POST_RESET_MIN = (0, 1, 1)


def parse(version: str) -> tuple[int, ...] | None:
    """``v0.2.1`` -> (0, 2, 1); None for anything that is not a plain release."""
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)", version.strip())
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def newer(candidate: str, current: str = dia.__version__) -> bool:
    a, b = parse(candidate), parse(current)
    if a is None or b is None or a == b:
        return False
    if a > b:
        return True
    return b in _PRE_RESET and a >= _POST_RESET_MIN


def editable() -> bool:
    """Installed from a checkout (``pip install -e``): that is updated with git."""
    try:
        text = metadata.distribution("dia").read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return True
    return bool(text and json.loads(text).get("dir_info", {}).get("editable"))


def system_package() -> bool:
    """Installed by the OS package manager (Arch PKGBUILD), not pip or a venv.

    Those installs must be updated with pacman (or the distro's tool), never
    ``pip install`` into ``/usr`` (DIA-06).
    """
    if editable() or sys.prefix != sys.base_prefix:
        return False
    try:
        root = Path(dia.__file__).resolve()
    except (TypeError, OSError):
        return False
    return root.parts[:2] == ("/", "usr")


def package_update_hint() -> str:
    """How to update a system-package install (shown instead of running pip)."""
    return "sudo pacman -Syu dia-assistant"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": f"dia/{dia.__version__}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        return response.read()


def latest() -> dict[str, Any] | None:
    """The newest release if it is newer than this one, else None."""
    data = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
    version = str(data.get("tag_name", "")).lstrip("v")
    if not newer(version):
        return None
    return {"version": version, "url": data.get("html_url", ""), "notes": data.get("body") or ""}


def checksum(sums: str, name: str) -> str:
    """The SHA-256 listed for ``name`` in a ``sha256sum`` file."""
    for line in sums.splitlines():
        digest, _, listed = line.strip().partition(" ")
        if listed.strip().lstrip("*") == name and re.fullmatch(r"[0-9a-f]{64}", digest):
            return digest
    raise ValueError(f"no checksum for {name}")


def install(version: str) -> None:
    """Install release ``version`` over this one, after verifying its wheel."""
    if editable():
        raise RuntimeError("Dia runs from a source checkout; update it with git")
    if system_package():
        raise RuntimeError(
            f"Dia was installed by the package manager; update with: {package_update_hint()}"
        )
    if parse(version) is None:
        raise ValueError(f"not a release version: {version}")
    base = f"https://github.com/{REPO}/releases/download/v{version}"
    name = f"dia-{version}-py3-none-any.whl"
    wheel = _get(f"{base}/{name}")
    expected = checksum(_get(f"{base}/SHA256SUMS").decode(), name)
    if hashlib.sha256(wheel).hexdigest() != expected:
        raise RuntimeError("the downloaded update does not match its checksum")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / name
        path.write_bytes(wheel)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", f"{path}[{EXTRAS}]"],
            capture_output=True,
            text=True,
            timeout=600,
        )
    if result.returncode:
        lines = result.stderr.strip().splitlines()
        raise RuntimeError(lines[-1] if lines else "pip failed")
