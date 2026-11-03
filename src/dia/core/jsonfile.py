"""Reading and writing the small JSON state files Dia keeps in its data directory.

Writes go to a temporary file in the same directory and are moved into place
with :func:`os.replace`, so a crash or a second Dia process never sees (or
leaves) a half-written file. An existing file keeps its permission bits; new
files get ``mode`` (default: the usual umask-based mode).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    """The JSON in ``path``; ``default`` when the file is missing, unreadable or invalid."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write_json(
    path: Path,
    data: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = True,
    newline: bool = False,
    mode: int | None = None,
) -> None:
    """Write ``data`` as JSON to ``path`` atomically (parent directories are created)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii) + ("\n" if newline else "")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(text)
        if mode is not None:
            temporary.chmod(mode)
        else:
            try:
                temporary.chmod(path.stat().st_mode & 0o7777)
            except FileNotFoundError:
                pass
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
