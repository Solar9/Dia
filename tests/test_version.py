"""Every place that carries Dia's version must match pyproject.toml (DIA-09)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_version_places_match_pyproject() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/bump-version"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
