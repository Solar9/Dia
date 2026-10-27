from datetime import UTC, datetime, timedelta
from pathlib import Path

from dia.config import parse_config
from dia.limits import Limits, is_limit, retry_at
from dia.orchestrator import Orchestrator

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def test_detects_limit_messages() -> None:
    assert is_limit("Claude AI usage limit reached|1761345600")
    assert is_limit("You've hit your usage limit. Try again in 3 hours.")
    assert is_limit("Error: 429 Too Many Requests")
    assert not is_limit("All tests passed")


def test_parses_reset_times() -> None:
    assert retry_at("Claude AI usage limit reached|1761345600") == datetime.fromtimestamp(
        1761345600, UTC
    )
    assert retry_at("try again in 90 minutes", NOW) == NOW + timedelta(minutes=90)
    assert retry_at("try again in 2h", NOW) == NOW + timedelta(hours=2)
    assert retry_at("limit reached") is None


def test_limits_persist_and_expire(tmp_path: Path) -> None:
    limits = Limits(tmp_path)
    limits.block("claude", datetime.now(UTC) + timedelta(hours=1))
    assert not Limits(tmp_path).available("claude")
    limits.block("codex", datetime.now(UTC) - timedelta(seconds=1))
    assert limits.available("codex") and limits.available("cursor")


def make(tmp_path: Path, repo: Path, limits: dict | None = None) -> Orchestrator:
    limited = ["sh", "-c", "echo 'Claude AI usage limit reached' >&2; exit 1"]
    working = ["sh", "-c", "echo done > out.txt; echo did it"]
    return Orchestrator(
        parse_config(
            {
                "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "claude"},
                "agents": {
                    "claude": {"type": "command", "argv": limited},
                    "codex": {"type": "command", "argv": working},
                },
                "projects": {"demo": {"path": str(repo)}},
                "limits": limits or {},
            }
        )
    )


async def test_limited_agent_hands_over_to_fallback(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo)
    events = []

    async def listen(event):
        events.append(event)

    orch.listeners.append(listen)
    task = (await orch.run_task("demo", "add output")).task
    assert task.status == "done", task.error
    assert task.details["author"] == "codex"
    assert task.details["fallbacks"] == [{"from": "claude", "to": "codex"}]
    assert "claude" in orch.limit_status()
    assert events[0].kind == "limit"
    # Known to be limited now: the next task skips claude without trying it.
    assert not orch.limits.available("claude")


async def test_no_fallback_and_no_wait_fails_with_reset_time(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, {"fallback": False, "wait": False})
    task = (await orch.run_task("demo", "add output")).task
    assert task.status == "failed" and "usage limit" in task.error


async def test_usage_counts_every_agent_call(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo)
    await orch.run_task("demo", "add output")
    usage = orch.store.usage(7)
    by_agent = {a["agent"]: a for a in usage["agents"]}
    assert by_agent["claude"]["limited"] == 1 and by_agent["claude"]["ok"] == 0
    assert by_agent["codex"]["calls"] == 1 and by_agent["codex"]["ok"] == 1
    assert usage["purposes"] == {"task": 2}
    assert usage["projects"] == [{"project": "demo", "tasks": 1, "done": 1, "failed": 0}]
    assert len(usage["daily"]) == 1
