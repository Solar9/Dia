from datetime import datetime, time
from pathlib import Path

from dia.attention import Attention, in_window, parse_window
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.schedule import Scheduler


def make(tmp_path: Path, **notifications) -> Orchestrator:
    raw = {"dia": {"data_dir": str(tmp_path)}, "notifications": notifications}
    return Orchestrator(parse_config(raw), use_memory=False)


def at(hour: int, minute: int = 0, day: int = 25) -> datetime:
    return datetime(2026, 10, day, hour, minute).astimezone()


def test_windows() -> None:
    night = parse_window("22:00-07:30")
    assert night == (time(22), time(7, 30))
    assert in_window(night, at(23)) and in_window(night, at(3)) and in_window(night, at(7, 29))
    assert not in_window(night, at(7, 30)) and not in_window(night, at(12))
    lunch = parse_window("12:00 - 13:00")
    assert in_window(lunch, at(12, 30)) and not in_window(lunch, at(13))
    assert parse_window("") is None and parse_window("late") is None
    assert not in_window(None, at(3))


def test_quiet_hours_hold_all_but_urgent(tmp_path: Path) -> None:
    attention = Attention(make(tmp_path, quiet_hours="22:00-07:00"))
    assert not attention.admit("ci", "CI · nova", "failed", at(23))
    assert attention.admit("system", "Computer", "CPU at 95 °C", at(23))  # urgent
    assert [h["title"] for h in attention.held()] == ["CI · nova"]
    assert attention.take_summary(at(23, 30)) == ""  # still quiet: nothing released
    assert attention.take_summary(at(8)) == "CI · nova: failed"
    assert attention.held() == [] and attention.take_summary(at(8)) == ""


def test_the_daily_budget(tmp_path: Path) -> None:
    attention = Attention(make(tmp_path, budget=2))
    assert attention.admit("task", "a", "", at(9)) and attention.admit("task", "b", "", at(10))
    assert not attention.admit("task", "c", "", at(11))
    assert attention.admit("task", "d", "", at(9, day=26))  # a new day, a new budget


async def test_the_scheduler_sends_the_summary_when_quiet_hours_end(tmp_path: Path) -> None:
    dia = make(tmp_path, quiet_hours="22:00-07:00")
    events = []

    async def listen(event):
        events.append((event.kind, event.message))

    dia.listeners.append(listen)
    Attention(dia).admit("watch", "Build · nova", "broken", at(23))
    scheduler = Scheduler(dia)
    scheduler.tick(at(23, 30))
    scheduler.tick(at(7, 1))
    await dia.drain()
    assert events == [("digest", "Build · nova: broken")]
