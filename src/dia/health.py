"""Self-check: Dia keeps itself running and says what it cannot fix.

**In ``dia serve``** every channel and watcher runs supervised: one that
crashes (Discord dropped, the microphone vanished) is restarted with a
growing pause (5 s up to 5 min) instead of taking all of Dia down, and the
UI shows what is restarting and why (``GET /api/health``). Tasks marked
running from before a restart are recorded as interrupted.

**``dia doctor --fix``** repairs what is safe to repair and reports the
rest:

- worktrees left behind by finished, discarded or vanished tasks (and stale
  benchmark copies) are removed, ``git worktree prune`` runs per project;
- a broken memory index is moved aside and rebuilt;
- Dia's data directory and secrets file get their private permissions back.

Everything it does is in the audit log.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sqlite3
import stat
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from dia.store import now
from dia.workspace import run

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.health")


def state(dia: Orchestrator) -> dict[str, dict[str, Any]]:
    if getattr(dia, "_health", None) is None:
        dia._health = {}
    return dia._health


async def supervise(
    dia: Orchestrator,
    name: str,
    start: Callable[[], Awaitable[Any]],
    first_pause: float = 5,
    max_pause: float = 300,
) -> None:
    """Run ``start()`` and run it again whenever it crashes, pausing longer each time."""
    health = state(dia)
    pause = first_pause
    restarts = 0
    while True:
        health[name] = {"state": "running", "since": now(), "restarts": restarts}
        try:
            await start()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            restarts += 1
            log.exception("%s crashed; restarting in %.0f s", name, pause)
            health[name] = {
                "state": "restarting",
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "restarts": restarts,
                "at": now(),
            }
            dia.audit("health.restart", name, health[name]["error"])
            if restarts in (1, 5, 20):  # once, then only when it keeps happening
                await dia.emit("system", None, f"{name} crashed and is restarting: {exc}")
            await asyncio.sleep(pause)
            pause = min(max_pause, pause * 2)
            continue
        health[name] = {"state": "finished", "at": now(), "restarts": restarts}
        return


def interrupted(dia: Orchestrator) -> list[str]:
    """Tasks still marked running or queued when Dia starts: none can be running."""
    found = []
    for task in dia.store.recent(500):
        if task.status in ("running", "queued") and task.mode not in ("goal",):
            task.status, task.error, task.finished_at = "failed", "interrupted by a restart", now()
            dia.store.save(task)
            found.append(task.id)
    if found:
        dia.audit("health.interrupted", None, ", ".join(found))
    return found


# ---------------------------------------------------------------- repairs ---


async def _worktrees(dia: Orchestrator, notes: list[str]) -> None:
    root = dia.config.data_dir / "worktrees"
    for project in dia.config.projects.values():
        if (project.path / ".git").exists():
            await run(["git", "worktree", "prune"], project.path)
        folder = root / project.name
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            task = dia.store.get(path.name)
            stale = path.name.startswith(("bench-", "mission-plan-")) or not task
            stale = stale or (task is not None and task.status in ("merged", "discarded"))
            if not stale:
                continue
            await run(["git", "worktree", "remove", "--force", str(path)], project.path)
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
            notes.append(f"removed leftover worktree {project.name}/{path.name}")
        if (project.path / ".git").exists():
            await run(["git", "worktree", "prune"], project.path)


def _index(dia: Orchestrator, notes: list[str], problems: list[str]) -> None:
    memory = dia.memory
    index = memory.semantic_index() if memory and hasattr(memory, "semantic_index") else None
    if not index:
        return
    try:
        ok = index.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        index.db.execute("SELECT COUNT(*) FROM chunks").fetchone()
    except sqlite3.DatabaseError:
        ok = False
    if ok:
        return
    path = index.db_path
    try:
        index.db.close()
    except Exception:
        pass
    path.replace(path.with_suffix(".broken"))
    memory._index = None
    try:
        count = memory.semantic_index().update()
        notes.append(f"memory index was broken: rebuilt ({count} notes; old one kept as .broken)")
    except Exception as exc:
        problems.append(f"memory index was broken and could not be rebuilt: {exc}")


def _permissions(dia: Orchestrator, notes: list[str]) -> None:
    from dia.service import env_path

    targets = [(dia.config.data_dir, 0o700)]
    if (secrets := env_path()).exists():
        targets.append((secrets, 0o600))
    for path, mode in targets:
        try:
            current = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            continue
        if current & 0o077:
            os.chmod(path, mode)
            notes.append(f"{path}: permissions {oct(current)} → {oct(mode)}")


async def fix(dia: Orchestrator) -> tuple[list[str], list[str]]:
    """Repair what is safe; returns (what was done, what could not be fixed)."""
    notes: list[str] = []
    problems: list[str] = []
    try:
        await _worktrees(dia, notes)
    except Exception as exc:
        problems.append(f"worktrees: {type(exc).__name__}: {exc}")
    for name, repair in (("memory index", _index), ("permissions", _permissions)):
        try:
            repair(dia, notes, problems) if repair is _index else repair(dia, notes)
        except Exception as exc:
            problems.append(f"{name}: {type(exc).__name__}: {exc}")
    stuck = [t.id for t in dia.store.recent(500) if t.status in ("running", "queued")]
    if stuck:
        problems.append(
            f"{len(stuck)} task(s) marked running ({', '.join(stuck[:3])}): if Dia is not "
            "running, `dia serve` records them as interrupted when it starts"
        )
    for line in notes:
        dia.audit("health.fix", None, line)
    return notes, problems
