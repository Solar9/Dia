"""Who did what: every action that changes something is written to the audit
log (``audit`` table in the task database), with the actor that asked for it.

Channels set the actor for the work they start (``with acting_as("discord:ann")``);
anything they spawn inherits it, so a merge clicked on the phone is logged as
that device even though the orchestrator does the work.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

ACTOR: ContextVar[str] = ContextVar("dia_actor", default="cli")


def actor() -> str:
    return ACTOR.get()


@contextmanager
def acting_as(name: str) -> Iterator[None]:
    token = ACTOR.set(name)
    try:
        yield
    finally:
        ACTOR.reset(token)
