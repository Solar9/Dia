"""Small types shared by the orchestrator and its collaborators."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dia.core.store import TaskRecord


@dataclass
class Event:
    kind: str  # "ci", "review", "voice" (state: listening/processing/speaking/idle)
    task: TaskRecord | None
    message: str
    data: dict[str, Any] = field(default_factory=dict)  # kind-specific extras


class TaskActionError(Exception):
    """A merge/discard/diff request that cannot be carried out; the message says why."""


@dataclass
class TaskReport:
    task: TaskRecord
    diff_stat: str = ""
    test_output: str = ""
    warnings: list[str] = field(default_factory=list)


def new_task_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
