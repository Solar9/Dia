"""`dia agents` commands."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from dia.core import plugins
from dia.core.config import Config, ConfigError
from dia.core.orchestrator import Orchestrator
from dia.core.workspace import uncommitted_files


async def cmd_doctor(config: Config, args: argparse.Namespace) -> int:
    print(f"config:   {config.source}")
    for other in config.shadowed:
        print(f"          note: {other} exists too but is NOT used (this one wins)")
    print(f"data dir: {config.data_dir}")
    problems = 0
    try:
        memory = config.memory()
        issue = memory.check() if memory else None
        status = "off" if not memory else (memory.describe() if not issue else "PROBLEM: " + issue)
    except Exception as exc:
        issue = status = f"PROBLEM: {exc}"
    problems += bool(issue)
    print(f"memory:   {status}")
    try:
        for brain in config.brain_chain():
            issue = brain.check()
            problems += bool(issue)
            state = brain.describe() if not issue else "PROBLEM: " + issue
            print(f"brain   {brain.name:<16} {state}")
    except ConfigError as exc:
        problems += 1
        print(f"brain   PROBLEM: {exc}")
    for name in config.channels:
        try:
            issue = config.channel(name, Orchestrator(config, use_memory=False)).check()
        except ConfigError as exc:
            issue = str(exc)
        problems += bool(issue)
        print(f"channel {name:<16} {'ok' if not issue else 'PROBLEM: ' + issue}")
    for name in config.agents:
        where = ""
        try:
            agent = config.agent(name)
            issue = await agent.check()
            where = getattr(agent, "command", "")
        except Exception as exc:
            issue = str(exc)
        problems += bool(issue)
        status = f"ok  {where}" if not issue else "PROBLEM: " + issue
        print(f"agent   {name:<16} {status}")
    for project in config.projects.values():
        if not project.path.is_dir():
            issue = f"path does not exist: {project.path}"
        elif not (project.path / ".git").exists():
            issue = f"not a git repository: {project.path}"
        else:
            issue = None
        toolchain = None
        if not issue:
            toolchain = Orchestrator(config, use_memory=False).toolchain_for(project)
            issue = toolchain.check() if toolchain else None
        problems += bool(issue)
        kind = f"  ({toolchain.describe()})" if toolchain and not issue else ""
        print(f"project {project.name:<16} {'ok' + kind if not issue else 'PROBLEM: ' + issue}")
        if not issue and (dirty := await uncommitted_files(project.path)):
            print(f"        {'':<16} note: {len(dirty)} uncommitted file(s); agents won't see them")
    if getattr(args, "fix", False):
        from dia.desktop.health import fix

        done, left = await fix(Orchestrator(config))
        for line in done:
            print(f"fixed:   {line}")
        for line in left:
            print(f"cannot fix: {line}")
        if not done and not left:
            print("fix:     nothing to repair")
        problems += len(left)
    return 1 if problems else 0


async def cmd_agents(config: Config, args: argparse.Namespace) -> int:
    print("installed agent plugins:")
    for kind, target in sorted(plugins.available("dia.agents").items()):
        print(f"  {kind:<14} {target}")
    print("configured agents:")
    for name, opts in config.agents.items():
        default = " (default)" if name == config.default_agent else ""
        print(f"  {name:<14} type={opts.get('type', name)}{default}")
    return 0


async def cmd_limits(config: Config, args: argparse.Namespace) -> int:
    orchestrator = Orchestrator(config, use_memory=False)
    if args.clear:
        orchestrator.limits.clear(None if args.clear == "all" else args.clear)
    limited = orchestrator.limit_status()
    for name in config.agents:
        state = "available"
        if until := limited.get(name):
            state = f"limit until {datetime.fromisoformat(until).astimezone():%Y-%m-%d %H:%M}"
        print(f"  {name:<14} {state}")
    return 0


async def cmd_usage(config: Config, args: argparse.Namespace) -> int:
    data = Orchestrator(config, use_memory=False).store.usage(args.days)
    print(f"last {args.days} days")
    for a in data["agents"]:
        rate = f"{100 * a['ok'] / a['calls']:.0f}%" if a["calls"] else "-"
        print(
            f"  {a['agent']:<14} {a['calls']:>4} calls  {rate:>4} ok  {a['minutes']:>7} min"
            f"  limits hit: {a['limited']}"
        )
    if not data["agents"]:
        print("  no agent calls yet")
    for p in data["projects"]:
        print(f"  {p['project']:<14} {p['tasks']:>4} tasks  {p['done']} done  {p['failed']} failed")
    from dia.core.config import save_settings
    from dia.quality.agent_stats import agent_stats, suggestions

    stats = agent_stats(Orchestrator(config, use_memory=False).store, max(args.days, 30))
    if stats:
        print("\nhow agents do (edit tasks they authored):")
    for r in stats:
        tests = f"{r['tests']:.0%}" if r["tests"] is not None else "-"
        print(
            f"  {r['project']:<12} {r['agent']:<10} {r['tasks']:>3} tasks  "
            f"{r['success']:.0%} done  tests {tests}  {r['minutes']} min/task  "
            f"quality {r['quality']:.0%}"
        )
    proposals = suggestions(config, stats)
    for s in proposals:
        change = f"default agent {s['current']} -> {s['agent']}"
        print(f"\nproposal: {s['project']}: {change} ({s['reason']})")
        print(f"  apply: dia usage --apply {s['project']} {s['agent']}")
    if args.apply:
        project, agent = args.apply
        if not any((s["project"], s["agent"]) == (project, agent) for s in proposals):
            print("error: that is not a current proposal", file=sys.stderr)
            return 1
        save_settings(config, {"projects": {project: {"default_agent": agent}}})
        print(f"{project}: default agent is now {agent}")
    return 0


async def cmd_brains(config: Config, args: argparse.Namespace) -> int:
    """The brain chain, each brain's state, and (with --test) what each one makes of a
    message and how long it takes: handy to tune a local model."""
    import time

    from dia.assistant import Assistant

    dia = Orchestrator(config, use_memory=False)
    assistant = Assistant(dia, brains=[])
    ctx = assistant.context()
    if args.replay:
        from dia.quality.shadow import describe_difference, replay

        chain = [b for b in config.brain_chain() if not args.brain or b.name == args.brain]
        if not chain:
            print(f"error: no brain named {args.brain!r}", file=sys.stderr)
            return 1
        for brain in chain:
            if problem := brain.check():
                print(f"{brain.name}: {problem}")
                continue
            result = await replay(brain, dia.store, ctx, args.replay)
            if not result["requests"]:
                print(f"{brain.name}: no logged requests from other brains to replay")
                continue
            print(
                f"{brain.name}: agrees on {result['agreed']}/{result['requests']} "
                f"({result['agreement']:.0%}); same action {result['same_action']}, "
                f"errors {result['errors']}"
            )
            for row in result["differences"][:20]:
                print(f"  {describe_difference(row)}")
        return 0
    for brain in config.brain_chain():
        problem = brain.check()
        print(f"{brain.name:<16} {brain.describe():<40} {'ok' if not problem else problem}")
        if not args.test or problem:
            continue
        started = time.monotonic()
        try:
            intent = await brain.interpret(args.test, ctx)
        except Exception as exc:
            print(f"    error: {exc}")
            continue
        took = time.monotonic() - started
        if intent is None:
            print(f"    ({took:.1f}s) passes to the next brain")
            continue
        extra = {k: v for k in ("project", "skill", "cron") if (v := getattr(intent, k))}
        print(f"    ({took:.1f}s) {intent.action} {extra or ''} {intent.args or ''}".rstrip())
        if intent.reply:
            print(f"    reply: {intent.reply}")
        if intent.prompt and intent.action in ("run", "ask", "plan"):
            print(f"    prompt: {intent.prompt}")
    return 0


async def cmd_council(config: Config, args: argparse.Namespace) -> int:
    """Several agents answer; a moderator weighs their answers."""
    from dia.knowledge.council import convene

    project = args.project if args.question else None
    question = args.question or args.project
    print("the council is meeting (one call per member, plus the moderator) ...", file=sys.stderr)
    task = await convene(Orchestrator(config), question, project, args.member or None)
    for answer in task.details.get("council", []):
        print(f"\n## {answer['agent']}\n{answer['answer']}")
    print(f"\n## {task.details.get('moderator', 'moderator')}\n{task.summary or task.error}")
    return 0 if task.status == "done" else 1


async def cmd_research(config: Config, args: argparse.Namespace) -> int:
    """A web research report, kept as a task and (with memory) a note."""
    from dia.knowledge.research import research

    project = args.project if args.topic else None
    topic = args.topic or args.project
    print("researching (this can take several minutes) ...", file=sys.stderr)
    task = await research(Orchestrator(config), topic, project, args.agent)
    print(task.summary or task.error)
    if note := task.details.get("note"):
        print(f"\nsaved as {note}", file=sys.stderr)
    return 0 if task.status == "done" else 1


async def cmd_scenario(config: Config, args: argparse.Namespace) -> int:
    """Does it work? An agent writes a test for the scenario; Dia runs it."""
    from dia.quality.scenario import check_scenario

    print("writing and running a test for it ...", file=sys.stderr)
    report = await check_scenario(Orchestrator(config), args.project, args.scenario, args.agent)
    print(report.task.summary or report.task.error)
    return {"works": 0, "broken": 1}.get(report.task.details.get("scenario_result", ""), 2)


def add_doctor(sub: argparse._SubParsersAction) -> None:
    doctor = sub.add_parser("doctor", help="check config, agents and projects")
    doctor.add_argument("--fix", action="store_true", help="repair what is safe to repair")
    doctor.set_defaults(fn=cmd_doctor)


def add_agents(sub: argparse._SubParsersAction) -> None:
    sub.add_parser("agents", help="list agent plugins and configured agents").set_defaults(
        fn=cmd_agents
    )


def add_usage(sub: argparse._SubParsersAction) -> None:
    usage = sub.add_parser("usage", help="how much each agent was used, and how well it does")
    usage.add_argument("--days", type=int, default=30)
    usage.add_argument(
        "--apply",
        nargs=2,
        metavar=("PROJECT", "AGENT"),
        help="make a proposed agent the project's default",
    )
    usage.set_defaults(fn=cmd_usage)


def add_brains(sub: argparse._SubParsersAction) -> None:
    brains = sub.add_parser("brains", help="the brain chain; --test compares the brains")
    brains.add_argument("--test", metavar="MESSAGE", help="what each brain makes of it")
    brains.add_argument(
        "--replay",
        type=int,
        nargs="?",
        const=50,
        metavar="N",
        help="give the last N real requests to a brain; how often does it agree?",
    )
    brains.add_argument("--brain", help="only this brain (with --replay)")
    brains.set_defaults(fn=cmd_brains)


def add_council(sub: argparse._SubParsersAction) -> None:
    council = sub.add_parser("council", help="several agents answer, a moderator weighs them")
    council.add_argument("project", help="a project, or the question")
    council.add_argument("question", nargs="?")
    council.add_argument("--member", action="append", help="agents to ask (repeatable)")
    council.set_defaults(fn=cmd_council)


def add_research(sub: argparse._SubParsersAction) -> None:
    res = sub.add_parser("research", help="a web research report (with sources)")
    res.add_argument("project", help="a project, or the topic")
    res.add_argument("topic", nargs="?")
    res.add_argument("-a", "--agent", help="an agent with web access")
    res.set_defaults(fn=cmd_research)


def add_scenario(sub: argparse._SubParsersAction) -> None:
    scenario = sub.add_parser("scenario", help="does it work? a test is written and run")
    scenario.add_argument("project")
    scenario.add_argument("scenario", help='e.g. "parrying an attack in the last 0.2 s"')
    scenario.add_argument("-a", "--agent", help="who writes the test")
    scenario.set_defaults(fn=cmd_scenario)


def add_limits(sub: argparse._SubParsersAction) -> None:
    limits = sub.add_parser("limits", help="agents that are out of their usage limit")
    limits.add_argument("--clear", metavar="AGENT", help="forget an agent's limit ('all': every)")
    limits.set_defaults(fn=cmd_limits)


COMMANDS = {
    "doctor": add_doctor,
    "agents": add_agents,
    "usage": add_usage,
    "brains": add_brains,
    "council": add_council,
    "research": add_research,
    "scenario": add_scenario,
    "limits": add_limits,
}
