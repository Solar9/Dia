"""Channels: the ways a person talks to Dia (Discord, voice, ...).

A channel turns messages into calls on the :class:`~dia.orchestrator.Orchestrator`
and reports back. All logic that is not about the medium itself belongs in
the core, so every channel gets it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator


class Channel(ABC):
    kind: ClassVar[str]

    def __init__(self, name: str, options: dict[str, Any], dia: Orchestrator) -> None:
        self.name = name
        self.options = dict(options)
        self.dia = dia

    @abstractmethod
    async def run(self) -> None:
        """Serve until cancelled."""

    def check(self) -> str | None:
        """Return a problem description if the channel cannot start, else ``None``."""
        return None
