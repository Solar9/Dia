"""Is Dia getting better? The same numbers every week, from its own history.

Per week (Monday to Sunday): how many coding tasks, the share finished, how
many were discarded or rolled back after a merge, how often a retry rescued a
task that failed at first, review rounds per reviewed task, minutes per task,
sandbox incidents and benchmark regressions. ``dia scorecard`` prints it, the
Usage view shows it; the last column against the ones before is the answer.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dia.store import TaskStore

DONE = ("done", "merged", "published")
CODING = ("edit",)


def _week(at: str) -> date:
    day = datetime.fromisoformat(at).astimezone(UTC).date()
    return day - timedelta(days=day.weekday())


def scorecard(store: TaskStore, weeks: int = 8) -> list[dict[str, Any]]:
    """One row per week, oldest first; empty weeks are kept (zeros, no rates)."""
    this_week = _week(datetime.now(UTC).isoformat())
    starts = [this_week - timedelta(weeks=i) for i in reversed(range(weeks))]
    raw: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for task in store.recent(20000):
        week = _week(task.created_at)
        if week < starts[0]:
            break  # newest first: everything after this is older
        if task.status in ("planned", "queued", "running"):
            continue
        row = raw[week]
        row["incidents"] += len(task.details.get("incidents", []))
        if task.mode not in CODING or task.details.get("reverts"):
            continue  # a rollback is Dia undoing a merge, not a task of its own
        row["tasks"] += 1
        row["done"] += task.status in DONE
        row["discarded"] += task.status == "discarded"
        row["reverted"] += bool(task.details.get("reverted_by"))
        if task.details.get("retries"):
            row["retried"] += 1
            row["rescued"] += task.status in DONE
        if reviews := task.details.get("reviews"):
            row["reviewed"] += 1
            row["rounds"] += len(reviews)
        row["seconds"] += float(task.details.get("duration_s") or 0)
    for entry in store.audit(limit=5000, action="benchmark.regression"):
        week = _week(entry["at"])
        if week >= starts[0]:
            raw[week]["regressions"] += 1

    def rate(a: str, b: str, digits: int = 2) -> float | None:
        return round(r[a] / r[b], digits) if r.get(b) else None

    result = []
    for start in starts:
        r = raw.get(start, {})
        n = int(r.get("tasks", 0))
        result.append(
            {
                "week": start.isoformat(),
                "tasks": n,
                "success": round(r["done"] / n, 2) if n else None,
                "discarded": int(r.get("discarded", 0)),
                "rolled_back": int(r.get("reverted", 0)),
                "retry_rescue": round(r["rescued"] / r["retried"], 2) if r.get("retried") else None,
                "review_rounds": round(r["rounds"] / r["reviewed"], 1)
                if r.get("reviewed")
                else None,
                "minutes_per_task": round(r["seconds"] / n / 60, 1) if n else None,
                "incidents": int(r.get("incidents", 0)),
                "regressions": int(r.get("regressions", 0)),
            }
        )
    return result


COLUMNS = (
    ("week", "week"),
    ("tasks", "tasks"),
    ("success", "done"),
    ("discarded", "discarded"),
    ("rolled_back", "rolled back"),
    ("retry_rescue", "retry rescue"),
    ("review_rounds", "review rounds"),
    ("minutes_per_task", "min/task"),
    ("incidents", "incidents"),
    ("regressions", "regressions"),
)


def format_table(rows: list[dict[str, Any]]) -> str:
    def cell(key: str, value: Any) -> str:
        if value is None:
            return "-"
        if key in ("success", "retry_rescue"):
            return f"{value:.0%}"
        return f"{value:g}" if isinstance(value, float) else str(value)

    table = [[label for _, label in COLUMNS]]
    table += [[cell(key, row[key]) for key, _ in COLUMNS] for row in rows]
    widths = [max(len(line[i]) for line in table) for i in range(len(COLUMNS))]
    return "\n".join(
        "  ".join(c.ljust(w) for c, w in zip(line, widths, strict=True)) for line in table
    )
