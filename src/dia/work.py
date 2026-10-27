"""Work profiles: "Zaczynam pracę nad Starfall" and "Kończę na dziś".

Starting work on a profile opens its apps (your own commands, detached),
and tells you where you are: the last tasks on the project, what waits for
your review, the goal and its latest review, and what you left yourself
last time. Stopping saves the session: what was done and merged, what
still waits, uncommitted files, the last things you talked about, and a
note if you say one ("zapisz, że skończyłem na dashu"). Next start shows it.

    [profiles.starfall]
    project = "uv"
    apps = ["godot4 --editor --path ~/games/uv", "code ~/games/uv"]
    names = ["starfall", "uv", "ultra"]     # how you call it (default: its name)

A project without a profile works too, just without apps. Only the
commands you configured are started; nothing about what you do in them is
recorded.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.store import now

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.work")


def profiles(dia: Orchestrator) -> dict[str, dict[str, Any]]:
    found = {name: dict(p) for name, p in dia.config.section("profiles").items()}
    for name, project in dia.config.projects.items():  # every project is a profile too
        if not any(p.get("project") == name for p in found.values()):
            found.setdefault(name, {"project": project.name})
    return found


def find(dia: Orchestrator, name: str | None) -> tuple[str, dict[str, Any]]:
    """A profile by its name, one of its names, or its project's name."""
    found = profiles(dia)
    if not name:
        current = _state(dia).get("current")
        if current in found:
            return current, found[current]
        raise ValueError("which profile? (dia work list)")
    wanted = name.strip().lower()
    for key, profile in found.items():
        names = {key.lower(), str(profile.get("project", "")).lower()}
        names |= {str(n).lower() for n in profile.get("names", [])}
        if wanted in names:
            return key, profile
    raise ValueError(f"no profile or project '{name}' (known: {', '.join(found)})")


def _dir(dia: Orchestrator) -> Path:
    return dia.config.data_dir / "sessions"


def _state(dia: Orchestrator) -> dict[str, Any]:
    try:
        return json.loads((_dir(dia) / "state.json").read_text())
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))


def _session(dia: Orchestrator, name: str) -> dict[str, Any]:
    try:
        return json.loads((_dir(dia) / f"{name}.json").read_text())
    except (OSError, ValueError):
        return {}


def launch_apps(apps: list[str]) -> list[str]:
    started = []
    for command in apps:
        argv = [os.path.expanduser(a) for a in shlex.split(command)]
        try:
            subprocess.Popen(  # detached: the app stays when Dia moves on
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            started.append(argv[0])
        except OSError as exc:
            log.warning("could not start %s: %s", command, exc)
    return started


def _waiting(dia: Orchestrator, project: str) -> list[str]:
    return [
        f"{t.id}: {t.prompt.splitlines()[0][:70]}"
        for t in dia.store.recent(50, project)
        if t.status == "done" and t.commit_sha and t.mode == "edit"
    ]


async def start(dia: Orchestrator, name: str, open_apps: bool = True) -> str:
    from dia import goals

    key, profile = find(dia, name)
    project = profile.get("project")
    started = launch_apps(list(profile.get("apps", []))) if open_apps else []
    _write(_dir(dia) / "state.json", {"current": key, "started": now()})
    dia.audit("work.start", key, ", ".join(started))
    previous = _session(dia, key).get("last") or {}
    lines = [f"Work on {key}" + (f" ({project})" if project else "") + "."]
    if started:
        lines.append("Opened: " + ", ".join(started))
    if previous:
        day = previous.get("at", "")[:10]
        lines.append(f"Last time ({day}): {previous.get('text', '')}")
    if project:
        recent = dia.store.recent(5, project)
        if recent:
            lines.append("Last tasks:")
            lines += [f"  [{t.status}] {t.prompt.splitlines()[0][:70]}" for t in recent]
        if waiting := _waiting(dia, project):
            lines.append(f"Waiting for your review ({len(waiting)}): " + "; ".join(waiting[:3]))
        for goal in goals.goals(dia):
            if goal.project == project:
                review = (goal.details.get("reviews") or [{}])[-1]
                lines.append(f"Goal: {goal.prompt}" + (
                    f" ({review.get('progress', '')})" if review else ""))  # fmt: skip
    return "\n".join(lines)


async def stop(dia: Orchestrator, name: str | None = None, note: str = "") -> str:
    from dia.workspace import uncommitted_files

    key, profile = find(dia, name)
    state = _state(dia)
    since = state.get("started") if state.get("current") == key else None
    project = profile.get("project")
    parts = []
    if note.strip():
        parts.append(note.strip())
    if project:
        tasks = [t for t in dia.store.recent(200, project) if not since or t.created_at >= since]
        merged = [t for t in tasks if t.status == "merged"]
        if tasks:
            parts.append(f"{len(tasks)} task(s) this session, {len(merged)} merged")
        if waiting := _waiting(dia, project):
            parts.append("waiting for review: " + "; ".join(waiting[:3]))
        try:
            dirty = await uncommitted_files(dia.config.project(project).path)
        except Exception:
            dirty = []
        if dirty:
            more = " ..." if len(dirty) > 5 else ""
            parts.append(f"uncommitted: {', '.join(dirty[:5])}{more}")
    turns = dia.conversations.history("owner")[-3:]
    if turns:
        parts.append("we talked about: " + "; ".join(t[0][:60] for t in turns))
    text = ". ".join(parts) or "nothing recorded"
    session = _session(dia, key)
    session["last"] = {"at": now(), "started": since, "text": text, "note": note.strip()}
    _write(_dir(dia) / f"{key}.json", session)
    _write(_dir(dia) / "state.json", {})
    dia.audit("work.stop", key, text[:200])
    took = ""
    if since:
        began = datetime.fromisoformat(since)
        took = f" after {int((datetime.now(began.tzinfo) - began).total_seconds() // 60)} min"
    return f"Saved the session on {key}{took}: {text}"
