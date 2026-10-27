"""Discreet suggestions, from Dia's own history only.

What Dia looks at: its tasks, its decision log, the debt register, goals,
and the projects' git history. Nothing about what you do on the computer.
From that, a few patterns are worth a word:

- **trouble in one area**: several rollbacks, benchmark regressions or
  failed tasks this week touching the same folder ("3 regressions in
  combat/ this week: analyse them?");
- **tests that keep failing** in a project;
- **hot debt**: a file you keep changing that is also high in the debt
  register;
- **work waiting**: finished tasks waiting for your review for days, a
  goal review waiting for approval.

At most ``per_day`` suggestions a day (default 1), the same one not again
for ``repeat_days`` (default 14), dismissed ones never again. They go out
like other notifications, so quiet hours and the notification budget hold
them back. Accepting one runs what it proposes (an analysis, a debt task);
it never merges or publishes anything.

    [suggestions]
    enabled = true
    per_day = 1
    repeat_days = 14
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from dia.store import now

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.suggestions")


def _since(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


def _area(path: str) -> str:
    parts = PurePosixPath(path).parts
    return f"{parts[0]}/" if len(parts) > 1 else path


def find(dia: Orchestrator) -> list[dict[str, Any]]:
    """Every suggestion the history supports right now (not yet filtered)."""
    found: list[dict[str, Any]] = []
    week = _since(7)
    # Trouble in one area: rollbacks, regressions, failures by folder.
    trouble: dict[tuple[str, str], list[str]] = defaultdict(list)
    for d in dia.store.decisions(limit=2000):
        if d["at"] < week or d["kind"] != "merge":
            continue
        task = dia.store.get(d["task_id"]) if d["task_id"] else None
        if task and (task.details.get("reverted_by") or task.details.get("regression")):
            for area in {_area(f) for f in d["detail"].get("files", [])}:
                trouble[(task.project, area)].append(task.id)
    for (project, area), tasks in trouble.items():
        if len(tasks) >= 2:
            found.append({
                "key": f"trouble:{project}:{area}",
                "text": f"{len(tasks)} rollbacks or regressions in {project}/{area} this week: "
                "analyse what they have in common?",
                "action": {"kind": "ask", "project": project,
                           "prompt": f"Several recent changes in {area} were rolled back or made "
                           f"benchmarks worse (tasks {', '.join(tasks)}). Find what they have in "
                           "common and what would prevent it. Change no files."},
            })  # fmt: skip
    # Tests that keep failing.
    failing: dict[str, int] = defaultdict(int)
    for t in dia.store.recent(500):
        if t.created_at >= week and t.mode == "edit" and t.tests_ok is False:
            failing[t.project] += 1
    for project, n in failing.items():
        if n >= 3:
            found.append({
                "key": f"failing:{project}",
                "text": f"Tests failed in {n} tasks on {project} this week: look for flaky or "
                "broken tests?",
                "action": {"kind": "ask", "project": project,
                           "prompt": "Tests failed in several recent tasks. Run the test suite, "
                           "find tests that fail regardless of the change (flaky or already "
                           "broken) and say why. Change no files."},
            })  # fmt: skip
    # Hot debt.
    from dia.debt import saved

    for project in dia.config.projects:
        for item in saved(dia, project)[:3]:
            if item.get("changes", 0) >= 5 and item["kind"] != "vulnerable dependency":
                found.append({
                    "key": f"debt:{project}:{item['file']}:{item['kind']}",
                    "text": f"{item['file']} changed {item['changes']}x lately and has "
                    f"{item['kind']} ({item['detail']}): pay it off?",
                    "action": {"kind": "debt", "project": project, "n": item["n"]},
                })  # fmt: skip
                break
    # Work waiting for you.
    old = _since(3)
    waiting = [
        t for t in dia.store.recent(300)
        if t.status == "done" and t.commit_sha and t.mode == "edit" and t.created_at < old
    ]  # fmt: skip
    if waiting:
        found.append({
            "key": f"waiting:{len(waiting)}",
            "text": f"{len(waiting)} finished task(s) have waited 3+ days for your review "
            f"(e.g. {waiting[0].prompt.splitlines()[0][:50]}): review or discard them?",
            "action": None,
        })  # fmt: skip
    from dia.goals import goals

    for goal in goals(dia):
        reviews = goal.details.get("reviews") or []
        if reviews and reviews[-1]["status"] == "proposed" and reviews[-1]["at"] < _since(2):
            found.append({
                "key": f"goal:{goal.id}:{reviews[-1]['at'][:10]}",
                "text": f"The review of '{goal.prompt[:50]}' waits for your approval "
                f"(next: {(reviews[-1].get('next') or {}).get('mission', '-')[:60]}).",
                "action": None,
            })  # fmt: skip
    return found


def _local_day(at: str) -> date | None:
    """The local calendar day of a stored (UTC) timestamp."""
    try:
        return datetime.fromisoformat(at).astimezone().date()
    except ValueError:
        return None


class Suggestions:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self.path = dia.config.data_dir / "suggestions.json"
        self.options = dia.config.section("suggestions")

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False))

    def open(self) -> list[dict[str, Any]]:
        return [s for s in self._load().get("open", []) if s.get("status") == "open"]

    async def check(self) -> list[dict[str, Any]]:
        """New suggestions to make now, within the daily limit; they are emitted."""
        if self.options.get("enabled", True) is False:
            return []
        data = self._load()
        today = datetime.now().astimezone().date()
        made_today = sum(1 for s in data.get("open", []) if _local_day(s.get("at", "")) == today)
        room = int(self.options.get("per_day", 1)) - made_today
        if room <= 0:
            return []
        repeat = _since(int(self.options.get("repeat_days", 14)))
        seen = data.get("seen", {})
        dismissed = set(data.get("dismissed", []))
        fresh = [
            s for s in find(self.dia)
            if s["key"] not in dismissed and seen.get(s["key"], "") < repeat
        ][:room]  # fmt: skip
        for s in fresh:
            s.update(at=now(), status="open")
            seen[s["key"]] = s["at"]
            data.setdefault("open", []).append(s)
            await self.dia.emit("suggestion", None, s["text"], {"key": s["key"]})
        data["open"] = data.get("open", [])[-50:]
        data["seen"] = seen
        self._save(data)
        return fresh

    def _take(self, key: str, status: str) -> dict[str, Any]:
        data = self._load()
        for s in data.get("open", []):
            if s["key"] == key and s.get("status") == "open":
                s["status"] = status
                if status == "dismissed":
                    data.setdefault("dismissed", []).append(key)
                self._save(data)
                self.dia.audit(f"suggestion.{status}", key, s["text"][:200])
                return s
        raise ValueError(f"no open suggestion {key}")

    def dismiss(self, key: str) -> None:
        self._take(key, "dismissed")

    async def accept(self, key: str, on_start: Any = None) -> Any:
        """Do what the suggestion proposes; returns the task report (or None)."""
        from dia.agents import Mode

        suggestion = self._take(key, "accepted")
        action = suggestion.get("action")
        if not action:
            return None
        if action["kind"] == "debt":
            from dia.debt import fix

            return await fix(self.dia, action["project"], action["n"], on_start)
        return await self.dia.run_task(
            action["project"], action["prompt"], mode=Mode.READ_ONLY, on_start=on_start
        )


class SuggestionWatcher:
    """Looks for something worth suggesting every few hours in `dia serve`."""

    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    async def run(self) -> None:
        while True:
            await asyncio.sleep(1800)  # not right at start-up
            try:
                await Suggestions(self.dia).check()
            except Exception:
                log.exception("suggestions failed")
            await asyncio.sleep(6 * 3600)
