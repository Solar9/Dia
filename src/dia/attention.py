"""How much Dia may interrupt you: quiet hours and a daily notification budget.

    [notifications]
    quiet_hours = "22:00-07:30"    # no announcements and no push in this window
    budget = 20                    # at most this many push notifications a day
    urgent = ["system", "security", "stop"]   # these always get through

What is held back is not lost: the first notification after quiet hours (or
the next day) comes with a summary of what was held, and the app lists it
(``GET /api/notifications``). Answers to what you ask are never held: quiet
hours only silence what Dia says on its own. Quiet mode ("tryb cichy")
stays the switch for silencing speech entirely.
"""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

URGENT = ["system", "security", "stop"]


def parse_window(text: str) -> tuple[time, time] | None:
    """ "22:00-07:30" -> (22:00, 07:30); None for an empty or invalid window."""
    try:
        start, end = (time.fromisoformat(p.strip()) for p in str(text).split("-", 1))
    except ValueError:
        return None
    return start, end


def in_window(window: tuple[time, time] | None, now: datetime) -> bool:
    if not window:
        return False
    start, end, t = window[0], window[1], now.time()
    return start <= t < end if start <= end else t >= start or t < end  # over midnight


class Attention:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self.path = dia.config.data_dir / "attention.json"

    @property
    def options(self) -> dict[str, Any]:
        return self.dia.config.section("notifications")

    def quiet_hours(self, now: datetime | None = None) -> bool:
        window = parse_window(self.options.get("quiet_hours", ""))
        return in_window(window, now or datetime.now().astimezone())

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False))

    def held(self) -> list[dict[str, str]]:
        return self._load().get("held", [])

    def admit(self, kind: str, title: str, body: str, now: datetime | None = None) -> bool:
        """May this notification go out now? If not, it is held for the summary."""
        now = now or datetime.now().astimezone()
        data = self._load()
        today = now.date().isoformat()
        if data.get("day") != today:
            data["day"], data["sent"] = today, 0
        urgent = kind in self.options.get("urgent", URGENT)
        budget = int(self.options.get("budget", 0) or 0)
        over = budget and data.get("sent", 0) >= budget
        if not urgent and (self.quiet_hours(now) or over):
            held = data.setdefault("held", [])
            held.append({"kind": kind, "title": title, "body": body[:200], "at": now.isoformat()})
            del held[:-100]  # the most recent 100 are plenty
            self._save(data)
            return False
        data["sent"] = data.get("sent", 0) + 1
        self._save(data)
        return True

    def take_summary(self, now: datetime | None = None) -> str:
        """What was held, as one line per notification; clears it. '' outside the
        moments it may be told (during quiet hours nothing is released)."""
        if self.quiet_hours(now):
            return ""
        data = self._load()
        held = data.pop("held", [])
        if not held:
            return ""
        self._save(data)
        lines = [f"{h['title']}: {h['body']}".strip(": ") for h in held[-10:]]
        more = len(held) - len(lines)
        return "\n".join(lines) + (f"\n(+{more})" if more > 0 else "")
