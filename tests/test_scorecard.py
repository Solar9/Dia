from datetime import UTC, datetime, timedelta
from pathlib import Path

from dia.scorecard import format_table, scorecard
from dia.store import TaskRecord, TaskStore


def task(n: int, status: str, days_ago: int = 0, **details) -> TaskRecord:
    at = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    return TaskRecord(
        id=f"t{n}", project="nova", agent="a", mode="edit", prompt="x",
        status=status, created_at=at, details={"duration_s": 300, **details},
    )  # fmt: skip


def test_weekly_numbers(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "t.db")
    rounds = [{"verdict": "changes_requested"}, {"verdict": "approved"}]
    for t in (
        task(1, "merged", reviews=rounds, reverted_by="t9"),
        task(2, "done", retries=[{"kind": "tests"}]),
        task(3, "failed", retries=[{"kind": "agent"}]),
        task(4, "discarded", incidents=[{"severity": "high"}]),
        task(5, "running"),  # not finished: not counted yet
        task(6, "done", reverts="t1"),  # Dia's own rollback
        task(7, "failed", days_ago=7),
        task(8, "done", days_ago=70),  # older than the window
    ):
        store.save(t)
    store.log_audit("dia", "benchmark.regression", "nova", "fps -12%")
    rows = scorecard(store, weeks=3)
    assert [r["tasks"] for r in rows] == [0, 1, 4]
    now = rows[-1]
    assert now["success"] == 0.5 and now["discarded"] == 1 and now["rolled_back"] == 1
    assert now["retry_rescue"] == 0.5 and now["review_rounds"] == 2.0
    assert now["minutes_per_task"] == 5.0 and now["incidents"] == 1 and now["regressions"] == 1
    assert rows[1]["success"] == 0.0 and rows[0]["success"] is None
    text = format_table(rows)
    assert "retry rescue" in text and "50%" in text
