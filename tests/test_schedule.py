from datetime import datetime
from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.brains import BrainContext, parse_intent
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.schedule import Cron, CronError, Scheduler, Schedules


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def test_cron_matching() -> None:
    weekdays = Cron.parse("30 7 * * 1-5")
    assert weekdays.matches(at("2026-10-23 07:30"))  # Friday
    assert not weekdays.matches(at("2026-10-24 07:30"))  # Saturday
    assert not weekdays.matches(at("2026-10-23 07:31"))
    every15 = Cron.parse("*/15 9-17 * * *")
    assert every15.matches(at("2026-10-24 17:45")) and not every15.matches(at("2026-10-24 18:00"))
    sunday = Cron.parse("0 12 * * 7")
    assert sunday.matches(at("2026-10-25 12:00"))
    # Day and weekday both given: either one matches (as in cron).
    either = Cron.parse("0 0 1 * 1")
    assert either.matches(at("2026-10-01 00:00")) and either.matches(at("2026-10-26 00:00"))
    assert Cron.parse("@daily").matches(at("2026-10-24 00:00"))
    for bad in ("* * *", "61 * * * *", "*/0 * * * *", "a * * * *"):
        with pytest.raises(CronError):
            Cron.parse(bad)


def test_next_run() -> None:
    assert Cron.parse("30 7 * * 1-5").next_after(at("2026-10-23 08:00")) == at("2026-10-26 07:30")
    leap = Cron.parse("0 0 29 2 *")
    assert leap.next_after(at("2026-10-24 00:00")) is None  # not within a year
    assert leap.next_after(at("2026-10-24 00:00"), 3 * 366) == at("2028-02-29 00:00")


@pytest.fixture
def dia(tmp_path: Path) -> Orchestrator:
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "language": "pl", "brain": ["rules"]},
            "schedule": [{"cron": "0 23 * * *", "text": "status", "name": "nightly"}],
        }
    )
    return Orchestrator(config, use_memory=False)


async def test_jobs_from_config_and_store(dia: Orchestrator) -> None:
    schedules = Schedules(dia)
    job = schedules.add({"cron": "30 7 * * 1-5", "text": "zadania", "speak": True})
    assert [j.source for j in schedules.list()] == ["config", "store"]
    with pytest.raises(ValueError):
        schedules.add({"cron": "30 7 * *", "text": "x"})
    with pytest.raises(ValueError):
        schedules.add({"cron": "* * * * *", "action": "task", "prompt": "no project"})
    with pytest.raises(LookupError):
        schedules.update("config-0", {"enabled": False})
    assert schedules.update(job.id, {"enabled": False}).enabled is False
    assert schedules.next_runs()[job.id] is None

    events = []

    async def listen(event):
        events.append(event)

    dia.listeners.append(listen)
    scheduler = Scheduler(dia)
    due = scheduler.tick(at("2026-10-24 23:00").astimezone())
    assert [j.name for j in due] == ["nightly"]
    await scheduler.execute(due[0])
    assert events[-1].kind == "schedule"
    assert events[-1].message == "Żadne zadanie teraz nie trwa."
    assert events[-1].data["job"]["name"] == "nightly"
    assert schedules.remove(job.id) and not schedules.remove(job.id)


async def test_asking_dia_to_schedule(dia: Orchestrator) -> None:
    ctx = BrainContext({}, [])
    raw = '{"action": "schedule", "cron": "0 7 * * *", "prompt": "pogoda", "reply": ""}'
    intent = parse_intent(raw, "codziennie o 7 mów mi pogodę", ctx)
    answer = (await Assistant(dia, brains=[]).execute(intent)).text
    assert answer.startswith("Ustawione (0 7 * * *): pogoda. Najbliżej: ")
    assert Schedules(dia).list()[-1].text == "pogoda"
    bad = parse_intent('{"action": "schedule", "cron": "o siódmej", "prompt": "x"}', "x", ctx)
    assert "Nie umiem" in (await Assistant(dia, brains=[]).execute(bad)).text
