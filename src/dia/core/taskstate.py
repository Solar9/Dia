"""What a task means for the person: working, or waiting for their decision.

One definition for every interface (web UI, tray, Plasma widget, phone): the API sends
``decision`` on each task and ``counts`` in the status, clients do not count on their own.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

RUNNING = ("queued", "running", "waiting")


class _Task(Protocol):
    status: str
    commit_sha: str | None
    details: dict[str, Any]


def decision_of(task: _Task) -> str | None:
    """Why the task needs the owner: ``merge`` (changes to merge or discard), ``plan``
    (a plan to approve), ``ci`` (published work whose CI failed) or ``comments``
    (review comments to address); None when nothing is asked of them."""
    details = task.details or {}
    if task.status == "done" and task.commit_sha:
        return "merge"
    if task.status == "planned":
        return "plan"
    if task.status == "published" and (details.get("ci") or {}).get("state") == "failed":
        return "ci"
    if task.status == "published" and details.get("comments_pending"):
        return "comments"
    return None


def counts(tasks: Iterable[_Task]) -> dict[str, int]:
    """``running``: queued, running or waiting for a limit; ``waiting_for_you``: a decision."""
    listed = list(tasks)
    return {
        "running": sum(1 for t in listed if t.status in RUNNING),
        "waiting_for_you": sum(1 for t in listed if decision_of(t)),
    }
