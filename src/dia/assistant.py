"""Free-form requests: a brain interprets them, the assistant carries them out.

Channels that accept natural language (Discord messages, voice, ``dia say``)
go through here, so they all understand the same things the same way.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from dia.agents import Mode
from dia.brains import Brain, BrainContext, Intent
from dia.brains.rules import strip_address
from dia.orchestrator import Orchestrator, TaskActionError, TaskReport
from dia.persona import persona_prompt
from dia.skills import NeedsConfirmation, Skill, enabled_skills
from dia.store import TaskRecord

log = logging.getLogger("dia.assistant")

# Answers to "run this plan?", in the user's own words.
_YES = re.compile(r"^(tak|uruchom( go| plan)?|zaczynaj|start|dawaj|ok|okej|yes|go|run it|do it)$")
_NO = re.compile(r"^(nie|anuluj|stop|nie teraz|no|cancel|not now)$")

PLAN_PHRASES = {
    "pl": {
        "ask": "Plan dla {project}: {steps}. Uruchomić? Powiedz tak albo nie.",
        "cancelled": "Dobrze, nie uruchamiam planu.",
        "action_cancelled": "Dobrze, nie robię tego.",
        "agents_ready": "Gotowi agenci: {agents}.",
        "agent_problem": "Agent {agent} ma problem: {problem}",
        "no_active": "Żadne zadanie teraz nie trwa.",
        "limited": "{agent} wyczerpał limit do {time}.",
        "active": "Trwające zadania: {count}.",
        "no_tasks": "Nie ma jeszcze żadnych zadań.",
        "skill_failed": "Nie udało się ({skill}): {error}",
        "stopped": "Zatrzymane ({count}). Nic nowego nie ruszy, dopóki nie powiesz „wznów”.",
        "resumed": "Wznawiam pracę.",
        "quiet_on": "Tryb cichy: odpowiadam tylko tekstem.",
        "confirm_end": "Zamknąć {what}? Powiedz tak albo nie.",
        "screen_on": "Dostęp do ekranu włączony. Wyłączysz go, mówiąc „nie patrz na ekran”.",
        "screen_off": "Nie patrzę już na ekran.",
        "no_process": "Nie widzę uruchomionego programu „{name}”.",
        "too_many": "Pasuje {count} procesów: {what}. Powiedz dokładniej.",
        "ended": "Zamknięte: {what}.",
        "confirm_restart": "Zrestartować usługę {unit}? Powiedz tak albo nie.",
        "done": "Zrobione: {what}.",
        "quiet_off": "Znowu mówię.",
        "howto_none": "Nie widzę ukończonego zadania, z którego mogłabym spisać sposób.",
        "howto_ask": "Spisałam „{title}”: {steps} Zapisać to jako sposób na przyszłość?",
        "howto_saved": "Zapisane: {path}. Agenci użyją tego przy podobnych zadaniach.",
        "prefer_saved": "Zapamiętam: {text}.",
        "camera_on": "Kamera włączona. Wyłączysz ją, mówiąc „wyłącz kamerę”.",
        "camera_off": "Kamera wyłączona.",
        "scheduled": "Ustawione ({cron}): {what}. Najbliżej: {next}.",
        "schedule_bad": "Nie umiem ustawić takiego harmonogramu: {error}",
    },
    "en": {
        "ask": "Plan for {project}: {steps}. Run it? Say yes or no.",
        "cancelled": "OK, the plan won't run.",
        "action_cancelled": "OK, I won't do that.",
        "agents_ready": "Agents ready: {agents}.",
        "agent_problem": "Agent {agent} has a problem: {problem}",
        "no_active": "No tasks are running.",
        "limited": "{agent} is out of its usage limit until {time}.",
        "active": "Running tasks: {count}.",
        "no_tasks": "No tasks yet.",
        "skill_failed": "That didn't work ({skill}): {error}",
        "stopped": "Stopped {count} process(es). Nothing new starts until you say “resume”.",
        "resumed": "Back to work.",
        "quiet_on": "Quiet mode: text answers only.",
        "howto_none": "I don't see a finished task to write down.",
        "howto_ask": "I wrote down “{title}”: {steps} Keep it as a how-to for next time?",
        "howto_saved": "Saved: {path}. Agents will follow it on similar tasks.",
        "prefer_saved": "I'll remember: {text}.",
        "camera_on": "Camera on. Say “camera access off” to switch it off.",
        "camera_off": "Camera off.",
        "confirm_end": "End {what}? Say yes or no.",
        "screen_on": "Screen access on. Say “stop looking at the screen” to switch it off.",
        "screen_off": "I'm not looking at the screen any more.",
        "no_process": "I don't see a running program called “{name}”.",
        "too_many": "{count} processes match: {what}. Be more specific.",
        "ended": "Ended: {what}.",
        "confirm_restart": "Restart the service {unit}? Say yes or no.",
        "done": "Done: {what}.",
        "quiet_off": "Talking again.",
        "scheduled": "Scheduled ({cron}): {what}. Next: {next}.",
        "schedule_bad": "I can't set up that schedule: {error}",
    },
}


def _normalise(text: str) -> str:
    return re.sub(r"[^\w\s]", "", strip_address(text.lower())).strip()


@dataclass
class Response:
    intent: Intent
    text: str
    report: TaskReport | None = None


class Assistant:
    """Interprets and carries out requests.

    A request for a plan only *prepares* it and asks; the plan runs when the
    next request is a yes ("tak", "uruchom", "yes"...), the same on every channel.
    """

    def __init__(
        self, dia: Orchestrator, brains: list[Brain] | None = None, language: str | None = None
    ) -> None:
        self.dia = dia
        self._fixed_brains = brains
        self._language = language
        self._conversation = "default"  # who is talking now (see dia.conversations)
        self.surface = "desktop"  # the channel's default; see BrainContext.surface
        # An action waiting for "yes": (what it is, what to do).
        self.pending_action: tuple[str, Callable[[], Awaitable[str]]] | None = None
        self._config = None
        self._turns = 0  # for [assistant] learn_every
        self._refresh()

    @property
    def pending_plan(self) -> str | None:
        """The plan waiting for a "yes" in the current conversation (shared by every
        channel the owner uses: dia.conversations)."""
        return self.dia.conversations.pending_plan(self._conversation)

    @pending_plan.setter
    def pending_plan(self, plan_id: str | None) -> None:
        self.dia.conversations.set_pending_plan(self._conversation, plan_id)

    def _refresh(self) -> None:
        """Follow configuration changes (settings saved in the UI)."""
        if self._config is self.dia.config:
            return
        self._config = config = self.dia.config
        self.brains = self._fixed_brains if self._fixed_brains is not None else config.brain_chain()
        language = self._language or config.language
        self.phrases = PLAN_PHRASES.get(language, PLAN_PHRASES["en"])
        self.skills: dict[str, Skill] = enabled_skills(self.dia)

    def context(self, conversation: str = "default", surface: str = "desktop") -> BrainContext:
        config = self.dia.config
        return BrainContext(
            projects={name: str(p.path) for name, p in config.projects.items()},
            agents=list(config.agents),
            default_agent=config.default_agent,
            recent_tasks=[
                f"{t.id} [{t.status}] {t.project}: {t.prompt.splitlines()[0][:80]}"
                for t in self.dia.store.recent(5)
            ],
            skills={name: skill.describe() for name, skill in self.skills.items()},
            persona=persona_prompt(config),
            history=self.dia.conversations.history(conversation),
            surface=surface,
        )

    def remember_turn(self, conversation: str, text: str, reply: str) -> None:
        if not text or not reply:
            return
        history = self.dia.conversations.add_turn(conversation, text, reply)
        options = self.dia.config.assistant
        self._turns += 1
        if (
            options.get("learn_preferences")
            and self._turns % int(options.get("learn_every", 10)) == 0
        ):
            from dia.preferences import learn_preferences

            self.dia.spawn(learn_preferences(self.dia, list(history)))

    async def interpret(
        self, text: str, conversation: str = "default", surface: str | None = None
    ) -> Intent:
        self._refresh()
        self._conversation = conversation
        self._surface_now = surface or self.surface
        self.dia.conversations.add_message(conversation, "me", text)
        if self.pending_plan or self.pending_action:
            answer = _normalise(text)
            if _YES.match(answer):
                return Intent("confirm", brain="plan", text=text, conversation=conversation)
            if _NO.match(answer):
                return Intent("cancel", brain="plan", text=text, conversation=conversation)
            # anything else: a new request, what waited for an answer is dropped
            self.pending_plan = self.pending_action = None
        ctx = self.context(conversation, surface or self.surface)
        problems = []
        for brain in self.brains:
            try:
                intent = await brain.interpret(text, ctx)
            except Exception as exc:  # next brain in the chain takes over
                log.warning("brain %s failed: %s", brain.name, exc)
                problems.append(f"{brain.name}: {exc}")
                continue
            if intent:
                intent.brain = brain.name
                intent.text, intent.conversation = text, conversation
                self._log_intent(intent)
                return intent
        detail = "; ".join(problems) or "no brain configured"
        return Intent("chat", reply=f"Sorry, I could not understand that ({detail}).")

    def _log_intent(self, intent: Intent) -> None:
        """Kept so another brain can be tried on real requests later (dia brains
        --replay); ``[assistant] log_intents = false`` turns it off."""
        if not self.dia.config.assistant.get("log_intents", True):
            return
        try:
            self.dia.store.log_intent(
                intent.text,
                intent.action,
                intent.project,
                intent.skill,
                intent.brain,
                intent.conversation,
            )
        except Exception:
            log.exception("could not log the intent")

    async def execute(
        self,
        intent: Intent,
        on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
    ) -> Response:
        self._conversation = intent.conversation or self._conversation
        response = await self._execute(intent, on_start)
        self.remember_turn(intent.conversation, intent.text, response.text)
        chats = self.dia.conversations
        planned = intent.action in ("plan", "mission")
        plan = chats.pending_plan(intent.conversation) if planned else None
        task = response.report.task.id if response.report else None
        chats.add_message(intent.conversation, "dia", response.text, task=task, plan=plan)
        return response

    async def _execute(
        self,
        intent: Intent,
        on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
    ) -> Response:
        chats = self.dia.conversations  # the plan waiting is this conversation's own
        if intent.action in ("run", "ask"):
            mode = Mode.EDIT if intent.action == "run" else Mode.READ_ONLY
            report = await self.dia.run_task(
                intent.project, intent.prompt, intent.agent, mode, on_start=on_start
            )
            return Response(intent, report.task.summary or report.task.error or "", report)
        if intent.action in ("plan", "mission"):
            if intent.action == "mission":
                from dia.missions import Missions

                plan = await Missions(self.dia).create(intent.project, intent.prompt)
            else:
                plan = await self.dia.create_plan(intent.project, intent.prompt)
            chats.set_pending_plan(intent.conversation, plan.id)  # this conversation's
            steps = ", ".join(
                f"{i}. {s.get('title') or s['agent']} ({s['agent']})"
                for i, s in enumerate(plan.details["plan"], 1)
            )
            from dia.simulation import describe

            ask = self.phrases["ask"].format(project=plan.project, steps=steps)
            plan = self.dia.store.get(plan.id) or plan
            spoken = getattr(self, "_surface_now", self.surface) == "voice"
            if not spoken and (sim := describe(plan.details.get("simulation"))):
                ask = f"{ask}\n{sim}"  # too long to read out; the app shows it
            return Response(intent, ask)
        if intent.action == "confirm" and self.pending_action:
            (_, action), self.pending_action = self.pending_action, None
            try:
                return Response(intent, await action())
            except Exception as exc:
                return Response(intent, str(exc))
        if intent.action == "confirm":
            plan_id = chats.pending_plan(intent.conversation)
            chats.set_pending_plan(intent.conversation, None)
            report = await self.dia.run_plan(plan_id, on_start=on_start)
            return Response(intent, report.task.summary or report.task.error or "", report)
        if intent.action == "cancel":
            phrase = "action_cancelled" if self.pending_action else "cancelled"
            if plan_id := chats.pending_plan(intent.conversation):
                chats.set_pending_plan(intent.conversation, None)
                self.pending_action = None
                try:
                    await self.dia.discard_task(plan_id)  # a rejected plan: a decision
                except TaskActionError:
                    pass
            self.pending_action = None
            return Response(intent, self.phrases[phrase])
        if intent.action == "launch":
            try:
                message = await self.dia.launch(intent.project)
            except TaskActionError as exc:
                message = str(exc)
            return Response(intent, intent.reply or message)
        if intent.action == "skill":
            return Response(intent, await self.run_skill(intent.skill or "", intent.args))
        if intent.action == "council":
            from dia.council import convene

            task = await convene(self.dia, intent.prompt or intent.text, intent.project)
            return Response(intent, task.summary or task.error or task.status)
        if intent.action == "build":
            from dia.release import Releases

            preset = intent.args.get("preset")
            task = await Releases(self.dia).build(
                intent.project,
                [preset] if preset else None,
                version=intent.args.get("version"),
                write_changelog=True,
            )
            return Response(intent, task.summary or task.error or task.status)
        if intent.action == "howto":
            return Response(intent, await self._propose_howto())
        if intent.action == "prefer":
            from dia.persona import add_preference

            text = add_preference(self.dia, str(intent.args.get("text") or intent.text))
            return Response(intent, self.phrases["prefer_saved"].format(text=text))
        if intent.action == "camera_access":
            on = bool(intent.args.get("on", True))
            self.dia.set_camera(on)
            return Response(intent, self.phrases["camera_on" if on else "camera_off"])
        if intent.action == "research":
            from dia.research import research

            task = await research(
                self.dia, intent.prompt or intent.text, intent.project, on_start=on_start
            )
            return Response(intent, task.summary or task.error or task.status, TaskReport(task))
        if intent.action == "work":
            from dia import work

            args = intent.args
            try:
                if args.get("action") == "stop":
                    text = await work.stop(self.dia, args.get("profile"), args.get("note", ""))
                else:
                    text = await work.start(self.dia, args.get("profile") or intent.project or "")
            except ValueError as exc:
                text = str(exc)
            return Response(intent, text)
        if intent.action == "goal":
            from dia import goals

            weeks = intent.args.get("weeks")
            weeks = int(weeks) if str(weeks or "").isdigit() else None
            goal = await goals.create(self.dia, intent.project, intent.prompt or intent.text, weeks)
            return Response(intent, goals.describe(goal))
        if intent.action == "debug":
            from dia.swarm import debug

            bug = intent.prompt or intent.text
            task = await debug(self.dia, intent.project, bug, None, on_start)
            return Response(intent, task.summary or task.error or task.status, TaskReport(task))
        if intent.action == "impact":
            from dia.impact import impact

            target = str(intent.args.get("target") or intent.prompt or "").strip()
            _, text = await impact(self.dia, intent.project, target)
            return Response(intent, text)
        if intent.action == "check_notes":
            from dia.contradictions import check

            task = await check(self.dia, intent.project, on_start=on_start)
            return Response(intent, task.summary or task.error or task.status, TaskReport(task))
        if intent.action == "why":
            from dia.decisions import describe, why

            found = await why(self.dia, intent.prompt or intent.text, intent.project)
            return Response(intent, describe(found))
        if intent.action == "experiment":
            from dia.experiments import run_experiment

            def names(key: str) -> list[str] | None:
                value = intent.args.get(key)
                return [str(v) for v in value] if isinstance(value, list) and value else None

            agents = [a for a in names("agents") or [] if a in self.dia.config.agents] or None
            task = await run_experiment(
                self.dia,
                intent.project,
                intent.prompt or intent.text,
                agents,
                names("approaches"),
                on_start,
            )
            return Response(intent, task.summary or task.error or task.status, TaskReport(task))
        if intent.action == "scenario":
            from dia.scenario import check_scenario

            report = await check_scenario(
                self.dia, intent.project, intent.prompt or intent.text, on_start=on_start
            )
            return Response(intent, report.task.summary or report.task.error or "", report)
        if intent.action == "screen_access":
            on = bool(intent.args.get("on", True))
            self.dia.set_screen(on)
            return Response(intent, self.phrases["screen_on" if on else "screen_off"])
        if intent.action == "process":
            return Response(intent, self._propose_end(intent))
        if intent.action == "service":
            unit = str(intent.args.get("unit", "")).strip()
            return Response(
                intent,
                self._propose(
                    self.phrases["confirm_restart"].format(unit=unit),
                    lambda: self._restart(unit),
                ),
            )
        if intent.action == "quiet":
            on = bool(intent.args.get("on", True))
            self.dia.set_quiet(on)
            return Response(intent, self.phrases["quiet_on" if on else "quiet_off"])
        if intent.action == "stop":
            stopped = await self.dia.stop_all("asked")
            return Response(intent, self.phrases["stopped"].format(count=len(stopped)))
        if intent.action == "resume":
            await self.dia.resume()
            return Response(intent, self.phrases["resumed"])
        if intent.action == "schedule":
            return Response(intent, self.add_schedule(intent.cron or "", intent.prompt or ""))
        if intent.action == "status":
            return Response(intent, await self.status_text())
        if intent.action == "tasks":
            return Response(intent, self.tasks_text())
        return Response(intent, intent.reply)

    async def handle(self, text: str, conversation: str = "default") -> Response:
        return await self.execute(await self.interpret(text, conversation))

    def add_schedule(self, cron: str, text: str) -> str:
        from dia.schedule import Cron, Schedules

        try:
            job = Schedules(self.dia).add({"cron": cron, "action": "say", "text": text})
        except ValueError as exc:
            return self.phrases["schedule_bad"].format(error=exc)
        upcoming = Cron.parse(job.cron).next_after(datetime.now().astimezone())
        when = f"{upcoming:%Y-%m-%d %H:%M}" if upcoming else "-"
        return self.phrases["scheduled"].format(cron=job.cron, what=text, next=when)

    def _propose(self, question: str, action: Callable[[], Awaitable[str]]) -> str:
        self.pending_plan = None
        self.pending_action = (question, action)
        return question

    def _propose_end(self, intent: Intent) -> str:
        from dia.system import find_processes

        name = str(intent.args.get("name", "")).strip()
        force = str(intent.args.get("force", "")).lower() in ("true", "1", "yes")
        found = find_processes(name) if name else []
        if not found:
            return self.phrases["no_process"].format(name=name)
        what = ", ".join(f"{pname} ({pid})" for pid, pname, _ in found[:5])
        if len(found) > 5:
            return self.phrases["too_many"].format(count=len(found), what=what)

        async def end() -> str:
            from dia.computer import end_process

            for pid, _, command in found:
                end_process(pid, force)
                self.dia.audit("process.end", str(pid), command)
            return self.phrases["ended"].format(what=what)

        return self._propose(self.phrases["confirm_end"].format(what=what), end)

    async def _propose_howto(self) -> str:
        done = next(
            (
                t
                for t in self.dia.store.recent(30)
                if t.mode == "edit" and t.status in ("done", "merged", "published")
            ),
            None,
        )
        if not done:
            return self.phrases["howto_none"]
        try:
            howto = await self.dia.propose_howto(done.id)
        except TaskActionError as exc:
            return str(exc)

        async def save() -> str:
            return self.phrases["howto_saved"].format(path=self.dia.accept_howto(done.id))

        first = howto["steps"].strip().splitlines()[0][:160]
        return self._propose(
            self.phrases["howto_ask"].format(title=howto["title"], steps=first), save
        )

    async def _restart(self, unit: str) -> str:
        from dia.computer import restart_user_unit

        await restart_user_unit(unit)
        self.dia.audit("service.restart", unit)
        return self.phrases["done"].format(what=f"restart {unit}")

    async def run_skill(self, name: str, args: dict | None = None) -> str:
        self._refresh()
        skill = self.skills.get(name)
        if not skill:
            return self.phrases["skill_failed"].format(skill=name, error="unknown skill")
        try:
            return await skill.run(args or {})
        except NeedsConfirmation as ask:
            return self._propose(ask.question, ask.action)
        except Exception as exc:
            log.warning("skill %s failed: %s", name, exc)
            return self.phrases["skill_failed"].format(skill=name, error=exc)

    async def status_text(self) -> str:
        """Short status in the assistant's language (it may be read aloud)."""
        config, t = self.dia.config, self.phrases
        ready, problems = [], []
        for name in config.agents:
            try:
                issue = await config.agent(name).check()
            except Exception as exc:
                issue = str(exc)
            if issue:
                problems.append(t["agent_problem"].format(agent=name, problem=issue))
            else:
                ready.append(name)
        lines = []
        if ready:
            lines.append(t["agents_ready"].format(agents=", ".join(ready)))
        lines += problems
        for name, until in self.dia.limit_status().items():
            time = datetime.fromisoformat(until).astimezone().strftime("%H:%M")
            lines.append(t["limited"].format(agent=name, time=time))
        active = [
            x for x in self.dia.store.recent(50) if x.status in ("queued", "running", "waiting")
        ]
        if not active:
            lines.append(t["no_active"])
        else:
            lines.append(t["active"].format(count=len(active)))
            lines += [f"{x.project}: {x.prompt.splitlines()[0][:60]} ({x.status})" for x in active]
        return "\n".join(lines)

    def tasks_text(self, limit: int = 10) -> str:
        tasks = self.dia.store.recent(limit)
        lines = [
            f"{x.project}: {x.prompt.splitlines()[0][:60]} ({x.status}, {x.id})" for x in tasks
        ]
        return "\n".join(lines) or self.phrases["no_tasks"]
