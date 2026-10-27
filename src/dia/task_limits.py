"""Limits for one task: how much agent time and how many agent calls it may
use, how long one call may run, and how much CPU agents and tests may take.

    [task_limits]
    minutes = 60          # agent minutes per task, all its calls together (0: none)
    calls = 12            # agent calls per task: retries, reviews, fixes included
    agent_timeout = 1800  # seconds per agent call (an agent's own timeout wins)
    nice = 10             # CPU priority of agents and tests: 0 normal .. 19 lowest

    [projects.nova]
    task_limits = { minutes = 120 }

All are off by default. A task that reaches its limit stops asking agents and
is reported as failed with the reason; nothing it already did is lost (its
branch stays for review). Missions also have their own budget.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dia.config import Config, ProjectConfig
    from dia.store import TaskRecord, TaskStore


@dataclass(frozen=True)
class TaskLimits:
    minutes: float = 0
    calls: int = 0
    agent_timeout: float = 0
    nice: int = 0

    @classmethod
    def for_project(cls, config: Config, project: ProjectConfig | None) -> TaskLimits:
        options = dict(config.section("task_limits"))
        if project is not None:
            options.update(project.options.get("task_limits") or {})
        return cls(
            minutes=max(0.0, float(options.get("minutes", 0))),
            calls=max(0, int(options.get("calls", 0))),
            agent_timeout=max(0.0, float(options.get("agent_timeout", 0))),
            nice=min(19, max(0, int(options.get("nice", 0)))),
        )

    def exceeded(self, store: TaskStore, task: TaskRecord) -> str | None:
        """Why the task may not call another agent, or None."""
        if not (self.minutes or self.calls):
            return None
        used = store.usage_for([task.id])
        if self.calls and used["calls"] >= self.calls:
            return f"task limit reached: {used['calls']} of {self.calls} agent calls"
        if self.minutes and used["seconds"] >= self.minutes * 60:
            return f"task limit reached: {used['minutes']:g} of {self.minutes:g} agent minutes"
        return None

    def timeout(self, store: TaskStore, task: TaskRecord | None, own: float | None) -> float | None:
        """The timeout for the next call: the agent's own, the default, and what is
        left of the task's minutes, whichever is shortest."""
        candidates = [t for t in (own, self.agent_timeout) if t]
        if task is not None and self.minutes:
            left = self.minutes * 60 - store.usage_for([task.id])["seconds"]
            candidates.append(max(left, 0.1))  # exactly what is left, never more
        return min(candidates) if candidates else None

    def wrap(self, argv: list[str]) -> list[str]:
        """``argv`` run at a lower CPU priority when ``nice`` is set."""
        if self.nice and shutil.which("nice"):
            return ["nice", "-n", str(self.nice), *argv]
        return argv
