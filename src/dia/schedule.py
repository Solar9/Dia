"""Recurring jobs while `dia serve` runs: "every weekday at 7:30 give me the
briefing", "every night at 23:00 check the projects' backups".

A job has a cron expression (minute hour day month weekday, local time) and
what to do:

- ``say``: a request in your own words, handled like a message to Dia
  ("briefing", "pogoda", "Dia, sprawdź czy nova się buduje");
- ``task``: a task for an agent (``project``, ``prompt``, ``mode``);
- ``skill``: a skill with arguments.

The answer is sent to the channels as a ``schedule`` event (Discord, push,
UI; spoken aloud with ``speak = true``). Jobs come from ``[[schedule]]`` in the
config (read-only) and from ``<data_dir>/schedules.json`` (added in the UI,
with ``dia schedule add`` or by asking Dia).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from dia.agents import Mode
from dia.audit import ACTOR

if TYPE_CHECKING:
    from dia.assistant import Assistant
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.schedule")

_FIELDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_ALIASES = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@weekdays": "0 9 * * 1-5",
}


class CronError(ValueError):
    pass


def _field(text: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            if not step_text.isdigit() or int(step_text) == 0:
                raise CronError(f"bad step in {text!r}")
            step = int(step_text)
        if part == "*":
            start, end = low, high
        elif re.fullmatch(r"\d+-\d+", part):
            start, end = map(int, part.split("-"))
        elif part.isdigit():
            start = end = int(part)
            if step > 1:
                end = high
        else:
            raise CronError(f"bad cron field {text!r}")
        if not (low <= start <= end <= high):
            raise CronError(f"{text!r} is outside {low}-{high}")
        values.update(range(start, end + 1, step))
    return values


@dataclass(frozen=True)
class Cron:
    expression: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]  # 0 = Sunday ... 6 = Saturday
    any_day: bool
    any_weekday: bool

    @classmethod
    def parse(cls, expression: str) -> Cron:
        text = _ALIASES.get(expression.strip(), expression.strip())
        parts = text.split()
        if len(parts) != 5:
            raise CronError("a cron expression has 5 fields: minute hour day month weekday")
        sets = [_field(p, lo, hi) for p, (lo, hi) in zip(parts, _FIELDS, strict=True)]
        weekdays = frozenset(d % 7 for d in sets[4])
        return cls(
            expression.strip(),
            *(frozenset(s) for s in sets[:4]),
            weekdays,
            any_day=parts[2] == "*",
            any_weekday=parts[4] == "*",
        )

    def _day_ok(self, at: datetime) -> bool:
        if at.month not in self.months:
            return False
        day_ok = at.day in self.days
        weekday_ok = (at.isoweekday() % 7) in self.weekdays
        if self.any_day or self.any_weekday:  # cron: both restricted means either
            return day_ok and weekday_ok
        return day_ok or weekday_ok

    def matches(self, at: datetime) -> bool:
        return at.minute in self.minutes and at.hour in self.hours and self._day_ok(at)

    def next_after(self, at: datetime, limit_days: int = 366) -> datetime | None:
        """The first matching minute after ``at``."""
        day = at.replace(hour=0, minute=0, second=0, microsecond=0)
        for _ in range(limit_days + 1):
            if self._day_ok(day):
                for hour in sorted(self.hours):
                    for minute in sorted(self.minutes):
                        candidate = day.replace(hour=hour, minute=minute)
                        if candidate > at:
                            return candidate
            day += timedelta(days=1)
        return None


ACTIONS = ("say", "task", "skill")


@dataclass
class Job:
    id: str
    cron: str
    action: str = "say"
    name: str = ""
    text: str = ""  # say
    project: str = ""  # task
    prompt: str = ""  # task
    mode: str = "edit"  # task: edit | read-only
    skill: str = ""  # skill
    args: dict[str, Any] = field(default_factory=dict)  # skill
    speak: bool = False  # also read the answer aloud
    enabled: bool = True
    source: str = "store"  # "config" jobs can't be changed from Dia

    def validate(self) -> Job:
        Cron.parse(self.cron)
        if self.action not in ACTIONS:
            raise ValueError(f"action must be one of {', '.join(ACTIONS)}")
        needed = {"say": ["text"], "task": ["project", "prompt"], "skill": ["skill"]}
        for key in needed[self.action]:
            if not getattr(self, key):
                raise ValueError(f"a '{self.action}' job needs '{key}'")
        return self

    def label(self) -> str:
        return self.name or self.text or self.prompt or self.skill

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: str = "store") -> Job:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        known.setdefault("id", secrets.token_hex(3))
        known["source"] = source
        return cls(**known)


class Schedules:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    @property
    def path(self):
        return self.dia.config.data_dir / "schedules.json"

    def _stored(self) -> list[Job]:
        try:
            return [Job.from_dict(d) for d in json.loads(self.path.read_text())]
        except (OSError, ValueError, TypeError):
            return []

    def _save(self, jobs: list[Job]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [{k: v for k, v in asdict(j).items() if k != "source"} for j in jobs]
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    def list(self) -> list[Job]:
        configured = self.dia.config.raw.get("schedule", [])
        jobs = []
        for i, data in enumerate(configured if isinstance(configured, list) else []):
            jobs.append(Job.from_dict({"id": f"config-{i}", **data}, source="config"))
        return jobs + self._stored()

    def add(self, data: dict[str, Any]) -> Job:
        data = {k: v for k, v in data.items() if k not in ("id", "source")}
        job = Job.from_dict(data).validate()
        self._save([*self._stored(), job])
        self.dia.audit("schedule.add", job.id, f"{job.cron} {job.label()}")
        return job

    def update(self, job_id: str, changes: dict[str, Any]) -> Job:
        jobs = self._stored()
        for i, job in enumerate(jobs):
            if job.id == job_id:
                merged = {**asdict(job), **changes, "id": job.id}
                jobs[i] = Job.from_dict(merged).validate()
                self._save(jobs)
                return jobs[i]
        raise LookupError(f"no schedule {job_id} (jobs from the config file can't be changed)")

    def remove(self, job_id: str) -> bool:
        jobs = self._stored()
        kept = [j for j in jobs if j.id != job_id]
        if len(kept) == len(jobs):
            return False
        self._save(kept)
        self.dia.audit("schedule.remove", job_id)
        return True

    def next_runs(self, now: datetime | None = None) -> dict[str, str | None]:
        now = now or datetime.now().astimezone()
        result = {}
        for job in self.list():
            try:
                at = Cron.parse(job.cron).next_after(now) if job.enabled else None
            except CronError:
                at = None
            result[job.id] = at.isoformat() if at else None
        return result


class Scheduler:
    """Runs due jobs every minute (in `dia serve`)."""

    def __init__(self, dia: Orchestrator, assistant: Assistant | None = None) -> None:
        from dia.assistant import Assistant

        self.dia = dia
        self.schedules = Schedules(dia)
        self.assistant = assistant or Assistant(dia)
        self._last: datetime | None = None
        self._jobs: set[asyncio.Task] = set()

    async def run(self) -> None:
        log.info("scheduler: %d job(s)", len(self.schedules.list()))
        while True:
            now = datetime.now().astimezone().replace(second=0, microsecond=0)
            if now != self._last:
                self._last = now
                self.tick(now)
            await asyncio.sleep(60 - datetime.now().second + 0.5)

    def tick(self, now: datetime) -> list[Job]:
        from dia.attention import Attention

        if summary := Attention(self.dia).take_summary(now):  # quiet hours are over
            self.dia.spawn(self.dia.emit("digest", None, summary))
        if self.dia.halted:
            return []
        due = []
        for job in self.schedules.list():
            try:
                if job.enabled and Cron.parse(job.cron).matches(now):
                    due.append(job)
            except CronError as exc:
                log.warning("schedule %s: %s", job.id, exc)
        for job in due:
            task = asyncio.ensure_future(self.execute(job))
            self._jobs.add(task)
            task.add_done_callback(self._jobs.discard)
        return due

    async def execute(self, job: Job) -> str:
        ACTOR.set(f"schedule:{job.id}")
        log.info("schedule %s: %s", job.id, job.label())
        self.dia.audit("schedule.run", job.id, job.label())
        record = None
        try:
            if job.action == "task":
                mode = Mode.READ_ONLY if job.mode == "read-only" else Mode.EDIT
                report = await self.dia.run_task(job.project, job.prompt, mode=mode)
                record = report.task
                text = record.summary or record.error or record.status
            elif job.action == "skill":
                text = await self.assistant.run_skill(job.skill, job.args)
            else:
                response = await self.assistant.handle(job.text)
                record = response.report.task if response.report else None
                text = response.text
        except Exception as exc:
            log.exception("schedule %s failed", job.id)
            text = f"{job.label()}: {exc}"
        await self.dia.emit("schedule", record, text, data={"job": asdict(job)})
        return text
