"""Brains turn a free-form message ("Dia, check what's up with Nova") into an
:class:`Intent` the core can execute.

Brains are tried in the order of ``[dia] brain`` until one answers, so a free
rule-based brain can handle trivial requests and a local model can fall back
to a cloud one. A brain only *interprets*; executing the intent is the
:class:`~dia.assistant.Assistant`'s job, and approvals (merge, discard) are
deliberately not something a brain can trigger.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from dia.config import Config

ACTIONS = (
    "run",
    "ask",
    "plan",
    "mission",
    "launch",
    "status",
    "tasks",
    "skill",
    "schedule",
    "stop",
    "resume",
    "quiet",
    "process",
    "service",
    "screen_access",
    "build",
    "council",
    "howto",
    "prefer",
    "scenario",
    "camera_access",
    "research",
    "experiment",
    "why",
    "check_notes",
    "impact",
    "debug",
    "goal",
    "work",
    "chat",
)


@dataclass
class Intent:
    action: str  # one of ACTIONS
    reply: str = ""  # short message for the user, in their language
    project: str | None = None
    agent: str | None = None
    prompt: str | None = None  # instruction for the coding agent (run/ask)
    skill: str | None = None  # which skill (action "skill")
    args: dict[str, Any] = field(default_factory=dict)  # the skill's arguments
    cron: str | None = None  # action "schedule": when (prompt: what to do then)
    text: str = ""  # the user's message it came from (for the conversation history)
    conversation: str = "default"  # whose conversation (a Discord user, the UI...)
    brain: str = ""  # which brain produced it


@dataclass
class BrainContext:
    projects: dict[str, str]  # name -> one-line description
    agents: list[str]
    default_agent: str | None = None
    recent_tasks: list[str] = field(default_factory=list)
    skills: dict[str, str] = field(default_factory=dict)  # name -> description with args
    persona: str = ""  # who Dia is (dia.persona.persona_prompt)
    history: list[tuple[str, str]] = field(default_factory=list)  # recent (user, Dia) turns
    surface: str = "desktop"  # where the answer is shown: desktop, phone, voice, discord


class Brain(ABC):
    kind: ClassVar[str]

    def __init__(self, name: str, options: dict[str, Any], config: Config) -> None:
        self.name = name
        self.options = dict(options)
        self.config = config

    @abstractmethod
    async def interpret(self, text: str, ctx: BrainContext) -> Intent | None:
        """The intent behind ``text``, or ``None`` to let the next brain try."""

    def check(self) -> str | None:
        return None

    def describe(self) -> str:
        return self.kind


SYSTEM_PROMPT = """\
You are the request router of Dia, a personal assistant that delegates software
work to coding agents. Turn the user's message into exactly one JSON object and
output nothing else:

{"action": "...", "project": "...", "agent": null, "prompt": "...", "skill": null,
 "args": {}, "cron": null, "reply": "..."}

action:
- "run": the user wants something built, changed or fixed in a project.
- "ask": a question that needs looking at a project's code or files, no changes.
  "Jak ja bym to zaprojektował?" / "how would I design it?" is "ask" too, with
  "prompt" = "Design it the way the user would, following their working-style
  profile, and give one alternative: <the thing>".
- "plan": a larger piece of work the user wants split into steps or shared
  between several agents (e.g. "design it with Claude, then let Codex build it").
- "mission": a big goal to organise across agents, with parts that can run in
  parallel ("organise the work on...", "get the game ready for the playtest").
  "prompt" = the goal.
- "launch": start/run/open a project itself, e.g. play the game.
- "status": how Dia, its agents or running tasks are doing.
- "tasks": list recent tasks.
- "skill": one of the listed skills fits (weather, news, markets...): set
  "skill" to its name and "args" to its arguments (omit what the user did not say).
- "schedule": the user wants something done regularly or at a set time
  ("every morning at 7 give me the weather"): "cron" = a 5-field cron
  expression in local time (minute hour day month weekday), "prompt" = what
  to do then, phrased as a request to you.
- "build": make a build/test version of a project ("przygotuj nową wersję
  testową nova"): "project", "args" = {"version": "...", "preset": "..."} when said.
- "council": the user wants several AI opinions on a question or decision ("zwołaj
  radę", "co o tym myślą wszyscy agenci"): "prompt" = the question; "project"
  when it is about one, else null.
- "scenario": the user asks whether something in a game/project works ("czy parry
  działa w nova?", "does saving work?"): "project", "prompt" = the behaviour to
  check, as a scenario to test. Dia writes a test for it and runs it.
- "research": the user wants something looked up on the web and summed up in a
  report ("zrób research", "sprawdź w internecie, jak ..."): "prompt" = the
  topic, "project" when it is about one, else null.
- "experiment": the user wants to know whether a change would help, tried several
  ways and measured ("sprawdź, czy przepisanie ekwipunku na ECS przyspieszy nova",
  "niech claude i codex zrobią to po swojemu i porównaj"): "project", "prompt" =
  the change, "args" = {"approaches": ["...", "..."]} when the user names ways to
  do it, {"agents": ["...", "..."]} when they name agents. Nothing is merged.
- "why": the user asks why something was decided or dropped earlier ("dlaczego
  zrezygnowaliśmy z ECS?", "why did we reject the new save system?"): "prompt" =
  the question, "project" when it is about one, else null. Dia searches its
  decision log, notes and commits.
- "check_notes": the user wants the project's notes/docs checked against the code
  ("sprawdź, czy notatki nova są aktualne", "are the docs still right?"): "project".
- "impact": the user asks what could break if something changes ("co się może
  zepsuć, jeśli zmienię dash?", "what depends on the save system?"): "project",
  "args" = {"target": "<the file, file name or name, e.g. dash>"}.
- "debug": the user describes a bug and wants its cause found ("znajdź, czemu
  postać przelatuje przez ścianę w nova", "debug the save crash"): "project",
  "prompt" = the bug as described. Several agents propose causes; tests decide.
- "goal": a goal over weeks, bigger than a mission ("cel: Starfall do Early
  Access w 8 tygodni"): "project", "prompt" = the goal, "args" = {"weeks": N} when
  said. Dia breaks it into milestones and reviews it weekly.
- "work": the user starts or ends a work session ("zaczynam pracę nad
  Starfall", "kończę na dziś, zapisz że skończyłem na dashu"): "args" =
  {"action": "start" or "stop", "profile": "<the name they used>", "note": "..."}.
- "howto": the user wants Dia to remember how the last task was done ("zapamiętaj,
  jak to zrobiłeś", "remember how you did it").
- "prefer": the user states a lasting personal preference about how Dia should
  work or answer ("wolę krótkie odpowiedzi", "remember I don't like emojis"):
  "args" = {"text": "<the preference, in the user's words, third person>"}.
- "process": end a running program ("zamknij zawieszonego godota"): "args" =
  {"name": "<program name>", "force": false}. Dia asks the user to confirm.
- "service": restart one of the user's systemd services: "args" = {"unit": "..."}.
- "chat": anything else: conversation, general questions you can answer
  yourself, or a clarifying question when it is unclear which project is meant.

Rules:
- "project" must be one of the listed project names, or null. Never invent one.
- "agent": only if the user explicitly named one of the listed agents, else null.
- "prompt" (run/ask/plan): a clear, self-contained instruction for a coding agent,
  in the user's language, keeping every detail the user gave.
- "reply": in the user's language and in your own personality: one short
  sentence saying what you will do, or your full answer (chat), or a
  clarifying question (e.g. which project).
- Merging, discarding or deleting work is never done by you: use "chat" and tell
  the user to use the Merge/Discard buttons or `dia merge` / `dia discard`.

Examples (projects: nova, dia):
- "napraw zapisywanie gry w nova" -> {"action": "run", "project": "nova", "agent": null,
  "prompt": "Napraw zapisywanie gry.", "reply": "Zlecam naprawę zapisu w nova."}
- "how does the save system in nova work?" -> {"action": "ask", "project": "nova",
  "agent": null, "prompt": "Explain how the save system works.", "reply": "Checking."}
- "jaka jutro pogoda w Gdańsku" -> {"action": "skill", "skill": "weather",
  "args": {"place": "Gdańsk", "day": "tomorrow"}, "reply": ""}
- "co rano o 7:30 w dni robocze daj mi briefing" -> {"action": "schedule",
  "cron": "30 7 * * 1-5", "prompt": "briefing", "reply": ""}
- "dodaj tryb co-op" (no project named) -> {"action": "chat", "project": null,
  "reply": "Do którego projektu? nova czy dia?"}
- "jak się masz?" -> {"action": "chat", "reply": "<a short answer in your personality>"}
"""


# How the "reply" should look where it will be read or heard.
SURFACE_STYLE = {
    "phone": "The user reads your reply on a phone: one or two short sentences, no lists.",
    "voice": "Your reply is read aloud: plain spoken sentences, no Markdown, no lists, short.",
    "discord": "Your reply is shown on Discord: short; Markdown is fine.",
}


def render_request(text: str, ctx: BrainContext) -> str:
    projects = "\n".join(f"- {name}: {desc}" for name, desc in ctx.projects.items()) or "(none)"
    agents = (
        ", ".join(f"{a} (default)" if a == ctx.default_agent else a for a in ctx.agents) or "(none)"
    )
    recent = "\n".join(f"- {t}" for t in ctx.recent_tasks) or "(none)"
    skills = "\n".join(f"- {desc}" for desc in ctx.skills.values()) or "(none)"
    history = ""
    if ctx.history:
        turns = "\n".join(f"User: {u}\nYou: {d}" for u, d in ctx.history)
        history = (
            "Conversation so far (use it to understand follow-ups like "
            f'"and tomorrow?" or "do it in nova"):\n{turns}\n\n'
        )
    return history + (
        f"Projects:\n{projects}\n\nAgents: {agents}\n\nSkills:\n{skills}\n\n"
        f"Recent tasks:\n{recent}\n\nUser message:\n{text}"
    )


def _match(name: Any, options: list[str]) -> str | None:
    if not isinstance(name, str):
        return None
    lowered = {o.lower(): o for o in options}
    return lowered.get(name.strip().lower())


def parse_intent(raw: str, text: str, ctx: BrainContext) -> Intent:
    """Parse and validate a model's JSON answer; anything unusable becomes "chat"."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in brain output: {raw[:200]!r}")
    data = json.loads(match.group(0))
    action = data.get("action")
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    intent = Intent(
        action=action,
        reply=str(data.get("reply") or "").strip(),
        project=_match(data.get("project"), list(ctx.projects)),
        agent=_match(data.get("agent"), ctx.agents),
        prompt=str(data.get("prompt") or "").strip() or text,
        skill=_match(data.get("skill"), list(ctx.skills)),
        args=data.get("args") if isinstance(data.get("args"), dict) else {},
        cron=str(data["cron"]).strip() if data.get("cron") else None,
    )
    if intent.action == "schedule" and not intent.cron:
        return Intent("chat", reply=intent.reply)
    if intent.action == "skill" and not intent.skill:
        return Intent("chat", reply=intent.reply)
    needs_project = (
        "run",
        "ask",
        "plan",
        "mission",
        "launch",
        "build",
        "experiment",
        "check_notes",
    )
    if intent.action in needs_project and not intent.project:
        names = ", ".join(ctx.projects) or "none configured"
        return Intent("chat", reply=intent.reply or f"Which project? ({names})")
    return intent


class LLMBrain(Brain):
    """A brain backed by a language model: subclasses only implement ``complete``."""

    @abstractmethod
    async def complete(self, system: str, user: str) -> str: ...

    async def interpret(self, text: str, ctx: BrainContext) -> Intent | None:
        system = SYSTEM_PROMPT + (f"\n{ctx.persona}\n" if ctx.persona else "")
        if style := SURFACE_STYLE.get(ctx.surface):
            system += f"\n{style}\n"
        raw = await self.complete(system, render_request(text, ctx))
        return parse_intent(raw, text, ctx)
