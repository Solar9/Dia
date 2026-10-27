"""What Dia knows about how you like things done: "wolę krótkie odpowiedzi",
"nie używaj emoji", "w testach używam GUT".

Preferences come from three places:

- you say them: "Dia, zapamiętaj, że wolę krótkie odpowiedzi" (kept at once);
- the config: ``[assistant] preferences = ["..."]``;
- Dia notices them in your conversations (``[assistant] learn_preferences =
  true``): every ``learn_every`` turns a cheap model call proposes what looks
  like a lasting preference. Proposals wait for you (Memory → Preferences, or
  ``dia preferences``); nothing is used before you accept it.

Accepted preferences are part of every prompt: how Dia answers you, and the
background the coding agents get. They live in ``<data_dir>/preferences.json``.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.agents import AgentRequest, Mode

if TYPE_CHECKING:
    from dia.config import Config
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.preferences")

PROMPT = """\
These are recent exchanges between the user and their assistant:

{turns}

Preferences already known:
{known}

Does the user show a lasting personal preference about how the assistant (or
the coding agents it runs) should work or answer: tone, length, language,
tools, habits, things to avoid? Only clear, lasting preferences, never a
one-off request, nothing already known, nothing private or sensitive (health,
relationships, money). Proposing nothing is normal.

Answer with JSON only: {{"preferences": ["The user prefers ...", ...]}}"""


class Preferences:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.path = config.data_dir / "preferences.json"

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        return {"accepted": data.get("accepted", []), "proposed": data.get("proposed", [])}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def snapshot(self) -> dict[str, Any]:
        data = self._load()
        configured = [str(p) for p in self.config.assistant.get("preferences", [])]
        return {**data, "configured": configured}

    def active(self) -> list[str]:
        """Every preference in force: from the config, then the accepted ones."""
        data = self.snapshot()
        return [*data["configured"], *(p["text"] for p in data["accepted"])]

    def add(self, text: str) -> str:
        text = " ".join(text.split()).rstrip(".")[:300]
        if not text:
            raise ValueError("an empty preference")
        data = self._load()
        if text.lower() not in (p["text"].lower() for p in data["accepted"]):
            data["accepted"].append({"text": text, "added": _today()})
            self._save(data)
        return text

    def propose(self, texts: list[str]) -> list[str]:
        data = self._load()
        seen = {p["text"].lower() for p in data["accepted"] + data["proposed"]}
        seen |= {p.lower() for p in self.snapshot()["configured"]}
        new = [t for t in texts if t.lower() not in seen]
        data["proposed"] += [{"text": t, "added": _today()} for t in new]
        if new:
            self._save(data)
        return new

    def decide(self, index: int, accept: bool) -> str:
        data = self._load()
        if not 0 <= index < len(data["proposed"]):
            raise IndexError(f"no proposed preference {index + 1}")
        item = data["proposed"].pop(index)
        if accept:
            data["accepted"].append({"text": item["text"], "added": _today()})
        self._save(data)
        return item["text"]

    def remove(self, index: int) -> str:
        data = self._load()
        if not 0 <= index < len(data["accepted"]):
            raise IndexError(f"no preference {index + 1}")
        item = data["accepted"].pop(index)
        self._save(data)
        return item["text"]


def _today() -> str:
    return f"{datetime.now():%Y-%m-%d}"


def preferences_text(config: Config) -> str:
    """The preferences as a prompt section ('' when there are none)."""
    try:
        active = Preferences(config).active()
    except Exception:  # never break a prompt over this
        log.exception("could not read preferences")
        return ""
    return "\n".join(f"- {p}" for p in active)


def parse_preferences(text: str) -> list[str]:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        items = json.loads(match.group(0)).get("preferences", []) if match else []
    except (ValueError, AttributeError):
        return []
    clean = [" ".join(str(p).split()) for p in items if isinstance(p, str)]
    return [p[:300] for p in clean if p][:3]


async def learn_preferences(dia: Orchestrator, turns: list[tuple[str, str]]) -> list[str]:
    """Propose preferences seen in ``turns``; they wait for the user's approval."""
    if not turns:
        return []
    prefs = Preferences(dia.config)
    options = dia.config.assistant
    prompt = PROMPT.format(
        turns="\n".join(f"User: {u}\nAssistant: {a}" for u, a in turns),
        known="\n".join(f"- {p}" for p in prefs.active()) or "(none)",
    )
    try:
        with tempfile.TemporaryDirectory(prefix="dia-learn-") as empty:
            _, result = await dia.call_agent(
                dia.config.agent(options.get("learn_agent")),
                AgentRequest(
                    prompt=prompt,
                    cwd=Path(empty),
                    mode=Mode.READ_ONLY,
                    model=options.get("learn_model"),
                    tools=False,
                    timeout=180,
                ),
                purpose="learn",
            )
    except Exception:
        log.exception("learning preferences failed")
        return []
    new = prefs.propose(parse_preferences(result.summary) if result.success else [])
    if new:
        await dia.emit("preferences", None, "\n".join(new))
    return new
