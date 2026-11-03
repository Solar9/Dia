"""The assistant's action table, one direct test per action (DIA-36).

Each action hands the intent's fields to one function elsewhere in Dia. The functions are
replaced by recorders, so these tests pin what the assistant passes on and what it says back,
without agents, a network or a model."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from dia.assistant import Assistant, Response
from dia.brains import ACTIONS, Intent
from dia.core.config import parse_config
from dia.core.orchestrator import Orchestrator, TaskActionError, TaskReport
from dia.core.store import TaskRecord
from dia.skills import NeedsConfirmation


def make(tmp_path: Path, repo: Path, language: str = "en") -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a", "language": language},
        "agents": {
            "a": {"type": "command", "argv": ["echo", "a did it"]},
            "b": {"type": "command", "argv": ["echo", "b did it"]},
        },
        "projects": {"demo": {"path": str(repo)}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


@pytest.fixture
def assistant(tmp_path: Path, repo: Path) -> Assistant:
    return Assistant(make(tmp_path, repo), [])


def task(summary: str = "the summary", status: str = "done", **kw) -> TaskRecord:
    return TaskRecord(
        id="t1", project="demo", agent="a", mode="read-only", prompt="p", status=status,
        summary=summary, **kw,
    )  # fmt: skip


def recorder(result, calls: list):
    async def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    return fake


def test_the_action_table_covers_every_action_a_brain_can_return() -> None:
    # "chat" is the one action with nothing to do: its reply is the answer
    assert set(Assistant.ACTIONS) | {"chat"} == set(ACTIONS) | {"cancel", "confirm"}
    for method in Assistant.ACTIONS.values():
        assert callable(getattr(Assistant, method)), method


async def test_chat_just_says_its_reply(assistant: Assistant) -> None:
    answer = await assistant.execute(Intent("chat", reply="Hello there", conversation="c"))
    assert answer.text == "Hello there" and answer.report is None


# ---- the actions that start work or look something up ---------------------------------------


async def test_council_asks_the_question_and_says_the_summary(assistant, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr("dia.knowledge.council.convene", recorder(task("They agree."), calls))
    answer = await assistant.execute(Intent("council", prompt="ECS or not?", project="demo"))
    assert answer.text == "They agree."
    assert calls[0][0][1:] == ("ECS or not?", "demo")


async def test_council_falls_back_to_the_users_words_and_to_the_error(assistant, monkeypatch):
    calls: list = []
    failed = task("", status="failed", error="no agents")
    failed.summary = None
    monkeypatch.setattr("dia.knowledge.council.convene", recorder(failed, calls))
    answer = await assistant.execute(Intent("council", text="what do you all think?"))
    assert answer.text == "no agents" and calls[0][0][1] == "what do you all think?"


async def test_build_passes_the_preset_and_version(assistant, monkeypatch) -> None:
    calls: list = []

    class FakeReleases:
        def __init__(self, dia) -> None:
            pass

        build = staticmethod(recorder(task("Built 0.2."), calls))

    monkeypatch.setattr("dia.release.release.Releases", FakeReleases)
    intent = Intent("build", project="demo", args={"preset": "linux", "version": "0.2"})
    assert (await assistant.execute(intent)).text == "Built 0.2."
    assert calls[0][0] == ("demo", ["linux"])
    assert calls[0][1] == {"version": "0.2", "write_changelog": True}
    calls.clear()
    await assistant.execute(Intent("build", project="demo"))
    assert calls[0][0] == ("demo", None)  # no preset: every preset


@pytest.mark.parametrize(
    ("action", "target"),
    [
        ("research", "dia.knowledge.research.research"),
        ("debug", "dia.work.swarm.debug"),
        ("check_notes", "dia.quality.contradictions.check"),
        ("experiment", "dia.quality.experiments.run_experiment"),
    ],
)
async def test_actions_that_run_a_task_report_it_and_pass_on_the_start_hook(
    assistant, monkeypatch, action, target
) -> None:
    calls: list = []
    monkeypatch.setattr(target, recorder(task("Done: " + action), calls))
    started = []

    async def on_start(t):
        started.append(t)

    answer = await assistant.execute(
        Intent(action, prompt="the thing", project="demo"), on_start=on_start
    )
    assert answer.text == "Done: " + action
    assert isinstance(answer.report, TaskReport) and answer.report.task.id == "t1"
    args, kwargs = calls[0]
    assert on_start in args or kwargs.get("on_start") is on_start  # the channel hears of it


async def test_experiment_keeps_only_configured_agents_and_named_approaches(
    assistant, monkeypatch
) -> None:
    calls: list = []
    monkeypatch.setattr("dia.quality.experiments.run_experiment", recorder(task(), calls))
    args = {"agents": ["a", "ghost", "b"], "approaches": ["ECS", "classic"]}
    await assistant.execute(Intent("experiment", prompt="inventory", project="demo", args=args))
    _, _, prompt, agents, approaches, _ = calls[0][0][:6]
    assert (prompt, agents, approaches) == ("inventory", ["a", "b"], ["ECS", "classic"])
    calls.clear()
    await assistant.execute(Intent("experiment", prompt="x", project="demo", args={"agents": []}))
    assert calls[0][0][3] is None and calls[0][0][4] is None  # defaults: every agent, one way


async def test_scenario_reports_the_checks_task(assistant, monkeypatch) -> None:
    calls: list = []
    report = TaskReport(task("It works."))
    monkeypatch.setattr("dia.quality.scenario.check_scenario", recorder(report, calls))
    answer = await assistant.execute(Intent("scenario", prompt="does parry work?", project="demo"))
    assert answer.text == "It works." and answer.report is report
    assert calls[0][0][1:] == ("demo", "does parry work?")


async def test_work_starts_and_stops_a_session(assistant, monkeypatch) -> None:
    started, stopped = [], []

    async def start(dia, profile):
        started.append(profile)
        return f"Started {profile}"

    async def stop(dia, profile, note):
        stopped.append((profile, note))
        return "Stopped"

    monkeypatch.setattr("dia.work.work.start", start)
    monkeypatch.setattr("dia.work.work.stop", stop)
    begin = Intent("work", project="demo", args={"action": "start", "profile": "starfall"})
    assert (await assistant.execute(begin)).text == "Started starfall"
    assert (await assistant.execute(Intent("work", project="demo"))).text == "Started demo"
    end = Intent("work", args={"action": "stop", "profile": "starfall", "note": "left at dash"})
    assert (await assistant.execute(end)).text == "Stopped"
    assert started == ["starfall", "demo"] and stopped == [("starfall", "left at dash")]

    async def refuse(dia, profile):
        raise ValueError("no such profile")

    monkeypatch.setattr("dia.work.work.start", refuse)
    assert (await assistant.execute(begin)).text == "no such profile"


async def test_goal_reads_the_weeks_only_when_they_are_a_number(assistant, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr("dia.work.goals.create", recorder("the goal", calls))
    monkeypatch.setattr("dia.work.goals.describe", lambda goal: f"Goal: {goal}")
    intent = Intent("goal", project="demo", prompt="Early Access", args={"weeks": "8"})
    assert (await assistant.execute(intent)).text == "Goal: the goal"
    assert calls[0][0][1:] == ("demo", "Early Access", 8)
    await assistant.execute(Intent("goal", project="demo", prompt="x", args={"weeks": "soon"}))
    assert calls[1][0][3] is None


async def test_impact_and_why_pass_the_question_on(assistant, monkeypatch) -> None:
    impact_calls, why_calls = [], []
    monkeypatch.setattr(
        "dia.quality.impact.impact", recorder((None, "dash touches 3 files"), impact_calls)
    )
    answer = await assistant.execute(Intent("impact", project="demo", args={"target": " dash "}))
    assert answer.text == "dash touches 3 files" and impact_calls[0][0][1:] == ("demo", "dash")
    monkeypatch.setattr("dia.knowledge.decisions.why", recorder(["found"], why_calls))
    monkeypatch.setattr("dia.knowledge.decisions.describe", lambda found: f"Why: {found}")
    answer = await assistant.execute(Intent("why", prompt="why drop ECS?", project="demo"))
    assert answer.text == "Why: ['found']" and why_calls[0][0][1:] == ("why drop ECS?", "demo")


async def test_prefer_remembers_the_preference(assistant, monkeypatch) -> None:
    saved = []
    monkeypatch.setattr("dia.persona.add_preference", lambda dia, text: saved.append(text) or text)
    answer = await assistant.execute(Intent("prefer", args={"text": "short answers"}))
    assert answer.text == "I'll remember: short answers." and saved == ["short answers"]
    await assistant.execute(Intent("prefer", text="no emoji"))
    assert saved[-1] == "no emoji"  # without args: the user's own words


# ---- switches --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "attribute", "on_phrase", "off_phrase"),
    [
        ("camera_access", "camera_enabled", "Camera on.", "Camera off."),
        ("screen_access", "screen_enabled", "Screen access on.", "I'm not looking"),
        ("quiet", "quiet", "Quiet mode: text answers only.", "Talking again."),
    ],
)
async def test_switches_flip_the_core_and_say_so(
    assistant, action, attribute, on_phrase, off_phrase
) -> None:
    on = await assistant.execute(Intent(action, args={"on": True}))
    assert on.text.startswith(on_phrase) and getattr(assistant.dia, attribute) is True
    off = await assistant.execute(Intent(action, args={"on": False}))
    assert off.text.startswith(off_phrase) and getattr(assistant.dia, attribute) is False
    assert (await assistant.execute(Intent(action))).text.startswith(on_phrase)  # default: on


async def test_stop_and_resume(assistant) -> None:
    stopped = await assistant.execute(Intent("stop"))
    assert stopped.text.startswith("Stopped 0 process(es).") and assistant.dia.halted
    assert (await assistant.execute(Intent("resume"))).text == "Back to work."
    assert not assistant.dia.halted


# ---- things that ask "yes?" first ------------------------------------------------------------


async def test_a_service_restart_waits_for_yes(assistant, monkeypatch) -> None:
    restarted = []

    async def restart(unit):
        restarted.append(unit)

    monkeypatch.setattr("dia.desktop.computer.restart_user_unit", restart)
    asked = await assistant.execute(Intent("service", args={"unit": " ollama.service "}))
    assert asked.text == "Restart the service ollama.service? Say yes or no."
    assert restarted == [] and assistant.pending_action is not None  # nothing happened yet
    done = await assistant.execute(Intent("confirm"))
    assert done.text == "Done: restart ollama.service." and restarted == ["ollama.service"]
    assert assistant.pending_action is None


async def test_a_failing_confirmed_action_says_why_instead_of_raising(assistant) -> None:
    async def fail() -> str:
        raise RuntimeError("it broke")

    assistant._propose("Sure?", fail)
    assert (await assistant.execute(Intent("confirm"))).text == "it broke"


async def test_saying_no_drops_what_waited(assistant) -> None:
    assistant._propose("Sure?", lambda: None)
    answer = await assistant.execute(Intent("cancel"))
    assert answer.text == "OK, I won't do that." and assistant.pending_action is None
    assert (await assistant.execute(Intent("cancel"))).text == "OK, the plan won't run."


async def test_cancelling_a_plan_discards_it_even_if_discarding_fails(
    assistant, monkeypatch
) -> None:
    discarded = []

    async def discard(plan_id):
        discarded.append(plan_id)
        raise TaskActionError("already gone")

    monkeypatch.setattr(assistant.dia, "discard_task", discard)
    assistant.dia.conversations.set_pending_plan("c", "plan-1")
    answer = await assistant.execute(Intent("cancel", conversation="c"))
    assert discarded == ["plan-1"] and answer.text == "OK, the plan won't run."
    assert assistant.dia.conversations.pending_plan("c") is None


async def test_yes_runs_the_waiting_plan(assistant, monkeypatch) -> None:
    ran = []

    async def run_plan(plan_id, on_start=None):
        ran.append(plan_id)
        return TaskReport(task("Plan done."))

    monkeypatch.setattr(assistant.dia, "run_plan", run_plan)
    assistant.dia.conversations.set_pending_plan("c", "plan-9")
    answer = await assistant.execute(Intent("confirm", conversation="c"))
    assert answer.text == "Plan done." and ran == ["plan-9"]
    assert assistant.dia.conversations.pending_plan("c") is None


async def test_ending_a_program_names_it_and_waits_for_yes(assistant, monkeypatch) -> None:
    ended, found = [], [(11, "godot", "godot --headless")]
    monkeypatch.setattr("dia.desktop.system.find_processes", lambda name: list(found))
    monkeypatch.setattr(
        "dia.desktop.computer.end_process", lambda pid, force: ended.append((pid, force))
    )
    asked = await assistant.execute(Intent("process", args={"name": "godot", "force": "true"}))
    assert asked.text == "End godot (11)? Say yes or no." and ended == []
    assert (await assistant.execute(Intent("confirm"))).text == "Ended: godot (11)."
    assert ended == [(11, True)]
    found.clear()
    missing = await assistant.execute(Intent("process", args={"name": "godot"}))
    assert missing.text == "I don't see a running program called “godot”."
    found.extend((n, f"p{n}", "cmd") for n in range(7))
    many = await assistant.execute(Intent("process", args={"name": "p"}))
    assert many.text.startswith("7 processes match:")
    assert assistant.pending_action is None  # too many to end blindly: nothing is proposed
    assert (await assistant.execute(Intent("process", args={}))).text.startswith("I don't see")


async def test_launch_says_what_happened(assistant, monkeypatch) -> None:
    async def launch(project):
        return f"Launched {project}"

    monkeypatch.setattr(assistant.dia, "launch", launch)
    assert (await assistant.execute(Intent("launch", project="demo"))).text == "Launched demo"
    assert (
        await assistant.execute(Intent("launch", project="demo", reply="Going."))
    ).text == "Going."

    async def broken(project):
        raise TaskActionError("no launch command")

    monkeypatch.setattr(assistant.dia, "launch", broken)
    assert (await assistant.execute(Intent("launch", project="demo"))).text == "no launch command"


# ---- how-tos, schedules, skills --------------------------------------------------------------


async def test_howto_has_nothing_to_write_down_without_a_finished_edit(assistant) -> None:
    assert (await assistant.execute(Intent("howto"))).text.startswith("I don't see a finished task")


async def test_howto_proposes_then_saves_on_yes(assistant, monkeypatch) -> None:
    assistant.dia.store.save(
        TaskRecord(id="e1", project="demo", agent="a", mode="edit", prompt="fix", status="done")
    )

    async def propose(task_id):
        return {"title": "Fixing saves", "steps": "1. Open the file\n2. Change it"}

    monkeypatch.setattr(assistant.dia, "propose_howto", propose)
    monkeypatch.setattr(assistant.dia, "accept_howto", lambda task_id: f"/notes/{task_id}.md")
    asked = await assistant.execute(Intent("howto"))
    assert asked.text.startswith("I wrote down “Fixing saves”: 1. Open the file")
    assert "Keep it as a how-to" in asked.text
    assert (
        await assistant.execute(Intent("confirm"))
    ).text == "Saved: /notes/e1.md. Agents will follow it on similar tasks."

    async def refuse(task_id):
        raise TaskActionError("nothing to learn")

    monkeypatch.setattr(assistant.dia, "propose_howto", refuse)
    assert (await assistant.execute(Intent("howto"))).text == "nothing to learn"


def test_a_schedule_is_added_with_its_next_run_or_refused(assistant) -> None:
    ok = assistant.add_schedule("30 7 * * 1-5", "briefing")
    assert ok.startswith("Scheduled (30 7 * * 1-5): briefing. Next: 20")
    bad = assistant.add_schedule("not a cron", "briefing")
    assert bad.startswith("I can't set up that schedule:")


async def test_skills_run_ask_or_fail_politely(assistant) -> None:
    class Weather:
        description = "weather"

        async def run(self, args):
            return f"Sunny in {args.get('place', '?')}"

    class Risky:
        async def run(self, args):
            async def go() -> str:
                return "done it"

            raise NeedsConfirmation("Really?", go)

    class Broken:
        async def run(self, args):
            raise RuntimeError("API down")

    assistant.skills = {"weather": Weather(), "risky": Risky(), "broken": Broken()}
    sunny = await assistant.execute(Intent("skill", skill="weather", args={"place": "Gdańsk"}))
    assert sunny.text == "Sunny in Gdańsk"
    assert (await assistant.execute(Intent("skill", skill="risky"))).text == "Really?"
    assert (await assistant.execute(Intent("confirm"))).text == "done it"
    broken = await assistant.execute(Intent("skill", skill="broken"))
    assert broken.text == "That didn't work (broken): API down"
    unknown = await assistant.execute(Intent("skill", skill="nope"))
    assert "unknown skill" in unknown.text


# ---- status and plans ------------------------------------------------------------------------


async def test_status_reports_agent_problems_limits_and_running_tasks(
    assistant, monkeypatch
) -> None:
    class Broken:
        async def check(self):
            return "not logged in"

    class Fine:
        async def check(self):
            return None

    agents = {"a": Fine(), "b": Broken()}
    monkeypatch.setattr(assistant.dia.config, "agent", lambda name, project=None: agents[name])
    monkeypatch.setattr(assistant.dia, "limit_status", lambda: {"b": "2026-11-03T10:00:00+00:00"})
    running = TaskRecord(
        id="r1", project="demo", agent="a", mode="edit", prompt="fix saving\nmore", status="running"
    )
    assistant.dia.store.save(running)
    text = await assistant.status_text()
    assert "Agents ready: a." in text and "Agent b has a problem: not logged in" in text
    assert "b is out of its usage limit until" in text
    assert "Running tasks: 1." in text and "demo: fix saving (running)" in text


def test_the_task_list_is_short_or_says_there_are_none(assistant) -> None:
    assert assistant.tasks_text() == "No tasks yet."
    assistant.dia.store.save(
        TaskRecord(id="x1", project="demo", agent="a", mode="edit", prompt="do\nit", status="done")
    )
    assert assistant.tasks_text() == "demo: do (done, x1)"


async def test_a_plan_is_prepared_and_asks_whether_to_run_it(assistant, monkeypatch) -> None:
    plan = TaskRecord(
        id="p1", project="demo", agent="a", mode="edit", prompt="co-op", status="planned",
        details={"plan": [{"agent": "a", "title": "Design"}, {"agent": "b", "title": "Build"}]},
    )  # fmt: skip
    assistant.dia.store.save(plan)

    async def create_plan(project, prompt):
        return plan

    monkeypatch.setattr(assistant.dia, "create_plan", create_plan)
    answer = await assistant.execute(
        Intent("plan", project="demo", prompt="co-op", conversation="c")
    )
    assert answer.text.startswith(
        "plan · demo\nPlan for demo: 1. Design (a), 2. Build (b). Run it?"
    )
    assert assistant.dia.conversations.pending_plan("c") == "p1"


async def test_a_mission_is_prepared_through_the_missions(assistant, monkeypatch) -> None:
    plan = TaskRecord(
        id="m1", project="demo", agent="a", mode="mission", prompt="ready", status="planned",
        details={"plan": [{"agent": "a", "title": "One"}]},
    )  # fmt: skip
    assistant.dia.store.save(plan)

    class FakeMissions:
        def __init__(self, dia) -> None:
            pass

        async def create(self, project, prompt):
            return plan

    monkeypatch.setattr("dia.work.missions.Missions", FakeMissions)
    answer = await assistant.execute(
        Intent("mission", project="demo", prompt="ready", conversation="c")
    )
    assert "Plan for demo: 1. One (a)." in answer.text
    assert assistant.dia.conversations.pending_plan("c") == "m1"


# ---- interpreting ----------------------------------------------------------------------------


async def test_without_any_brain_it_says_so(assistant) -> None:
    intent = await assistant.interpret("do something")
    assert intent.action == "chat" and "no brain configured" in intent.reply


async def test_a_failing_brain_is_reported_when_no_other_answers(tmp_path, repo) -> None:
    from dia.brains import Brain

    class Failing(Brain):
        kind = "failing"

        async def interpret(self, text, ctx):
            raise RuntimeError("model offline")

    orch = make(tmp_path, repo)
    intent = await Assistant(orch, [Failing("llm", {}, orch.config)]).interpret("hello")
    assert intent.action == "chat" and "llm: model offline" in intent.reply


async def test_a_reply_that_is_not_yes_or_no_drops_what_waited(assistant) -> None:
    assistant._propose("Sure?", lambda: None)
    assistant.dia.conversations.set_pending_plan("default", "p1")
    await assistant.interpret("something else entirely")
    assert assistant.pending_action is None and assistant.pending_plan is None


async def test_a_failure_to_log_the_intent_does_not_stop_the_request(
    assistant, monkeypatch
) -> None:
    from dia.brains import Brain

    class Quick(Brain):
        kind = "quick"

        async def interpret(self, text, ctx):
            return Intent("chat", reply="ok")

    def boom(*args):
        raise RuntimeError("disk full")

    monkeypatch.setattr(assistant.dia.store, "log_intent", boom)
    assistant.brains = [Quick("q", {}, assistant.dia.config)]
    assert (await assistant.interpret("hi")).reply == "ok"


def test_the_agent_for_an_intent_without_a_known_project_is_the_default(assistant) -> None:
    assert assistant.understood(Intent("run", project="ghost")) == "code change · ghost · a"
    assert Response(Intent("chat"), "x").report is None


@pytest.mark.parametrize(
    "action",
    ["run", "ask", "plan", "mission", "launch", "build", "experiment", "check_notes",
     "debug", "impact", "goal", "scenario"],
)  # fmt: skip
async def test_an_action_on_a_project_asks_which_one_when_there_is_none(
    assistant, monkeypatch, action
) -> None:
    # A model may answer project: null. The core must not be asked about "project None".
    for name in ("run_task", "create_plan", "launch"):
        monkeypatch.setattr(assistant.dia, name, AsyncMock(side_effect=AssertionError(name)))
    answer = await assistant.execute(Intent(action, prompt="the thing", text="the thing"))
    assert answer.text == "Which project is this about? (demo)"
    assert answer.report is None


async def test_the_question_is_in_the_assistants_language(tmp_path, repo) -> None:
    pl = Assistant(make(tmp_path, repo, "pl"), [])
    answer = await pl.execute(Intent("debug", prompt="crash"))
    assert answer.text == "Którego projektu to dotyczy? (demo)"


async def test_a_missing_prompt_falls_back_to_what_the_user_said(assistant, monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(assistant.dia, "run_task", recorder(TaskReport(task("ok")), calls))
    await assistant.execute(Intent("run", project="demo", prompt=None, text="fix the save"))
    assert calls[0][0][:2] == ("demo", "fix the save")
