"""Skills: everyday things Dia can do besides coding (weather, news, markets...).

A skill is a plugin in the ``dia.skills`` group. The brain picks one by name
with arguments (``{"action": "skill", "skill": "weather", "args": {"place":
"Kraków"}}``); the skill fetches what it needs and answers with a short text
in the user's language, suitable for reading aloud. Options come from
``[skills.<name>]``; ``[assistant] skills`` limits which ones are enabled.
"""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, ClassVar

from dia import plugins

if TYPE_CHECKING:
    from dia.config import Config
    from dia.orchestrator import Orchestrator

USER_AGENT = "Dia/0.1 (personal assistant; https://github.com/Solar9/Dia)"


class NeedsConfirmation(Exception):
    """Raised by a skill whose action needs the user's yes first (a lock, an alarm...):
    the assistant asks ``question`` and runs ``action`` on a yes."""

    def __init__(self, question: str, action: Callable[[], Awaitable[str]]) -> None:
        super().__init__(question)
        self.question, self.action = question, action


class Skill(ABC):
    kind: ClassVar[str]
    # For the brain: what it does and which arguments it takes.
    description: ClassVar[str]
    args: ClassVar[dict[str, str]] = {}

    def __init__(self, options: dict[str, Any], dia: Orchestrator) -> None:
        self.options = dict(options)
        self.dia = dia

    @property
    def config(self) -> Config:
        return self.dia.config

    @property
    def language(self) -> str:
        return self.config.language

    def t(self, pl: str, en: str) -> str:
        return pl if self.language == "pl" else en

    @abstractmethod
    async def run(self, args: dict[str, Any]) -> str:
        """The answer, as short text in the user's language."""

    def describe(self) -> str:
        spec = ", ".join(f"{k}: {v}" for k, v in self.args.items())
        return f"{self.kind}({spec}): {self.description}"


async def fetch(url: str, params: dict[str, Any] | None = None, timeout: float = 15) -> bytes:
    """GET ``url`` (standard library only), in a thread."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

    def get() -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(5_000_000)

    return await asyncio.to_thread(get)


async def fetch_json(url: str, params: dict[str, Any] | None = None) -> Any:
    return json.loads(await fetch(url, params))


def enabled_skills(dia: Orchestrator) -> dict[str, Skill]:
    """The skills to offer, by name (all installed ones unless ``[assistant] skills``)."""
    config = dia.config
    names = config.assistant.get("skills") or list(plugins.available("dia.skills"))
    options = config.section("skills")
    skills = {}
    for name in names:
        try:
            skills[name] = plugins.load("dia.skills", name)(options.get(name, {}), dia)
        except (LookupError, ImportError):
            continue
    return skills
