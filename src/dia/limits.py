"""Usage limits of subscription agents: notice them, remember them, work around them.

When an agent stops because its plan's limit is used up ("Claude AI usage limit
reached", Codex's "You've hit your usage limit", HTTP 429...), Dia marks it
unavailable until the time the message names (or a default cooldown), hands
the step to another agent, or waits. The marks are kept in
``<data_dir>/limits.json`` so every Dia process and restart sees them.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

LIMIT_PATTERNS = [
    r"usage limit",
    r"rate.?limit",
    r"limit (?:reached|exceeded)",
    r"hit your (?:\w+ )?limit",
    r"quota (?:exceeded|reached)|insufficient_quota",
    r"too many requests",
    r"\b429\b",
    r"out of (?:credits|requests)",
]
_LIMIT = re.compile("|".join(LIMIT_PATTERNS), re.IGNORECASE)
_EPOCH = re.compile(r"\|(\d{10})\b")  # Claude: "Claude AI usage limit reached|1761345600"
_IN = re.compile(
    r"(?:in|after)\s+(?:about\s+)?(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\b",
    re.IGNORECASE,
)
_AT = re.compile(r"(?:at|until|resets?)\s+(\d{1,2}):(\d{2})\s*(am|pm)?", re.IGNORECASE)


def is_limit(text: str) -> bool:
    return bool(_LIMIT.search(text or ""))


def retry_at(text: str, now: datetime | None = None) -> datetime | None:
    """When the limit ends, if the message says so."""
    now = now or datetime.now(UTC)
    if match := _EPOCH.search(text):
        return datetime.fromtimestamp(int(match.group(1)), UTC)
    if match := _IN.search(text):
        amount, unit = float(match.group(1)), match.group(2).lower()
        seconds = amount * (3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1)
        return now + timedelta(seconds=seconds)
    if match := _AT.search(text):
        hour, minute = int(match.group(1)), int(match.group(2))
        if (suffix := (match.group(3) or "").lower()) == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        local = now.astimezone()
        at = local.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
        if at <= local:
            at += timedelta(days=1)
        return at.astimezone(UTC)
    return None


class Limits:
    """Which agents are out of their limit, and until when."""

    def __init__(self, data_dir: Path, default_cooldown: timedelta = timedelta(hours=1)) -> None:
        self.path = data_dir / "limits.json"
        self.default_cooldown = default_cooldown

    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def block(self, agent: str, until: datetime | None = None) -> datetime:
        until = until or datetime.now(UTC) + self.default_cooldown
        data = self._load()
        data[agent] = until.isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))
        return until

    def clear(self, agent: str | None = None) -> None:
        """Forget a limit (all of them without ``agent``), e.g. after upgrading a plan."""
        data = {} if agent is None else {k: v for k, v in self._load().items() if k != agent}
        if self.path.exists():
            self.path.write_text(json.dumps(data, indent=2))

    def blocked_until(self, agent: str) -> datetime | None:
        value = self._load().get(agent)
        if not value:
            return None
        until = datetime.fromisoformat(value)
        return until if until > datetime.now(UTC) else None

    def available(self, agent: str) -> bool:
        return self.blocked_until(agent) is None
