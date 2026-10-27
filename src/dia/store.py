"""Persistent task history (SQLite). The seed of Dia's long-term memory."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    agent       TEXT NOT NULL,
    mode        TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    status      TEXT NOT NULL,
    branch      TEXT,
    commit_sha  TEXT,
    tests_ok    INTEGER,
    summary     TEXT,
    error       TEXT,
    details     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS usage (
    at         TEXT NOT NULL,
    agent      TEXT NOT NULL,
    project    TEXT,
    task_id    TEXT,
    purpose    TEXT NOT NULL,
    duration_s REAL NOT NULL,
    success    INTEGER NOT NULL,
    limited    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_at ON usage (at);
CREATE TABLE IF NOT EXISTS audit (
    at     TEXT NOT NULL,
    actor  TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS audit_at ON audit (at);
CREATE TABLE IF NOT EXISTS benchmarks (
    at       TEXT NOT NULL,
    project  TEXT NOT NULL,
    sha      TEXT NOT NULL,
    ref      TEXT,
    task_id  TEXT,
    metrics  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS benchmarks_project ON benchmarks (project, at);
CREATE TABLE IF NOT EXISTS intents (
    at           TEXT NOT NULL,
    conversation TEXT,
    text         TEXT NOT NULL,
    action       TEXT NOT NULL,
    project      TEXT,
    skill        TEXT,
    brain        TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    at       TEXT NOT NULL,
    project  TEXT,
    task_id  TEXT,
    kind     TEXT NOT NULL,      -- merge | discard | rollback | review | plan
    outcome  TEXT NOT NULL,      -- merged, discarded, approved, rejected, ...
    title    TEXT NOT NULL,      -- what it was about (the task's request)
    reason   TEXT,               -- why, when someone said
    actor    TEXT,
    detail   TEXT                -- JSON: sha, agent, branch, files, ...
);
CREATE INDEX IF NOT EXISTS decisions_project ON decisions (project, at);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class TaskRecord:
    id: str
    project: str
    agent: str
    mode: str
    prompt: str
    # planned | queued | running | done | failed | merged | discarded | published
    status: str = "queued"
    branch: str | None = None
    commit_sha: str | None = None
    tests_ok: bool | None = None
    summary: str | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now)
    finished_at: str | None = None


class TaskStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        # Called with every saved task (e.g. to push live updates to the UI).
        self.listeners: list[Callable[[TaskRecord], None]] = []
        # Called with every audit entry (the UI's live activity feed).
        self.audit_listeners: list[Callable[[dict[str, Any]], None]] = []

    def save(self, task: TaskRecord) -> None:
        row = asdict(task)
        row["details"] = json.dumps(row["details"])
        cols = ", ".join(row)
        marks = ", ".join(f":{c}" for c in row)
        with self._db:
            self._db.execute(f"INSERT OR REPLACE INTO tasks ({cols}) VALUES ({marks})", row)
        for listener in list(self.listeners):
            listener(task)

    def get(self, task_id: str) -> TaskRecord | None:
        row = self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._from_row(row) if row else None

    def recent(self, limit: int = 20, project: str | None = None) -> list[TaskRecord]:
        query, args = "SELECT * FROM tasks", []
        if project:
            query, args = query + " WHERE project = ?", [project]
        rows = self._db.execute(query + " ORDER BY created_at DESC LIMIT ?", [*args, limit])
        return [self._from_row(r) for r in rows]

    def by_status(self, status: str) -> list[TaskRecord]:
        rows = self._db.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,)
        )
        return [self._from_row(r) for r in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TaskRecord:
        data = dict(row)
        data["details"] = json.loads(data["details"] or "{}")
        if data["tests_ok"] is not None:
            data["tests_ok"] = bool(data["tests_ok"])
        return TaskRecord(**data)

    def log_usage(
        self,
        agent: str,
        purpose: str,
        duration_s: float,
        success: bool,
        limited: bool,
        task: TaskRecord | None = None,
    ) -> None:
        """One agent call (a step, a review, a fix, learning...), for the usage panel."""
        with self._db:
            self._db.execute(
                "INSERT INTO usage VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now(),
                    agent,
                    task.project if task else None,
                    task.id if task else None,
                    purpose,
                    round(duration_s, 2),
                    int(success),
                    int(limited),
                ),
            )

    def usage_for(self, task_ids: list[str]) -> dict[str, float]:
        """Agent calls and minutes spent on these tasks (a mission's budget)."""
        if not task_ids:
            return {"calls": 0, "minutes": 0.0, "seconds": 0.0}
        marks = ",".join("?" * len(task_ids))
        calls, seconds = self._db.execute(
            f"SELECT COUNT(*), COALESCE(SUM(duration_s), 0) FROM usage WHERE task_id IN ({marks})",
            task_ids,
        ).fetchone()
        return {"calls": calls, "minutes": round(seconds / 60, 1), "seconds": float(seconds)}

    def usage(self, days: int = 30) -> dict[str, Any]:
        """Agent calls of the last ``days`` days: per agent, per day, per purpose."""
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
        q = self._db.execute
        agents = [
            {
                "agent": r[0],
                "calls": r[1],
                "ok": r[2],
                "minutes": round(r[3] / 60, 1),
                "limited": r[4],
            }
            for r in q(
                "SELECT agent, COUNT(*), SUM(success), SUM(duration_s), SUM(limited) FROM usage"
                " WHERE at >= ? GROUP BY agent ORDER BY COUNT(*) DESC",
                (since,),
            )
        ]
        daily = [
            {"day": r[0], "calls": r[1], "minutes": round(r[2] / 60, 1)}
            for r in q(
                "SELECT substr(at, 1, 10), COUNT(*), SUM(duration_s) FROM usage WHERE at >= ?"
                " GROUP BY substr(at, 1, 10) ORDER BY 1",
                (since,),
            )
        ]
        purposes = dict(
            q("SELECT purpose, COUNT(*) FROM usage WHERE at >= ? GROUP BY purpose", (since,))
        )
        tasks = [
            {"project": r[0], "tasks": r[1], "done": r[2], "failed": r[3]}
            for r in q(
                "SELECT project, COUNT(*), SUM(status IN ('done','merged','published')),"
                " SUM(status = 'failed') FROM tasks WHERE created_at >= ? AND mode != 'check'"
                " GROUP BY project ORDER BY COUNT(*) DESC",
                (since,),
            )
        ]
        return {
            "days": days,
            "agents": agents,
            "daily": daily,
            "purposes": purposes,
            "projects": tasks,
        }

    def log_benchmark(
        self,
        project: str,
        sha: str,
        metrics: dict[str, float],
        ref: str | None = None,
        task_id: str | None = None,
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO benchmarks VALUES (?, ?, ?, ?, ?, ?)",
                (now(), project, sha, ref, task_id, json.dumps(metrics)),
            )

    def benchmarks(
        self, project: str, ref: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Benchmark results of a project, newest first (only ``ref``'s when given)."""
        query = "SELECT * FROM benchmarks WHERE project = ?"
        args: list[Any] = [project]
        if ref is not None:
            query += " AND ref = ?"
            args.append(ref)
        rows = self._db.execute(query + " ORDER BY rowid DESC LIMIT ?", [*args, limit])
        return [{**dict(r), "metrics": json.loads(r["metrics"])} for r in rows]

    def log_intent(
        self,
        text: str,
        action: str,
        project: str | None = None,
        skill: str | None = None,
        brain: str | None = None,
        conversation: str | None = None,
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO intents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now(), conversation, text[:2000], action, project, skill, brain),
            )

    def log_decision(
        self,
        kind: str,
        outcome: str,
        title: str,
        project: str | None = None,
        task_id: str | None = None,
        reason: str | None = None,
        actor: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now(),
                    project,
                    task_id,
                    kind,
                    outcome,
                    title[:500],
                    (reason or "").strip()[:2000] or None,
                    actor,
                    json.dumps(detail or {}),
                ),
            )

    def decisions(
        self, project: str | None = None, task_id: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        """Decisions newest first, optionally of one project or one task."""
        query, args = "SELECT * FROM decisions WHERE 1", []
        if project:
            query, args = query + " AND project = ?", [*args, project]
        if task_id:
            query, args = query + " AND task_id = ?", [*args, task_id]
        rows = self._db.execute(query + " ORDER BY rowid DESC LIMIT ?", [*args, limit])
        return [{**dict(r), "detail": json.loads(r["detail"] or "{}")} for r in rows]

    def intents(self, limit: int = 100) -> list[dict[str, Any]]:
        """What people asked and how it was understood, newest first."""
        rows = self._db.execute("SELECT * FROM intents ORDER BY rowid DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def log_audit(self, actor: str, action: str, target: str | None, detail: str = "") -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO audit VALUES (?, ?, ?, ?, ?)",
                (now(), actor, action, target, detail[:1000]),
            )
        for listener in list(self.audit_listeners):
            listener(
                {
                    "at": now(),
                    "actor": actor,
                    "action": action,
                    "target": target,
                    "detail": detail[:1000],
                }
            )

    def audit(
        self, limit: int = 100, action: str | None = None, target: str | None = None
    ) -> list[dict[str, Any]]:
        query, args = "SELECT at, actor, action, target, detail FROM audit WHERE 1", []
        if action:
            query, args = query + " AND action LIKE ?", [*args, action + "%"]
        if target:
            query, args = query + " AND target = ?", [*args, target]
        rows = self._db.execute(query + " ORDER BY rowid DESC LIMIT ?", [*args, limit])
        keys = ("at", "actor", "action", "target", "detail")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def close(self) -> None:
        self._db.close()
