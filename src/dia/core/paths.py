"""Where Dia keeps per-user files outside the data directory."""

from __future__ import annotations

import os
from pathlib import Path


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def env_path() -> Path:
    """Dia's secrets file (read by the service and by ``dia secret``)."""
    return config_home() / "dia" / "env"
