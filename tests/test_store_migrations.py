import sqlite3
from pathlib import Path

from dia.core import store
from dia.core.store import MIGRATIONS, TaskRecord, TaskStore, migrate


def version(path: Path) -> int:
    with sqlite3.connect(path) as db:
        return db.execute("PRAGMA user_version").fetchone()[0]


def test_a_new_database_is_stamped_with_the_latest_version(tmp_path):
    path = tmp_path / "dia.db"
    TaskStore(path)
    assert version(path) == len(MIGRATIONS)


def test_a_database_made_before_versioning_is_stamped_and_keeps_its_data(tmp_path):
    path = tmp_path / "dia.db"
    # What the old code did: the schema script, no user_version.
    db = sqlite3.connect(path)
    db.executescript(store._SCHEMA_1)
    db.execute(
        "INSERT INTO tasks (id, project, agent, mode, prompt, status, created_at) "
        "VALUES ('old', 'demo', 'a', 'edit', 'do it', 'done', '2026-01-01T00:00:00+00:00')"
    )
    db.execute("INSERT INTO audit VALUES ('2026-01-01', 'cli', 'task.merge', 'old', '')")
    db.commit()
    db.close()
    assert version(path) == 0

    tasks = TaskStore(path)
    assert version(path) == 1
    assert tasks.get("old").prompt == "do it"
    assert tasks._db.execute("SELECT count(*) FROM audit").fetchone()[0] == 1
    tasks.save(TaskRecord(id="new", project="demo", agent="a", mode="edit", prompt="p"))
    assert {t.id for t in tasks.recent()} == {"old", "new"}


def test_later_migrations_run_once_and_in_order(tmp_path):
    db = sqlite3.connect(tmp_path / "x.db")
    steps = [
        "CREATE TABLE t (a TEXT);",
        "ALTER TABLE t ADD COLUMN b TEXT;",
        "ALTER TABLE t ADD COLUMN c TEXT;",
    ]
    assert migrate(db, steps[:1]) == 1
    db.execute("INSERT INTO t VALUES ('keep')")
    db.commit()
    assert migrate(db, steps) == 3
    assert migrate(db, steps) == 3  # idempotent: nothing is applied twice
    assert db.execute("SELECT a, b, c FROM t").fetchall() == [("keep", None, None)]


def test_a_database_from_a_newer_dia_is_left_alone(tmp_path):
    db = sqlite3.connect(tmp_path / "x.db")
    db.execute("PRAGMA user_version = 99")
    assert migrate(db) == 99


def test_the_audit_log_filters_by_action_prefix_and_target(tmp_path):
    from dia.core.store import TaskStore

    store = TaskStore(tmp_path / "t.db")
    for action, target in (("task.merge", "a"), ("task.discard", "b"), ("config.save", "c")):
        store.log_audit("tester", action, target, "detail")
    assert [e["action"] for e in store.audit()] == ["config.save", "task.discard", "task.merge"]
    assert [e["target"] for e in store.audit(action="task.")] == ["b", "a"]  # a prefix
    assert [e["action"] for e in store.audit(target="c")] == ["config.save"]
    assert len(store.audit(limit=2)) == 2
    assert store.audit(action="task.", target="a")[0]["actor"] == "tester"
    store.close()
