from types import SimpleNamespace

from dia.core import taskstate


def task(status, commit_sha=None, details=None):
    return SimpleNamespace(status=status, commit_sha=commit_sha, details=details or {})


def test_decision_rule():
    assert taskstate.decision_of(task("done", "abc")) == "merge"
    assert taskstate.decision_of(task("done")) is None
    assert taskstate.decision_of(task("planned")) == "plan"
    assert taskstate.decision_of(task("published", details={"ci": {"state": "failed"}})) == "ci"
    assert (
        taskstate.decision_of(task("published", details={"comments_pending": ["x"]})) == "comments"
    )
    assert taskstate.decision_of(task("published")) is None
    assert taskstate.decision_of(task("failed", "abc")) is None


def test_counts():
    tasks = [task("running"), task("queued"), task("waiting"), task("done", "a"), task("merged")]
    assert taskstate.counts(tasks) == {"running": 3, "waiting_for_you": 1}
    assert taskstate.counts([]) == {"running": 0, "waiting_for_you": 0}
