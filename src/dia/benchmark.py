"""How well each agent does on each project, from the task history, and what Dia
would change: "Codex gets nova's tasks done more often than Claude (9/10 vs
5/9); make it nova's default agent?"

Done is not the whole story: a merge that was later rolled back, a merge that
made the project's benchmark worse, or work that needed several review rounds
counts against the agent. ``quality`` is the share of tasks done and still
standing, less a little for every extra review round; proposals and automatic
routing use it.

Dia only proposes. Applying a proposal is your click (or `dia usage --apply`),
and it can only change which agent is the default for a project, never a
permission or a safety rule.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from dia.review import APPROVED

if TYPE_CHECKING:
    from dia.config import Config
    from dia.store import TaskStore

DONE = ("done", "merged", "published")
EDIT_MODES = ("edit",)


def agent_stats(store: TaskStore, days: int = 90) -> list[dict[str, Any]]:
    """Per (project, agent): tasks, success rate, tests passed, first-review approvals,
    merged, average minutes. The agent is whoever wrote the code (``author``)."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "tasks": 0,
            "done": 0,
            "tests_ok": 0,
            "tested": 0,
            "reviewed": 0,
            "approved": 0,
            "merged": 0,
            "seconds": 0.0,
            "reverted": 0,
            "regressions": 0,
            "discarded": 0,
            "rounds": 0,
        }
    )
    for task in store.recent(5000):
        if task.mode not in EDIT_MODES or task.status in ("planned", "queued", "running"):
            continue
        if task.details.get("mission") or datetime.fromisoformat(task.created_at) < since:
            continue  # mission steps are judged with their mission, not alone
        agent = task.details.get("author") or task.agent.split("+")[0]
        row = rows[(task.project, agent)]
        row["tasks"] += 1
        row["done"] += task.status in DONE
        row["merged"] += task.status == "merged"
        row["discarded"] += task.status == "discarded"
        row["reverted"] += bool(task.details.get("reverted_by"))
        row["regressions"] += bool(task.details.get("regression"))
        if task.tests_ok is not None:
            row["tested"] += 1
            row["tests_ok"] += bool(task.tests_ok)
        if reviews := task.details.get("reviews"):
            row["reviewed"] += 1
            row["approved"] += reviews[0].get("verdict") == APPROVED
            row["rounds"] += len(reviews)
        row["seconds"] += float(task.details.get("duration_s") or 0)
    result = []
    for (project, agent), row in sorted(rows.items()):
        n = row["tasks"]
        rounds = row["rounds"] / row["reviewed"] if row["reviewed"] else None
        standing = row["done"] - row["reverted"] - row["regressions"]
        quality = max(0.0, standing / n - 0.1 * max(0.0, (rounds or 1) - 1))
        result.append(
            {
                "project": project,
                "agent": agent,
                "tasks": n,
                "success": round(row["done"] / n, 2),
                "tests": round(row["tests_ok"] / row["tested"], 2) if row["tested"] else None,
                "approved": round(row["approved"] / row["reviewed"], 2)
                if row["reviewed"]
                else None,
                "merged": row["merged"],
                "minutes": round(row["seconds"] / n / 60, 1),
                "discarded": row["discarded"],
                "reverted": row["reverted"],
                "regressions": row["regressions"],
                "review_rounds": round(rounds, 1) if rounds is not None else None,
                "quality": round(quality, 2),
            }
        )
    return result


def score(row: dict[str, Any]) -> float:
    """Quality when known (rows from ``agent_stats``), else the plain success rate."""
    return row.get("quality", row["success"])


def rank(row: dict[str, Any]) -> tuple[float, float, float]:
    return score(row), row["success"], row.get("tests") or 0


def why(row: dict[str, Any]) -> str:
    text = f"{row['success']:.0%} of {row['tasks']} tasks done"
    flaws = [
        f"{row[key]} {label}"
        for key, label in (("reverted", "rolled back"), ("regressions", "made it slower"))
        if row.get(key)
    ]
    if row.get("review_rounds") and row["review_rounds"] > 1:
        flaws.append(f"{row['review_rounds']:g} review rounds on average")
    return text + (f" ({', '.join(flaws)})" if flaws else "")


def suggestions(
    config: Config, stats: list[dict[str, Any]], min_tasks: int = 5, margin: float = 0.2
) -> list[dict[str, Any]]:
    """Projects where another agent clearly does better than the current default."""
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stats:
        if row["tasks"] >= min_tasks and row["agent"] in config.agents:
            by_project[row["project"]].append(row)
    proposals = []
    for project, rows in by_project.items():
        if project not in config.projects or len(rows) < 2:
            continue
        current = config.projects[project].default_agent or config.default_agent
        best = max(rows, key=rank)
        now = next((r for r in rows if r["agent"] == current), None)
        if not now or best["agent"] == current or score(best) - score(now) < margin:
            continue
        proposals.append(
            {
                "project": project,
                "agent": best["agent"],
                "current": current,
                "reason": f"{best['agent']}: {why(best)}; {current}: {why(now)}",
            }
        )
    return proposals
