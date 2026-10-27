"""Optional long-term memory: what agents should know, and a record of what they did.

Memory is an add-on. Without a ``[memory]`` section in the config Dia works
the same, just without extra context. A memory backend must never be able to
fail a task: the orchestrator turns its errors into warnings.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from dia.config import ProjectConfig
    from dia.memory.search import Hit
    from dia.orchestrator import TaskReport


class Memory(ABC):
    kind: ClassVar[str]

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options: dict[str, Any] = dict(options or {})

    @abstractmethod
    def context_for(self, project: ProjectConfig, task: str) -> str:
        """Knowledge to hand to an agent doing ``task`` on ``project`` ('' if none)."""

    def search(self, query: str, limit: int = 5) -> list[Hit]:
        """Notes relevant to ``query``. Backends without search return nothing."""
        return []

    @abstractmethod
    def record(self, project: ProjectConfig, report: TaskReport) -> None:
        """Remember a finished task."""

    def remember(self, project: ProjectConfig, facts: list[str]) -> None:
        """Keep ``facts`` (accepted by a person) where future tasks will read them."""
        raise NotImplementedError(f"memory '{self.kind}' cannot store facts")

    def howtos(self) -> list[dict[str, Any]]:
        """Procedures the agents follow when they apply (title, when, projects, steps)."""
        return []

    def save_howto(
        self, title: str, when: str, steps: str, projects: list[str] | None = None
    ) -> str:
        """Keep a how-to (accepted by a person); returns where it was stored."""
        raise NotImplementedError(f"memory '{self.kind}' cannot store how-tos")

    def notes(self) -> list[dict[str, Any]]:
        """The notes Dia keeps (for browsing them in the UI); backends may have none."""
        return []

    def read_note(self, path: str) -> str:
        raise NotImplementedError(f"memory '{self.kind}' has no notes to read")

    def write_note(self, path: str, text: str) -> None:
        raise NotImplementedError(f"memory '{self.kind}' has no notes to write")

    def check(self) -> str | None:
        """Return a problem description if the backend is unusable, else ``None``."""
        return None

    def describe(self) -> str:
        return self.kind
