"""The emergency stop's reach: every agent process (and test run) Dia starts is
registered here in its own process group, so one call ends them all, children
included (agents start their own tools and shells)."""

from __future__ import annotations

import asyncio
import os
import signal

_RUNNING: dict[int, str] = {}  # pid -> what it is
_STOPPED: set[int] = set()


def track(pid: int, label: str) -> None:
    _RUNNING[pid] = label


def untrack(pid: int) -> None:
    _RUNNING.pop(pid, None)


def was_stopped(pid: int) -> bool:
    """True if the emergency stop ended this process (then forget it)."""
    if pid in _STOPPED:
        _STOPPED.discard(pid)
        return True
    return False


def running() -> dict[int, str]:
    return dict(_RUNNING)


def _signal(pid: int, sig: signal.Signals) -> None:
    try:
        os.killpg(pid, sig)  # pid == pgid: started with start_new_session
    except (ProcessLookupError, PermissionError):
        pass


def _kill_remaining(pids: list[int]) -> None:
    for pid in pids:
        if pid in _RUNNING:
            _signal(pid, signal.SIGKILL)


def stop_all(grace: float = 5.0) -> list[str]:
    """SIGTERM every registered process group, SIGKILL whatever is left after ``grace``."""
    stopped = []
    for pid, label in list(_RUNNING.items()):
        _STOPPED.add(pid)
        _signal(pid, signal.SIGTERM)
        stopped.append(label)
    pids = list(_RUNNING)
    if pids:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop:
            loop.call_later(
                grace, lambda: [_signal(p, signal.SIGKILL) for p in pids if p in _RUNNING]
            )
    return stopped
