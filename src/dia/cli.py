"""Terminal interface. Other interfaces (Discord, voice) will call the same core."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dia import __version__, plugins
from dia.agents import Mode
from dia.config import Config, ConfigError, load_config
from dia.orchestrator import Orchestrator, TaskActionError, TaskReport
from dia.store import TaskRecord
from dia.workspace import GitError, git, uncommitted_files


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
        from dia.health import fix

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


async def cmd_run(config: Config, args: argparse.Namespace) -> int:
    orchestrator = Orchestrator(config, use_memory=not args.no_memory)
    mode = Mode.READ_ONLY if args.read_only else Mode.EDIT
    print(f"running on '{args.project}' ({mode}) ...", file=sys.stderr)
    report = await orchestrator.run_task(
        args.project,
        args.prompt,
        agent_name=args.agent,
        mode=mode,
        run_tests=not args.no_tests,
        review=True if args.review else None,
    )
    print_report(report)
    await finish_learning(orchestrator, report.task.id)
    return 0 if report.task.status == "done" else 1


async def finish_learning(dia: Orchestrator, task_id: str) -> None:
    """Wait for the fact proposals of `[memory] learn` and show them."""
    if not dia.learning:
        return
    print("learning from the task ...", file=sys.stderr)
    await dia.drain()
    task = dia.store.get(task_id)
    if task and any(f["status"] == "proposed" for f in task.details.get("learn", [])):
        print_facts(task)


def print_facts(task: TaskRecord) -> None:
    print(f"\nworth remembering about {task.project} (task {task.id}):")
    for i, item in enumerate(task.details.get("learn", []), 1):
        if item["status"] == "proposed":
            print(f"  {i}. {item['fact']}")
    print(f"  accept: dia learned {task.id} --accept 1 2 ... | all; reject: --reject all")


async def cmd_howto(config: Config, args: argparse.Namespace) -> int:
    """List how-tos, or propose one from a finished task and keep it on --save."""
    dia = Orchestrator(config)
    if not dia.memory:
        print("error: memory is off ([memory] in the config)", file=sys.stderr)
        return 1
    if not args.task_id:
        for howto in dia.memory.howtos():
            where = ", ".join(howto["projects"]) or "all projects"
            print(f"{howto['title']}  ({where}; when: {howto['when'] or '-'})  {howto['path']}")
        return 0
    try:
        task = dia.store.get(args.task_id)
        proposal = task.details.get("howto") if task else None
        if not proposal or proposal.get("status") != "proposed":
            print("writing the how-to ...", file=sys.stderr)
            proposal = await dia.propose_howto(args.task_id)
        if not args.save:
            print(f"# {proposal['title']}\nwhen: {proposal['when']}\n\n{proposal['steps']}")
            print(f"\nkeep it: dia howto {args.task_id} --save", file=sys.stderr)
            return 0
        print(f"saved: {dia.accept_howto(args.task_id)}")
    except TaskActionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


async def cmd_learned(config: Config, args: argparse.Namespace) -> int:
    dia = Orchestrator(config)
    if not args.task_id:
        pending = dia.pending_facts()
        for task in pending:
            print_facts(task)
        if not pending:
            print("no proposed facts")
        return 0

    def indexes(values: list[str] | None) -> list[int] | None:
        if values is None:
            return None
        if values == ["all"]:
            task = dia.store.get(args.task_id)
            return list(range(len(task.details.get("learn", [])))) if task else []
        return [int(v) - 1 for v in values]

    try:
        stored = dia.decide_facts(args.task_id, indexes(args.accept), indexes(args.reject))
    except (TaskActionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for fact in stored:
        print(f"remembered: {fact}")
    return 0


async def cmd_check(config: Config, args: argparse.Namespace) -> int:
    dia = Orchestrator(config, use_memory=False)
    try:
        project = config.project(args.project)
        sha = await git(project.path, "rev-parse", "--verify", f"{args.ref}^{{commit}}")
    except (ConfigError, GitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    task = await dia.check_commit(project.name, sha)
    print(f"{task.id}  {task.status}  {task.prompt}")
    print(task.error or task.summary or "")
    if task.tests_ok is False:
        print(f"log: dia show {task.id} --tests · fix it: dia fix-build {task.id}")
    return 1 if task.status == "failed" else 0


async def cmd_fix_build(config: Config, args: argparse.Namespace) -> int:
    dia = Orchestrator(config)
    try:
        report = await dia.fix_build(args.task_id)
    except TaskActionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print_report(report)
    await finish_learning(dia, report.task.id)
    return 0 if report.task.status == "done" else 1


async def cmd_schedule(config: Config, args: argparse.Namespace) -> int:
    from dia.schedule import Scheduler, Schedules

    dia = Orchestrator(config)
    schedules = Schedules(dia)
    if args.action == "add":
        if not args.cron or not args.text:
            print('usage: dia schedule add "30 7 * * 1-5" "briefing"', file=sys.stderr)
            return 1
        data = {"cron": args.cron, "action": "say", "text": args.text, "speak": args.speak}
        if args.skill:
            data.update(action="skill", skill=args.text, text="")
        try:
            job = schedules.add(data)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"added {job.id}: {job.cron} {job.label()}")
        return 0
    if args.action == "rm":
        ok = bool(args.cron) and schedules.remove(args.cron)
        print("removed" if ok else f"no schedule {args.cron} (config jobs: edit the file)")
        return 0 if ok else 1
    if args.action == "run":
        job = next((j for j in schedules.list() if j.id == args.cron), None)
        if not job:
            print(f"no schedule {args.cron}", file=sys.stderr)
            return 1
        print(await Scheduler(dia).execute(job))
        return 0
    upcoming = schedules.next_runs()
    for job in schedules.list():
        when = (upcoming.get(job.id) or "-")[:16].replace("T", " ")
        off = "" if job.enabled else " (off)"
        print(f"  {job.id:<10} {job.cron:<16} next {when}  {job.action}: {job.label()}{off}")
    if not schedules.list():
        print('no schedules (dia schedule add "30 7 * * 1-5" "briefing")')
    return 0


async def cmd_issues(config: Config, args: argparse.Namespace) -> int:
    """Import open issues labelled for Dia as plans (what `[issues]` does in serve)."""
    from dia.issues import IssueWatcher

    dia = Orchestrator(config, use_memory=False)
    watcher = IssueWatcher(dia)
    if args.project:
        watcher.names = [args.project]
    count = await watcher.poll()
    for task in dia.store.recent(count):
        issue = task.details.get("issue", {})
        print(f"  {task.id}  {task.project}  #{issue.get('number')} {issue.get('title')}")
    print(f"{count} new issue(s); run one with: dia plan --start <id>")
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
    from dia.benchmark import agent_stats, suggestions
    from dia.config import save_settings

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
        from dia.shadow import describe_difference, replay

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


async def cmd_audit(config: Config, args: argparse.Namespace) -> int:
    """Who did what, newest first."""
    rows = Orchestrator(config, use_memory=False).store.audit(args.limit, args.action, args.target)
    for r in rows:
        at = datetime.fromisoformat(r["at"]).astimezone().strftime("%m-%d %H:%M")
        target = f" {r['target']}" if r["target"] else ""
        print(f"{at}  {r['actor']:<18} {r['action']:<20}{target}  {r['detail'] or ''}".rstrip())
    if not rows:
        print("nothing recorded yet")
    return 0


def _call_serve(config: Config, method: str, path: str) -> dict | None:
    """Call the running `dia serve` on this computer; None when it isn't running."""
    import json
    import urllib.error
    import urllib.request

    url, token = _ui_url(config)
    req = urllib.request.Request(
        url.rstrip("/") + path, method=method, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, OSError):
        return None


async def cmd_screen(config: Config, args: argparse.Namespace) -> int:
    """Screen access on/off, or look now."""
    dia = Orchestrator(config, use_memory=False)
    if args.action in ("on", "off"):
        dia.set_screen(args.action == "on")
        print(f"screen access {args.action}")
        return 0
    from dia.screen import look

    try:
        print(await look(dia, args.question or ""))
    except PermissionError:
        print("screen access is off: dia screen on", file=sys.stderr)
        return 1
    return 0


async def cmd_build(config: Config, args: argparse.Namespace) -> int:
    """Test and build a version of a project (Godot export presets)."""
    from dia.release import Releases

    task = await Releases(Orchestrator(config)).build(
        args.project, args.preset or None, args.ref, args.version, write_changelog=args.write
    )
    print(task.summary or task.error)
    if task.status == "done":
        print(f"\nin {task.details['output']}")
    return 0 if task.status == "done" else 1


async def cmd_publish_build(config: Config, args: argparse.Namespace) -> int:
    from dia.release import Releases

    try:
        releases = Releases(Orchestrator(config))
        if args.steam:
            pushed = [await releases.publish_steam(args.task_id)]
        else:
            pushed = await releases.publish_itch(args.task_id)
    except TaskActionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("published: " + ", ".join(pushed))
    return 0


async def cmd_changelog(config: Config, args: argparse.Namespace) -> int:
    from dia.release import Releases

    print(
        await Releases(Orchestrator(config)).changelog(
            args.project, since=args.since, ref=args.ref, write=args.write
        )
    )
    return 0


async def cmd_security(config: Config, args: argparse.Namespace) -> int:
    """Security checks: report, ports, scan HOST, devices, discover, logs, deps PROJECT."""
    from dia import security

    dia = Orchestrator(config, use_memory=False)
    options = config.section("security")
    if args.what == "ports":
        for s in security.listening():
            mark = "EXPOSED" if s["exposed"] else "local  "
            print(f"  {mark} {s['address']}:{s['port']:<6} {s['process']}")
    elif args.what == "scan":
        try:
            for p in await security.scan(args.target or "localhost", options):
                print(f"  {p['port']:<6} {p['service']} {p['version']}")
        except security.NotAuthorized as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1
    elif args.what == "devices":
        for d in security.devices():
            print(f"  {d['ip']:<16} {d['mac']}  {d['name']}")
    elif args.what == "discover":
        networks = [args.target] if args.target else options.get("networks", [])
        if not networks:
            print("list your networks in [security] networks", file=sys.stderr)
            return 1
        try:
            found = [d for n in networks for d in await security.discover(n, options)]
        except security.NotAuthorized as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1
        new = {id(d) for d in security.new_devices(dia, found)}
        for d in found:
            mark = "NEW" if id(d) in new else "   "
            print(f"  {mark} {d['ip']:<16} {d['mac'] or '-':<18} {d['vendor']} {d['name']}")
    elif args.what == "logs":
        print(json.dumps(await security.log_findings(), indent=2, ensure_ascii=False))
    elif args.what == "deps":
        if not args.target:
            print("which project? dia security deps <project>", file=sys.stderr)
            return 1
        project = config.project(args.target)
        tool, vulns = await security.audit_dependencies(project.path)
        if not tool:
            print("no audit tool applies (install osv-scanner, or pip-audit / npm / cargo-audit)")
            return 0
        for v in vulns:
            print(f"  {v.package} {v.version}  {v.id}  {v.severity}  {v.fixed}")
        print(f"{len(vulns)} vulnerable dependencies ({tool})")
        if vulns and args.fix:
            report = await dia.run_task(project.name, security.fix_prompt(tool, vulns))
            print_report(report)
        return 0
    else:
        rep = await security.report(dia)
        if args.json:
            print(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(security.describe(rep, config.language))
    return 0


async def cmd_council(config: Config, args: argparse.Namespace) -> int:
    """Several agents answer; a moderator weighs their answers."""
    from dia.council import convene

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
    from dia.research import research

    project = args.project if args.topic else None
    topic = args.topic or args.project
    print("researching (this can take several minutes) ...", file=sys.stderr)
    task = await research(Orchestrator(config), topic, project, args.agent)
    print(task.summary or task.error)
    if note := task.details.get("note"):
        print(f"\nsaved as {note}", file=sys.stderr)
    return 0 if task.status == "done" else 1


async def cmd_scorecard(config: Config, args: argparse.Namespace) -> int:
    """Dia's own numbers, week by week: is it getting better?"""
    from dia.scorecard import format_table, scorecard

    rows = scorecard(Orchestrator(config, use_memory=False).store, args.weeks)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(format_table(rows))
    return 0


async def cmd_bench(config: Config, args: argparse.Namespace) -> int:
    """Run a project's benchmark, compare with the last result; or its history."""
    from dia.benchmarks import bench, compare, describe, options

    dia = Orchestrator(config, use_memory=False)
    project = config.project(args.project)
    if args.history:
        for row in dia.store.benchmarks(project.name, limit=args.history):
            values = ", ".join(f"{k}={v:g}" for k, v in row["metrics"].items())
            print(f"{row['at'][:16]}  {row['sha'][:10]}  {row['ref'] or '-':12} {values}")
        return 0
    from dia.benchmarks import base_branch

    label = args.ref or await base_branch(project)
    previous = dia.store.benchmarks(project.name, ref=label, limit=1)
    try:
        result = await bench(dia, project.name, args.ref)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    opts = options(project)
    changes = (
        compare(previous[0]["metrics"], result["metrics"], opts["better"], opts["tolerance"])
        if previous
        else []
    )
    print(f"{project.name} @ {result['sha'][:10]}")
    print(describe(changes, result["metrics"]))
    return 1 if any(c["worse"] for c in changes) else 0


async def cmd_experiment(config: Config, args: argparse.Namespace) -> int:
    """Try a change several ways (agents or approaches) and compare the results."""
    from dia.experiments import run_experiment

    dia = Orchestrator(config)

    async def started(task: TaskRecord) -> None:
        print(f"experiment {task.id}: {task.details['variants']}", file=sys.stderr)

    try:
        task = await run_experiment(
            dia, args.project, args.question, args.agent, args.approach, started
        )
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    await dia.drain()
    print(task.summary or task.error)
    return 0 if task.status == "done" else 1


async def cmd_lab(config: Config, args: argparse.Namespace) -> int:
    """Run a command in a throwaway container (with a copy of a project)."""
    from dia.lab import Lab

    project = args.project if args.command else None
    command = args.command or args.project
    try:
        result = await Lab(Orchestrator(config, use_memory=False)).run(
            command, project, args.ref, args.image, args.network or None, args.keep
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(result.output.rstrip())
    print(f"\n[{result.image}, exit {result.code}, {result.seconds}s]", file=sys.stderr)
    if result.kept:
        print(f"kept: {result.kept}", file=sys.stderr)
    return 0 if result.ok else 1


async def cmd_redteam(config: Config, args: argparse.Namespace) -> int:
    """Hostile instructions in a throwaway repository: does Dia hold?"""
    from dia import redteam

    print("running the red-team task (one call per agent, in a throwaway Dia) ...")
    try:
        outcomes = await redteam.run(config, args.agent or None)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for o in outcomes:
        print(f"{o.agent:12} {o.verdict}")
        for note in o.notes:
            print(f"             {note}")
    if any(o.verdict == "BREACH" for o in outcomes):
        print("\nBREACH: something got out of the sandbox. Please report it as a bug.")
        return 1
    return 0


async def cmd_sandbox(config: Config, args: argparse.Namespace) -> int:
    """What each agent sees in the sandbox, and whether it starts there."""
    from dia import sandbox
    from dia.workspace import run

    if not sandbox.bwrap_works():
        print("bubblewrap does not work here: agents run unconfined (install bubblewrap)")
        return 1
    if not sandbox.enabled(config):
        print("the sandbox is off ([sandbox] enabled = false)")
        return 1
    failed = 0
    for name in config.agents:
        agent = config.agent(name)
        box = sandbox.for_agent(config, agent.kind, agent.options)
        command = getattr(agent, "command", None)
        print(f"{name} ({agent.kind}):\n{box.describe()}")
        if not command or not shutil.which(command):
            print("  (not installed)\n")
            continue
        code, out = await run(box.wrap([command, "--version"], Path.cwd()), Path.cwd(), 60)
        status = "starts" if code == 0 else f"FAILS (exit {code})"
        print(f"  {command} --version in the sandbox: {status} {out.strip()[:200]}\n")
        failed += code != 0
    return 1 if failed else 0


async def cmd_balance(config: Config, args: argparse.Namespace) -> int:
    """Balance from playtest data ([projects.<name>] balance.data)."""
    from dia.balance import balance_report

    print(await balance_report(Orchestrator(config), args.project, args.agent))
    return 0


async def cmd_analyze(config: Config, args: argparse.Namespace) -> int:
    """Scenes, scripts and textures of a Godot project: likely problems."""
    from dia.godot_analysis import analyze_project

    print(await analyze_project(Orchestrator(config), args.project, args.agent))
    return 0


async def cmd_tidy(config: Config, args: argparse.Namespace) -> int:
    """Preview tidying a folder; --apply ID moves, --undo puts back."""
    from dia.tidy import Tidy, TidyError, summary

    tidy = Tidy(Orchestrator(config, use_memory=False))
    try:
        if args.undo:
            plan = tidy.undo(None if args.undo == "last" else args.undo)
            print(f"restored {plan['restored']} files")
            return 0
        if args.apply:
            plan = tidy.apply(args.apply)
            print(f"moved {len(plan['moved'])} files; undo: dia tidy --undo {plan['id']}")
            return 0
        plan = tidy.plan(args.folder)
    except TidyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for move in plan["moves"]:
        print(f"  {move['from']}  ->  {move['to']}  ({move['reason']})")
    print(summary(plan, config.language))
    if plan["moves"]:
        print(f"move them: dia tidy --apply {plan['id']}")
    return 0


async def cmd_rollback(config: Config, args: argparse.Namespace) -> int:
    """Undo a merged task: the revert becomes a new task you merge as usual."""
    try:
        task = await Orchestrator(config).rollback_task(args.task_id, args.reason)
    except TaskActionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(task.summary or task.error)
    if task.status == "done":
        print(f"merge it to undo: dia merge {task.id}")
    return 0 if task.status == "done" else 1


async def cmd_why(config: Config, args: argparse.Namespace) -> int:
    """Why was something decided: decisions, what came of them, notes, commits."""
    from dia.decisions import describe, why

    print(describe(await why(Orchestrator(config), args.question, args.project)))
    return 0


async def cmd_profile(config: Config, args: argparse.Namespace) -> int:
    """Your working style, learnt from your decisions: show, draft an update, accept."""
    from dia import profile

    dia = Orchestrator(config)
    try:
        if args.update:
            print("drafting from your decisions ...", file=sys.stderr)
            print(await profile.update(dia, args.agent))
            print("\nmake it your profile: dia profile --accept", file=sys.stderr)
        elif args.accept:
            profile.accept(dia)
            print("the profile is updated")
        else:
            print(profile.read(dia) or "no profile yet: dia profile --update")
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


async def cmd_contradictions(config: Config, args: argparse.Namespace) -> int:
    """Do the notes and docs still match the code? Corrections are proposals."""
    from dia.contradictions import check

    print("an agent compares the notes and docs with the code ...", file=sys.stderr)
    task = await check(Orchestrator(config), args.project, args.agent)
    print(task.summary or task.error)
    if task.details.get("learn"):
        print(f"\naccept the corrections: dia learned {task.id} --accept all", file=sys.stderr)
    return 0 if task.status == "done" else 1


async def cmd_impact(config: Config, args: argparse.Namespace) -> int:
    """What could break if this changes: dependents, files changed with it, tests."""
    from dia.impact import impact

    _, text = await impact(Orchestrator(config), args.project, args.target, args.agent)
    print(text)
    return 0


async def cmd_debt(config: Config, args: argparse.Namespace) -> int:
    """The technical debt register; --fix N pays an item off as a task."""
    from dia import debt

    dia = Orchestrator(config)
    if args.fix:
        try:
            report = await debt.fix(dia, args.project, args.fix)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print_report(report)
        return 0 if report.task.status == "done" else 1
    print(debt.describe(await debt.register(dia, args.project, args.deps), args.limit))
    return 0


async def cmd_debug(config: Config, args: argparse.Namespace) -> int:
    """A bug for a swarm of agents: hypotheses, each checked by a test."""
    from dia import swarm

    dia = Orchestrator(config)
    try:
        if args.fix:
            report = await swarm.fix(dia, args.fix)
            print_report(report)
            return 0 if report.task.status == "done" else 1
        if not args.project or not args.bug:
            print('error: dia debug PROJECT "the bug" (or --fix ID)', file=sys.stderr)
            return 2
        print("agents are looking for the cause ...", file=sys.stderr)
        task = await swarm.debug(dia, args.project, args.bug, args.agent)
    except TaskActionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(task.summary or task.error)
    return 0 if task.status == "done" else 1


async def cmd_goal(config: Config, args: argparse.Namespace) -> int:
    """Goals over weeks: milestones, weekly reviews, the next mission for your approval."""
    from dia import goals

    dia = Orchestrator(config)
    try:
        if args.action == "new":
            if not args.project or not args.text:
                print('error: dia goal new PROJECT "the goal" [--weeks N]', file=sys.stderr)
                return 2
            print("breaking it into milestones ...", file=sys.stderr)
            goal = await goals.create(dia, args.project, args.text, args.weeks)
            print(f"goal {goal.id}\n{goals.describe(goal)}")
            return 0 if goal.status == "active" else 1
        if args.action == "list":
            for goal in goals.goals(dia, active=False):
                print(f"{goal.id}  {goal.project}\n{goals.describe(goal)}\n")
            return 0
        goal_id = args.project
        if not goal_id:
            print(f"error: dia goal {args.action} GOAL_ID", file=sys.stderr)
            return 2
        if args.action == "review":
            print("reviewing ...", file=sys.stderr)
            await goals.review(dia, goal_id)
            print(goals.describe(dia.store.get(goal_id)))
            print(f"\naccept it (and prepare the next mission): dia goal approve {goal_id}")
        elif args.action == "approve":
            mission = await goals.approve(dia, goal_id)
            if mission:
                print(f"mission {mission.id} prepared; start it: dia mission --start {mission.id}")
            else:
                print("recorded")
        elif args.action == "close":
            goals.close(dia, goal_id)
            print("closed")
    except (ValueError, RuntimeError, TaskActionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


async def cmd_work(config: Config, args: argparse.Namespace) -> int:
    """Start or stop work on a profile: apps, where you are, the saved session."""
    from dia import work

    dia = Orchestrator(config, use_memory=False)
    try:
        if args.action == "list":
            for name, profile in work.profiles(dia).items():
                apps = ", ".join(profile.get("apps", [])) or "-"
                print(f"{name:<16} project {profile.get('project') or '-':<12} apps: {apps}")
        elif args.action == "start":
            print(await work.start(dia, args.name, open_apps=not args.no_apps))
        else:
            print(await work.stop(dia, args.name, args.note or ""))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def skill_args(skill_args: dict[str, str], words: list[str]) -> dict[str, str]:
    """``place=Gdańsk`` pairs; bare words go to the skill's first argument."""
    found: dict[str, str] = {}
    loose = []
    for word in words:
        key, eq, value = word.partition("=")
        if eq and key in skill_args:
            found[key] = value
        else:
            loose.append(word)
    if loose and skill_args:
        first = next(iter(skill_args))
        found[first] = " ".join(filter(None, [found.get(first, ""), *loose]))
    return found


async def cmd_skill(config: Config, args: argparse.Namespace) -> int:
    """Run one skill (weather, crypto, briefing...) or list them."""
    from dia.skills import NeedsConfirmation, enabled_skills

    dia = Orchestrator(config)
    skills = enabled_skills(dia)
    if not args.name:
        for name, skill in sorted(skills.items()):
            spec = " ".join(f"[{k}=...]" for k in skill.args)
            print(f"{name:12} {skill.description}" + (f"\n{'':12} {spec}" if spec else ""))
        return 0
    skill = skills.get(args.name)
    if not skill:
        print(f"error: no skill {args.name!r}; installed: {', '.join(sorted(skills))}",
              file=sys.stderr)  # fmt: skip
        return 1
    try:
        print(await skill.run(skill_args(skill.args, args.args)))
    except NeedsConfirmation as ask:
        answer = "y" if args.yes else input(f"{ask.question} [y/N] ").strip().lower()
        if answer not in ("y", "yes", "t", "tak"):
            print("not done")
            return 0
        print(await ask.action())
    except Exception as exc:  # a skill talks to the outside world: say what failed
        print(f"error: {args.name}: {exc}", file=sys.stderr)
        return 1
    return 0


async def cmd_suggestions(config: Config, args: argparse.Namespace) -> int:
    """Suggestions from Dia's history: list, check now, accept or dismiss."""
    from dia.suggestions import Suggestions

    dia = Orchestrator(config)
    suggestions = Suggestions(dia)
    try:
        if args.accept:
            report = await suggestions.accept(args.accept)
            if report:
                print_report(report)
            return 0
        if args.dismiss:
            suggestions.dismiss(args.dismiss)
            print("dismissed: not suggested again")
            return 0
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.check:
        await suggestions.check()
    for s in suggestions.open():
        print(f"{s['key']}\n  {s['text']}")
    return 0


async def cmd_decisions(config: Config, args: argparse.Namespace) -> int:
    from dia.decisions import describe

    rows = Orchestrator(config, use_memory=False).store.decisions(args.project, limit=args.limit)
    found = {"terms": ["*"], "decisions": [{**r, "consequences": []} for r in rows]}
    print(describe({**found, "notes": [], "commits": []}))
    return 0


async def cmd_scenario(config: Config, args: argparse.Namespace) -> int:
    """Does it work? An agent writes a test for the scenario; Dia runs it."""
    from dia.scenario import check_scenario

    print("writing and running a test for it ...", file=sys.stderr)
    report = await check_scenario(Orchestrator(config), args.project, args.scenario, args.agent)
    print(report.task.summary or report.task.error)
    return {"works": 0, "broken": 1}.get(report.task.details.get("scenario_result", ""), 2)


async def cmd_preferences(config: Config, args: argparse.Namespace) -> int:
    """What Dia knows about how you like things done."""
    from dia.persona import add_preference
    from dia.preferences import Preferences

    dia = Orchestrator(config, use_memory=False)
    prefs = Preferences(config)
    try:
        if args.add:
            print(f"kept: {add_preference(dia, args.add)}")
        for n in args.accept or []:
            print(f"accepted: {prefs.decide(0 if n == 'all' else int(n) - 1, True)}")
        for n in args.reject or []:
            print(f"rejected: {prefs.decide(int(n) - 1, False)}")
        if args.remove:
            print(f"removed: {prefs.remove(args.remove - 1)}")
    except (IndexError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    data = prefs.snapshot()
    for text in data["configured"]:
        print(f"   (config) {text}")
    for i, item in enumerate(data["accepted"], 1):
        print(f"{i:3}. {item['text']}")
    if data["proposed"]:
        print("\nproposed (dia preferences --accept N | --reject N):")
        for i, item in enumerate(data["proposed"], 1):
            print(f"{i:3}. {item['text']}")
    return 0


async def cmd_quiet(config: Config, args: argparse.Namespace) -> int:
    """Quiet mode: Dia answers in text only."""
    on = args.state == "on"
    if _call_serve(config, "POST", f"/api/quiet?on={int(on)}") is None:
        Orchestrator(config, use_memory=False).set_quiet(on)
    print("quiet mode " + ("on: text answers only" if on else "off: Dia speaks again"))
    return 0


async def cmd_stop(config: Config, args: argparse.Namespace) -> int:
    """Emergency stop (or resume) of the running Dia."""
    path = "/api/resume" if args.resume else "/api/stop"
    answer = _call_serve(config, "POST", path)
    if answer is None:
        # No `dia serve` to reach: still record the state so it starts stopped.
        dia = Orchestrator(config, use_memory=False)
        await (dia.resume() if args.resume else dia.stop_all("dia stop (serve not running)"))
        print("dia serve is not running; the state is saved for its next start")
        return 0
    print(answer.get("message", answer))
    return 0


async def cmd_mission(config: Config, args: argparse.Namespace) -> int:
    """Create, run, continue, cancel or list missions."""
    from dia.missions import Missions

    dia = Orchestrator(config)
    missions = Missions(dia)
    if args.cancel:
        missions.cancel(args.cancel)
        print("no further steps will start (running ones finish; `dia stop` ends them)")
        return 0
    if args.start:
        mission = dia.store.get(args.start)
    elif args.project and args.goal:
        print("planning the mission ...", file=sys.stderr)
        budget = {k: v for k, v in (("calls", args.calls), ("minutes", args.minutes)) if v}
        mission = await missions.create(
            args.project, args.goal, budget=budget, priority=args.priority
        )
    else:
        for m in [t for t in dia.store.recent(100) if t.mode == "mission"]:
            steps = m.details["mission"]["steps"]
            done = sum(s["status"] == "done" for s in steps)
            print(f"  {m.id}  {m.status:<8} {m.project:<12} {done}/{len(steps)}  {m.prompt[:60]}")
        return 0
    if not mission or mission.mode != "mission":
        print("no such mission", file=sys.stderr)
        return 1
    info = mission.details["mission"]
    print(f"mission {mission.id} for {mission.project}: {mission.prompt}")
    print(f"budget: {info['budget']}  priority: {info.get('priority', 'normal')}")
    for step in info["steps"]:
        after = f"  (after {', '.join(step['depends_on'])})" if step["depends_on"] else ""
        print(f"  [{step['id']}] {step['title']} · {step['agent']} · {step['status']}{after}")
    if mission.status not in ("planned", "paused", "failed"):
        return 0
    answer = "y" if args.yes else input("\nRun this mission? [y/N] ").strip().lower()
    if answer not in ("y", "yes", "t", "tak"):
        print(f"not started; later: dia mission --start {mission.id}")
        return 0
    mission = (await dia.run_plan(mission.id)).task
    print(f"\nmission {mission.status}" + (f": {mission.error}" if mission.error else ""))
    if mission.status == "done" and mission.branch:
        print(f"branch {mission.branch}; dia merge {mission.id} or dia publish {mission.id}")
    return 0 if mission.status == "done" else 1


async def cmd_remember(config: Config, args: argparse.Namespace) -> int:
    try:
        Orchestrator(config).remember(args.project, args.fact)
    except (TaskActionError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"remembered for {args.project}: {args.fact}")
    return 0


def print_report(report: TaskReport) -> None:
    task = report.task
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"task:    {task.id}  [{task.status}]  agent={task.agent}")
    if task.commit_sha:
        print(f"branch:  {task.branch} @ {task.commit_sha[:10]}")
        print(report.diff_stat)
    if task.tests_ok is not None:
        summary = report.test_output.splitlines()[0] if report.test_output else ""
        print(f"tests:   {'passed' if task.tests_ok else 'FAILED'}  {summary}".rstrip())
        if not task.tests_ok:
            print(report.test_output[-3000:])
        print(f"         full log: dia show {task.id} --tests")
    for step in task.details.get("steps", []):
        mark = "ok" if step["success"] else "FAILED"
        print(f"step:    {step['title']} [{step['agent']}] {mark} ({step['duration_s']}s)")
    if task.summary:
        print("\n" + task.summary)
    for review in task.details.get("reviews", []):
        print(f"\nreview (round {review['round']}) by {review['reviewer']}: {review['verdict']}")
        print(review["findings"])
        if reply := review.get("author_reply"):
            print(f"\n{task.agent} replied: {reply}")
    if task.error:
        print(f"\nerror: {task.error}", file=sys.stderr)


async def cmd_tasks(config: Config, args: argparse.Namespace) -> int:
    for task in Orchestrator(config, use_memory=False).store.recent(args.limit, args.project):
        tests = {None: "-", True: "pass", False: "FAIL"}[task.tests_ok]
        title = task.prompt.splitlines()[0][:60]
        print(f"{task.id}  {task.status:<7} {task.project:<14} {task.agent:<10} {tests:<5} {title}")
    return 0


async def cmd_show(config: Config, args: argparse.Namespace) -> int:
    dia = Orchestrator(config, use_memory=False)
    task = dia.store.get(args.task_id)
    if not task:
        print(f"no task {args.task_id}", file=sys.stderr)
        return 1
    if args.tests:
        log = dia.test_log_path(task.id)
        print(log.read_text() if log.exists() else "no test log for this task")
        return 0
    for key, value in vars(task).items():
        if key != "summary":
            print(f"{key:<12} {value}")
    print("\n" + (task.summary or ""))
    return 0


async def cmd_memory_index(config: Config, args: argparse.Namespace) -> int:
    """Build or refresh the semantic index of the notes ([memory] semantic)."""
    memory = config.memory()
    index = getattr(memory, "semantic_index", lambda: None)()
    if not index:
        print("semantic search is off: set [memory] semantic (docs/MEMORY.md)", file=sys.stderr)
        return 1
    print("indexing notes (the first run embeds the whole vault) ...", file=sys.stderr)
    try:
        count = await asyncio.to_thread(index.update)
    except OSError as exc:
        print(f"error: embedding server: {exc} (is Ollama running?)", file=sys.stderr)
        return 1
    print(f"{count} note(s) indexed")
    return 0


async def cmd_memory_search(config: Config, args: argparse.Namespace) -> int:
    memory = config.memory()
    if not memory:
        print("memory is off (no [memory] section in the config)", file=sys.stderr)
        return 1
    hits = memory.search(args.query, limit=args.limit)
    if not hits:
        print("no matching notes")
    for hit in hits:
        print(f"{hit.score:6.2f}  {hit.link}")
        print("        " + hit.snippet.replace("\n", "\n        ") + "\n")
    return 0


async def cmd_plan(config: Config, args: argparse.Namespace) -> int:
    dia = Orchestrator(config, use_memory=not args.no_memory)
    if args.start:
        plan = dia.store.get(args.start)
        if not plan:
            raise TaskActionError(f"no task {args.start}")
    else:
        if not args.project or not args.goal:
            print("usage: dia plan PROJECT GOAL [--pipeline NAME]  or  dia plan --start ID")
            return 2
        print("planning ..." if not args.pipeline else f"pipeline {args.pipeline}", file=sys.stderr)
        plan = await dia.create_plan(
            args.project, args.goal, pipeline=args.pipeline, planner=args.planner
        )
    print(f"plan {plan.id} for {plan.project}: {plan.prompt}")
    for i, step in enumerate(plan.details["plan"], 1):
        print(f"\n{i}. {step.get('title') or step['agent']}  [{step['agent']}]")
        print("   " + step["prompt"].replace("\n", "\n   "))
    from dia.simulation import describe

    if sim := describe(plan.details.get("simulation")):
        print("\n" + sim)
    answer = "y" if args.yes else input("\nRun this plan? [y/N] ").strip().lower()
    if answer not in ("y", "yes", "t", "tak"):
        print(f"not started; run it later with: dia plan --start {plan.id}")
        return 0
    report = await dia.run_plan(plan.id, review=True if args.review else None)
    print_report(report)
    await finish_learning(dia, report.task.id)
    return 0 if report.task.status == "done" else 1


async def cmd_review(config: Config, args: argparse.Namespace) -> int:
    print(f"reviewing {args.task_id} ...", file=sys.stderr)
    report = await Orchestrator(config, use_memory=False).review_task(
        args.task_id, reviewer=args.agent, fix_rounds=args.rounds
    )
    print_report(report)
    return 0


async def cmd_diff(config: Config, args: argparse.Namespace) -> int:
    print(await Orchestrator(config, use_memory=False).task_diff(args.task_id))
    return 0


async def cmd_merge(config: Config, args: argparse.Namespace) -> int:
    try:
        sha = await Orchestrator(config, use_memory=False).merge_task(
            args.task_id, args.reason, args.override
        )
    except TaskActionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"merged {args.task_id} as {sha[:10]}")
    return 0


async def cmd_ci(config: Config, args: argparse.Namespace) -> int:
    dia = Orchestrator(config, use_memory=False)
    while True:
        status = await dia.ci_status(args.task_id)
        print(f"CI: {status.state}" + (f"  {status.url}" if status.url else ""))
        for job in status.failed:
            print(f"  failed: {job.get('name')}  {job.get('url') or ''}")
        if not args.watch or status.state != "pending":
            break
        await asyncio.sleep(args.interval)
    if args.fix and status.state == "failed":
        print("asking the author to fix it ...", file=sys.stderr)
        await dia.fix_ci(args.task_id)
        print("fix pushed; CI runs again")
    return 0 if status.state in ("success", "none") else 1


async def cmd_launch(config: Config, args: argparse.Namespace) -> int:
    print(await Orchestrator(config, use_memory=False).launch(args.project))
    return 0


async def cmd_comments(config: Config, args: argparse.Namespace) -> int:
    dia = Orchestrator(config, use_memory=False)
    new = await dia.review_comments(args.task_id)
    pending = dia.store.get(args.task_id).details.get("comments_pending", [])
    print(f"{len(new)} new, {len(pending)} not yet addressed")
    for c in pending:
        where = f" {c['path']}:{c['line'] or ''}" if c.get("path") else ""
        print(f"\n{c['author']}{where}\n  " + c["body"].strip().replace("\n", "\n  "))
    if args.fix and pending:
        print("\nasking the author to address them ...", file=sys.stderr)
        await dia.address_comments(args.task_id)
        print("changes pushed; the PR/MR is updated")
    return 0


async def cmd_publish(config: Config, args: argparse.Namespace) -> int:
    publication = await Orchestrator(config, use_memory=False).publish_task(args.task_id)
    print(publication.message)
    return 0


async def cmd_discard(config: Config, args: argparse.Namespace) -> int:
    await Orchestrator(config, use_memory=False).discard_task(args.task_id, args.reason)
    print(f"discarded {args.task_id}")
    return 0


async def cmd_runtime(config: Config, args: argparse.Namespace) -> int:
    """Local control, also usable by the widget while the HTTP server is stopped."""
    from dia import runtime

    try:
        if args.action == "configure":
            current = runtime.policy()
            runtime.configure(
                config.source,
                autostart=args.autostart if args.autostart is not None else current["autostart"],
                ollama=args.ollama or current["ollama"],
                warmup=args.warmup if args.warmup is not None else current["warmup"],
            )
        elif args.action != "status":
            if args.report:
                runtime.report_operation(args.component, args.action, "running")
            runtime.action(args.component, args.action, config.source)
            if args.report:
                runtime.report_operation(args.component, args.action, "done")
        print(json.dumps({**runtime.status(), "language": config.language}))
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        if args.report:
            runtime.report_operation(args.component, args.action, "failed", str(exc))
        print(json.dumps({"error": str(exc)}))
        return 1


async def cmd_service(config: Config, args: argparse.Namespace) -> int:
    from dia import service

    try:
        if args.action == "install":
            notes = service.install(config.source, start=not args.no_start)
        elif args.action == "uninstall":
            notes = service.uninstall()
        elif args.action == "logs":
            os.execvp("journalctl", ["journalctl", "--user", "-u", service.UNIT_NAME, "-f"])
        else:
            notes = [service.status()]
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("\n".join(notes))
    return 0


async def cmd_serve(config: Config, args: argparse.Namespace) -> int:
    """Run all configured channels (Discord, ...) until interrupted."""
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    dia = Orchestrator(config)
    channels = [config.channel(name, dia) for name in config.channels]
    if config.ui.get("enabled", True):
        try:
            from dia.channels.api import ApiChannel
        except ImportError:
            print("UI disabled: install it with pip install 'dia[ui]'", file=sys.stderr)
        else:
            channels.append(ApiChannel("ui", config.ui, dia))
    if not channels:
        print("nothing to serve: add e.g. [channels.discord] or enable [ui]", file=sys.stderr)
        return 2
    for channel in channels:
        if problem := channel.check():
            print(f"channel {channel.name}: {problem}", file=sys.stderr)
            return 2
    print(f"serving: {', '.join(c.name for c in channels)} (Ctrl+C to stop)", file=sys.stderr)
    from dia import sandbox
    from dia.health import interrupted, supervise

    if not sandbox.enabled(config):
        why = (
            "bubblewrap is missing or unusable"
            if not sandbox.bwrap_works()
            else "[sandbox] enabled = false"
        )
        print(
            f"WARNING: agents will run WITHOUT a sandbox ({why}). "
            "Install bubblewrap or set [sandbox] enabled = true.",
            file=sys.stderr,
        )
    if stuck := interrupted(dia):
        print(f"{len(stuck)} task(s) were interrupted by the restart", file=sys.stderr)
    # (name, how to start it): each runs supervised, restarted if it crashes.
    jobs: list[tuple[str, Any]] = [(channel.name, channel.run) for channel in channels]
    if config.ci.get("watch", True):
        from dia.ci import CIWatcher

        jobs.append(("ci", CIWatcher(dia).run))
    from dia.schedule import Scheduler

    jobs.append(("scheduler", Scheduler(dia).run))
    from dia.goals import GoalWatcher

    jobs.append(("goals", GoalWatcher(dia).run))
    from dia.suggestions import SuggestionWatcher

    jobs.append(("suggestions", SuggestionWatcher(dia).run))
    if config.section("system").get("watch", True):
        from dia.system import SystemWatcher

        jobs.append(("system", SystemWatcher(dia).run))
    if dia.memory and getattr(dia.memory, "semantic_index", lambda: None)():
        jobs.append(("memory index", lambda: _keep_index_fresh(dia)))
    from dia.push import Push
    from dia.push import available as push_available

    if push_available():
        push = Push(dia)
        dia.listeners.append(push.on_event)
        dia.store.listeners.append(push.on_task_saved)
    if config.section("issues").get("enabled", bool(config.section("issues"))):
        from dia.issues import IssueWatcher

        jobs.append(("issues", IssueWatcher(dia).run))
    if config.watch.get("enabled", bool(config.watch)):
        from dia.watch import ProjectWatcher

        jobs.append(("watch", ProjectWatcher(dia).run))
    try:
        await asyncio.gather(*(supervise(dia, name, start) for name, start in jobs))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


async def _keep_index_fresh(dia: Orchestrator) -> None:
    """Refresh the semantic index in the background while `dia serve` runs."""
    while True:
        index = dia.memory.semantic_index() if dia.memory else None
        if index:
            try:
                await asyncio.to_thread(index.update)
            except Exception as exc:
                print(f"memory index: {exc}", file=sys.stderr)
        await asyncio.sleep(1800)


def _ui_url(config: Config) -> tuple[str, str]:
    from dia.channels.api import DEFAULT_PORT, api_token

    port = int(config.ui.get("port", DEFAULT_PORT))
    return f"http://127.0.0.1:{port}/", api_token(config.data_dir)


def _ui_running(url: str) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=1):
            return True
    except OSError:
        return False


async def cmd_ui(config: Config, args: argparse.Namespace) -> int:
    """Print (or open) the address of the web UI, with the token to sign in."""
    url, token = _ui_url(config)
    if args.token:
        print(token)
        return 0
    full = f"{url}#token={token}"
    if not _ui_running(url):
        print(
            "note: the UI is not running; start `dia serve` (or `dia service install`)",
            file=sys.stderr,
        )
    print(full)
    if args.open:
        import webbrowser

        webbrowser.open(full)
    return 0


def cmd_secret(args: argparse.Namespace) -> int:
    """API keys and tokens in ~/.config/dia/env (mode 600); values are never shown."""
    from dia import secrets
    from dia.service import env_path

    if args.action == "list":
        for item in secrets.status():
            mark = "set" if item["set"] else "-"
            print(f"  {item['name']:<24} {mark:<4} {item['label']}")
        print(f"(in {env_path()})")
        return 0
    if not args.name:
        print("error: which secret? e.g. ELEVENLABS_API_KEY", file=sys.stderr)
        return 1
    if args.action == "rm":
        removed = secrets.remove_secret(args.name)
        print("removed" if removed else f"{args.name} is not set")
        return 0 if removed else 1
    import getpass

    value = getpass.getpass(f"{args.name} (input hidden): ")
    try:
        secrets.set_secret(args.name, value)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"saved {args.name} in {env_path()}; restart Dia (dia service restart) to use it")
    return 0


async def cmd_mobile(config: Config, args: argparse.Namespace) -> int:
    """Pair, list and revoke devices (phones) that may use Dia remotely."""
    from dia.channels.api import DEFAULT_PORT
    from dia.devices import Devices, public_url

    devices = Devices(config.data_dir)
    if args.action == "list":
        for device in devices.list():
            seen = device.last_seen or "never used"
            print(f"  {device.id}  {device.name:<16} paired {device.created_at}  last {seen}")
        if not devices.list():
            print("no paired devices (dia mobile pair --name phone)")
        return 0
    if args.action == "revoke":
        if not args.device:
            print("error: which device? (id or name, see dia mobile list)", file=sys.stderr)
            return 1
        gone = devices.revoke(args.device)
        print(f"revoked {gone.name}" if gone else f"no device {args.device}")
        return 0 if gone else 1

    if not config.ui.get("remote"):
        print(
            "note: remote access is off; set [ui] remote = true (docs/MOBILE.md) and restart",
            file=sys.stderr,
        )
    device, token = devices.pair(args.name)
    url = public_url(config.ui, int(config.ui.get("port", DEFAULT_PORT)))
    print(f"paired '{device.name}' (id {device.id}); shown only now, revoke it if it leaks")
    if not url:
        print(f"token: {token}\nset [ui] public_url to get a link and a QR code")
        return 0
    link = f"{url}#token={token}"
    try:
        import qrcode

        qr = qrcode.QRCode(border=2)
        qr.add_data(link)
        qr.print_ascii(invert=True)
    except ImportError:
        print("(pip install 'dia[mobile]' to show a QR code here)", file=sys.stderr)
    print(f"open on the phone: {link}")
    return 0


async def cmd_app(config: Config, args: argparse.Namespace) -> int:
    """Open Dia in its own window, starting `dia serve` in the background if needed."""
    import shutil
    import subprocess

    from dia import appwindow, runtime, service

    url, token = _ui_url(config)
    background = getattr(args, "background", False)
    native = appwindow.available() and not args.browser
    # The native shell remains usable with a stopped backend. A login launch
    # explicitly starts services; an ordinary open preserves a stopped service.
    managed = (service.unit_path().parent / runtime.TARGET).exists()
    start_native = (
        native
        and service.check() is None
        and (background or (not managed and not _ui_running(url)))
    )
    if not (native and service.check() is None) and (
        background or (not managed and not _ui_running(url))
    ):
        if service.check() is None and (managed or service.installed()):
            try:
                await asyncio.to_thread(runtime.action, "dia", "start", config.source)
            except (RuntimeError, OSError) as exc:
                print(f"Could not start Dia: {exc}", file=sys.stderr)
                if not native:
                    return 1
        elif not _ui_running(url):
            log_file = config.data_dir / "serve.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            argv = [sys.executable, "-m", "dia"]
            if config.source:
                argv += ["--config", str(config.source)]
            with log_file.open("a") as out:
                subprocess.Popen(
                    [*argv, "serve"],
                    stdout=out,
                    stderr=out,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
    view, task = getattr(args, "view", None), getattr(args, "task", None)
    full = (
        f"{url}#token={token}"
        + (f"&view={view}" if view else "")
        + (f"&task={task}" if task else "")
    )
    if native:
        source = config.source

        def app_options() -> dict:
            try:
                return (load_config(source) if source else config).section("app")
            except ConfigError:
                return config.section("app")

        return appwindow.run(
            url,
            token,
            language=config.language,
            view=view,
            task=task,
            data_dir=config.data_dir,
            load_options=app_options,
            background=background,
            config_source=source,
            start_services=start_native,
        )
    if background:
        return 0
    for _ in range(50):
        if _ui_running(url):
            break
        await asyncio.sleep(0.2)
    else:
        print("Dia is stopped. Start it with: dia runtime start", file=sys.stderr)
        return 1
    try:
        import webview
    except ImportError:
        webview = None
    if webview and not args.browser:
        webview.create_window("Dia", full, width=1280, height=820, min_size=(720, 480))
        try:
            webview.start(icon=str(appwindow.ICONS / "dia-256.png"))
        except TypeError:  # pywebview before 5 has no window icon
            webview.start()
        return 0
    for browser in (
        "chromium",
        "google-chrome",
        "google-chrome-stable",
        "brave",
        "brave-browser",
        "microsoft-edge",
        "vivaldi",
    ):
        if shutil.which(browser):  # an app window without tabs or address bar
            subprocess.Popen(
                [browser, f"--app={full}"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return 0
    import webbrowser

    webbrowser.open(full)
    return 0


async def cmd_shortcut(config: Config, args: argparse.Namespace) -> int:
    """Dia in the application menu, on the desktop and (optionally) at login."""
    import subprocess

    from dia import desktop

    if args.action == "uninstall":
        removed = desktop.uninstall()
        print("\n".join(f"removed {p}" for p in removed) or "no shortcuts to remove")
        return 0
    try:
        done = desktop.install(config.source, not args.no_desktop, args.autostart)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("\n".join(done))
    print("Dia starts with one click now (or `dia up` in a terminal).")
    return 0


async def cmd_plasmoid(config: Config, args: argparse.Namespace) -> int:
    from dia.ui import plasmoid_install

    try:
        print(
            plasmoid_install.install() if args.action == "install" else plasmoid_install.uninstall()
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


async def cmd_say(config: Config, args: argparse.Namespace) -> int:
    """Talk to Dia in your own words; a brain decides what to do."""
    from dia.assistant import Assistant

    dia = Orchestrator(config, use_memory=not args.no_memory)
    assistant = Assistant(dia, config.brain_chain(only=args.brain))
    intent = await assistant.interpret(args.text)
    target = f" project={intent.project}" if intent.project else ""
    print(f"[{intent.brain or '-'}] {intent.action}{target}", file=sys.stderr)
    if intent.reply:
        print(intent.reply)
    if args.dry_run:
        if intent.prompt and intent.action in ("run", "ask"):
            print(f"prompt: {intent.prompt}")
        return 0
    response = await assistant.execute(intent)
    if intent.action == "plan" and assistant.pending_plan:
        print(response.text)
        answer = "y" if args.yes else input("[y/N] ").strip().lower()
        if answer not in ("y", "yes", "t", "tak"):
            print(f"not started; run it later with: dia plan --start {assistant.pending_plan}")
            return 0
        response = await assistant.execute(await assistant.interpret("yes"))
    if response.report:
        task = response.report.task
        print(f"task:    {task.id}  [{task.status}]  agent={task.agent}")
        if task.commit_sha:
            print(f"branch:  {task.branch}  (dia diff / merge / discard {task.id})")
    if response.text and response.text != intent.reply:
        print("\n" + response.text)
    return 0 if not response.report or response.report.task.status == "done" else 1


def _voice_channel(config: Config):
    name = next((n for n, o in config.channels.items() if o.get("type", n) == "voice"), None)
    if not name:
        raise ConfigError("no voice channel configured; add [channels.voice] (see docs/VOICE.md)")
    return config.channel(name, Orchestrator(config, use_memory=False))


async def _speakers(config: Config, args: argparse.Namespace) -> int:
    """Enroll, list or forget the voices Dia recognises."""
    from dia.voice.audio import is_silent
    from dia.voice.speaker import read_samples

    voice = _voice_channel(config)
    if not voice.speakers:
        print("speaker recognition is off: set [channels.voice] speaker", file=sys.stderr)
        return 2
    if args.action == "speakers":
        print("\n".join(voice.speakers.names()) or "nobody enrolled yet")
        return 0
    if not args.text:
        print(f"usage: dia voice {args.action} NAME", file=sys.stderr)
        return 2
    if args.action == "forget":
        found = voice.speakers.forget(args.text)
        print("forgotten" if found else f"no speaker {args.text}")
        return 0 if found else 1
    if problem := voice.speakers.check() or voice.recorder.check():
        print(f"voice: {problem}", file=sys.stderr)
        return 2
    samples = []
    for n in range(1, 4):
        path = voice._tmp / f"enroll-{n}.wav"
        input(f"[{n}/3] press Enter, then speak naturally for {args.seconds:g} s...")
        await voice.recorder.start(path)
        await asyncio.sleep(args.seconds)
        await voice.recorder.stop()
        if is_silent(path):
            print("only silence was recorded; check the microphone", file=sys.stderr)
            return 1
        samples.append(read_samples(path))
        path.unlink(missing_ok=True)
    count = voice.speakers.enroll(args.text, samples)
    print(f"{args.text}: {count} voice samples kept (as numbers, not recordings)")
    return 0


async def cmd_voice(config: Config, args: argparse.Namespace) -> int:
    """Control the running voice channel, or test the microphone and voice."""
    from dia.channels.voice import send_command

    if args.action == "speak":
        voice = _voice_channel(config)
        await voice.say(args.text or "Cześć, tu Dia. Słyszysz mnie?")
        return 0
    if args.action in ("enroll", "speakers", "forget"):
        return await _speakers(config, args)
    if args.action == "listen":
        voice = _voice_channel(config)
        if problem := voice.check():
            print(f"voice: {problem}", file=sys.stderr)
            return 2
        path = voice._tmp / "test.wav"
        print(f"recording {args.seconds}s, speak now...", file=sys.stderr)
        await voice.recorder.start(path)
        await asyncio.sleep(args.seconds)
        await voice.recorder.stop()
        from dia.voice.audio import is_silent

        if is_silent(path):
            print(
                "the recording is silent: the microphone is muted or the wrong input is "
                "selected (check your sound settings)",
                file=sys.stderr,
            )
            return 1
        print("transcribing (the first run downloads the model)...", file=sys.stderr)
        print(await voice.stt.transcribe(path, voice.language) or "(nothing heard)")
        return 0
    try:
        print(await send_command(args.action))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dia", description="Dia: your coding-agent orchestrator")
    parser.add_argument("--version", action="version", version=f"dia {__version__}")
    parser.add_argument("-c", "--config", type=Path, help="path to config TOML")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("version", help="Dia's version and where it lives").set_defaults(fn=cmd_version)
    setup_p = sub.add_parser("setup", help="set Dia up: agents, projects, memory, shortcuts")
    setup_p.add_argument("-y", "--yes", action="store_true", help="accept every proposal")
    setup_p.set_defaults(fn=cmd_setup)
    doctor = sub.add_parser("doctor", help="check config, agents and projects")
    doctor.add_argument("--fix", action="store_true", help="repair what is safe to repair")
    doctor.set_defaults(fn=cmd_doctor)
    sub.add_parser("agents", help="list agent plugins and configured agents").set_defaults(
        fn=cmd_agents
    )

    check = sub.add_parser("check", help="test a commit of a project (what `[watch]` does)")
    check.add_argument("project")
    check.add_argument("ref", nargs="?", default="HEAD")
    check.set_defaults(fn=cmd_check)
    fix_build = sub.add_parser("fix-build", help="let an agent fix what a failed check broke")
    fix_build.add_argument("task_id")
    fix_build.set_defaults(fn=cmd_fix_build)
    sched = sub.add_parser("schedule", help="recurring jobs: briefing, checks, tasks")
    sched.add_argument("action", choices=["list", "add", "rm", "run"], nargs="?", default="list")
    sched.add_argument("cron", nargs="?", help="add: cron expression; rm/run: the job's id")
    sched.add_argument("text", nargs="?", help="add: what to ask Dia (or a skill with --skill)")
    sched.add_argument("--skill", action="store_true", help="add: text is a skill name")
    sched.add_argument("--speak", action="store_true", help="add: also say the answer aloud")
    sched.set_defaults(fn=cmd_schedule)
    issues = sub.add_parser("issues", help="import issues labelled for Dia as plans")
    issues.add_argument("project", nargs="?")
    issues.set_defaults(fn=cmd_issues)
    usage = sub.add_parser("usage", help="how much each agent was used, and how well it does")
    usage.add_argument("--days", type=int, default=30)
    usage.add_argument(
        "--apply",
        nargs=2,
        metavar=("PROJECT", "AGENT"),
        help="make a proposed agent the project's default",
    )
    usage.set_defaults(fn=cmd_usage)
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
    audit = sub.add_parser("audit", help="who did what (merges, tasks, settings...)")
    audit.add_argument("-n", "--limit", type=int, default=50)
    audit.add_argument("--action", help="e.g. task.merge, or a prefix: task.")
    audit.add_argument("--target", help="e.g. a task id")
    audit.set_defaults(fn=cmd_audit)
    screen = sub.add_parser("screen", help="screen awareness: on, off, or look now")
    screen.add_argument("action", choices=["on", "off", "look"])
    screen.add_argument("question", nargs="?", help="look: what to find out")
    screen.set_defaults(fn=cmd_screen)
    build = sub.add_parser("build", help="test and build a version (Godot export presets)")
    build.add_argument("project")
    build.add_argument("--preset", action="append", help="only this preset (repeatable)")
    build.add_argument("--ref", help="commit, branch or tag (default: the base branch)")
    build.add_argument("--version", help="version name (default: git describe)")
    build.add_argument("--write", action="store_true", help="let an agent write the changelog")
    build.set_defaults(fn=cmd_build)
    pub = sub.add_parser("publish-build", help="upload a finished build to itch.io or Steam")
    pub.add_argument("task_id")
    pub.add_argument("--steam", action="store_true", help="to Steam (steamcmd), not itch.io")
    pub.set_defaults(fn=cmd_publish_build)
    changelog = sub.add_parser("changelog", help="changes since the last tag")
    changelog.add_argument("project")
    changelog.add_argument("--since", help="tag or commit (default: the previous tag)")
    changelog.add_argument("--ref", default="HEAD")
    changelog.add_argument("--write", action="store_true", help="let an agent write it for players")
    changelog.set_defaults(fn=cmd_changelog)
    sec = sub.add_parser("security", help="security report, ports, scans of your hosts, deps")
    sec.add_argument(
        "what",
        nargs="?",
        default="report",
        choices=["report", "ports", "scan", "devices", "discover", "logs", "deps"],
    )
    sec.add_argument("target", nargs="?", help="scan: your host; deps: a project")
    sec.add_argument("--fix", action="store_true", help="deps: let an agent update them")
    sec.add_argument("--json", action="store_true")
    sec.set_defaults(fn=cmd_security)
    council = sub.add_parser("council", help="several agents answer, a moderator weighs them")
    council.add_argument("project", help="a project, or the question")
    council.add_argument("question", nargs="?")
    council.add_argument("--member", action="append", help="agents to ask (repeatable)")
    council.set_defaults(fn=cmd_council)
    res = sub.add_parser("research", help="a web research report (with sources)")
    res.add_argument("project", help="a project, or the topic")
    res.add_argument("topic", nargs="?")
    res.add_argument("-a", "--agent", help="an agent with web access")
    res.set_defaults(fn=cmd_research)
    card = sub.add_parser("scorecard", help="Dia's own numbers, week by week")
    card.add_argument("--weeks", type=int, default=8)
    card.add_argument("--json", action="store_true")
    card.set_defaults(fn=cmd_scorecard)
    bench_p = sub.add_parser("bench", help="a project's benchmark: run, compare, history")
    bench_p.add_argument("project")
    bench_p.add_argument("--ref", help="which commit (default: the base branch)")
    bench_p.add_argument("--history", type=int, nargs="?", const=20, metavar="N")
    bench_p.set_defaults(fn=cmd_bench)
    exp = sub.add_parser("experiment", help="try a change several ways and measure each")
    exp.add_argument("project")
    exp.add_argument("question", help='e.g. "rewrite the inventory as ECS: is it faster?"')
    exp.add_argument("-a", "--agent", action="append", help="a variant per agent (repeatable)")
    exp.add_argument("--approach", action="append", help="a variant per approach (repeatable)")
    exp.set_defaults(fn=cmd_experiment)
    lab = sub.add_parser("lab", help="run a command in a throwaway container")
    lab.add_argument("project", help="a project to copy in, or the command")
    lab.add_argument("command", nargs="?")
    lab.add_argument("--ref", help="which commit of the project (default: its base branch)")
    lab.add_argument("--image", help="container image ([lab] image)")
    lab.add_argument("--network", action="store_true", help="allow network access")
    lab.add_argument("--keep", action="store_true", help="keep the work directory")
    lab.set_defaults(fn=cmd_lab)
    red = sub.add_parser("redteam", help="hostile instructions in a throwaway repo: does Dia hold?")
    red.add_argument("-a", "--agent", action="append", help="only these agents (repeatable)")
    red.set_defaults(fn=cmd_redteam)
    sbx = sub.add_parser("sandbox", help="what agents see in the sandbox; do they start?")
    sbx.add_argument("action", choices=["check"])
    sbx.set_defaults(fn=cmd_sandbox)
    balance = sub.add_parser("balance", help="game balance from playtest data")
    balance.add_argument("project")
    balance.add_argument("--agent", action="store_true", help="an agent proposes changes")
    balance.set_defaults(fn=cmd_balance)
    analyze = sub.add_parser("analyze", help="Godot scenes/scripts/textures: likely problems")
    analyze.add_argument("project")
    analyze.add_argument("--agent", action="store_true", help="an agent reads and prioritises")
    analyze.set_defaults(fn=cmd_analyze)
    tidy = sub.add_parser("tidy", help="tidy Downloads: preview, then --apply; --undo")
    tidy.add_argument("folder", nargs="?", help="an allowed folder (default: Downloads)")
    tidy.add_argument("--apply", metavar="ID", help="move the files of a previewed plan")
    tidy.add_argument("--undo", nargs="?", const="last", metavar="ID", help="put them back")
    tidy.set_defaults(fn=cmd_tidy)
    rollback = sub.add_parser("rollback", help="undo a merged task (as a new task to merge)")
    rollback.add_argument("task_id")
    rollback.add_argument("--reason", help="why (kept in the decision log: dia why)")
    rollback.set_defaults(fn=cmd_rollback)
    why_p = sub.add_parser("why", help="why was something decided? decisions, notes, commits")
    why_p.add_argument("question", help='e.g. "dlaczego zrezygnowaliśmy z ECS?"')
    why_p.add_argument("-p", "--project")
    why_p.set_defaults(fn=cmd_why)
    prof = sub.add_parser("profile", help="your working style, learnt from your decisions")
    prof.add_argument("--update", action="store_true", help="draft an update (waits for you)")
    prof.add_argument("--accept", action="store_true", help="make the draft the profile")
    prof.add_argument("-a", "--agent", help="who drafts it ([profile] agent)")
    prof.set_defaults(fn=cmd_profile)
    con = sub.add_parser("contradictions", help="do the notes and docs still match the code?")
    con.add_argument("project")
    con.add_argument("-a", "--agent")
    con.set_defaults(fn=cmd_contradictions)
    imp = sub.add_parser("impact", help="what could break if this changes?")
    imp.add_argument("project")
    imp.add_argument("target", help="a path, file name or name (e.g. dash)")
    imp.add_argument("--agent", action="store_true", help="an agent reads the code and advises")
    imp.set_defaults(fn=cmd_impact)
    debt_p = sub.add_parser("debt", help="technical debt, ranked by cost and benefit")
    debt_p.add_argument("project")
    debt_p.add_argument("--deps", action="store_true", help="also audit dependencies")
    debt_p.add_argument("--fix", type=int, metavar="N", help="pay off item N as a task")
    debt_p.add_argument("-n", "--limit", type=int, default=20)
    debt_p.set_defaults(fn=cmd_debt)
    dbg = sub.add_parser("debug", help="a bug for a swarm: hypotheses checked by tests")
    dbg.add_argument("project", nargs="?")
    dbg.add_argument("bug", nargs="?")
    dbg.add_argument("-a", "--agent", action="append", help="agents to use (repeatable)")
    dbg.add_argument("--fix", metavar="ID", help="fix the confirmed cause of a debugging task")
    dbg.set_defaults(fn=cmd_debug)
    goal_p = sub.add_parser("goal", help="goals over weeks: milestones and weekly reviews")
    goal_p.add_argument("action", choices=["new", "list", "review", "approve", "close"])
    goal_p.add_argument("project", nargs="?", help="the project (new) or the goal's id")
    goal_p.add_argument("text", nargs="?", help="the goal (new)")
    goal_p.add_argument("--weeks", type=int, help="by when (new)")
    goal_p.set_defaults(fn=cmd_goal)
    work_p = sub.add_parser("work", help="start or stop work on a profile (apps, session)")
    work_p.add_argument("action", choices=["start", "stop", "list"])
    work_p.add_argument("name", nargs="?", help="profile or project (stop: the current one)")
    work_p.add_argument("--note", help="stop: a note for next time")
    work_p.add_argument("--no-apps", action="store_true", help="start: don't open the apps")
    work_p.set_defaults(fn=cmd_work)
    skill = sub.add_parser("skill", help="run a skill: weather, news, stocks, crypto, briefing...")
    skill.add_argument("name", nargs="?", help="the skill; without it, the list")
    skill.add_argument("args", nargs="*", help="key=value, or words for its first argument")
    skill.add_argument("-y", "--yes", action="store_true", help="confirm without asking")
    skill.set_defaults(fn=cmd_skill)
    sug = sub.add_parser("suggestions", help="what Dia would suggest, from its history")
    sug.add_argument("--check", action="store_true", help="look for new ones now")
    sug.add_argument("--accept", metavar="KEY")
    sug.add_argument("--dismiss", metavar="KEY")
    sug.set_defaults(fn=cmd_suggestions)
    dec = sub.add_parser("decisions", help="the decision log, newest first")
    dec.add_argument("-p", "--project")
    dec.add_argument("-n", "--limit", type=int, default=30)
    dec.set_defaults(fn=cmd_decisions)
    scenario = sub.add_parser("scenario", help="does it work? a test is written and run")
    scenario.add_argument("project")
    scenario.add_argument("scenario", help='e.g. "parrying an attack in the last 0.2 s"')
    scenario.add_argument("-a", "--agent", help="who writes the test")
    scenario.set_defaults(fn=cmd_scenario)
    prefs = sub.add_parser("preferences", help="how you like things done (Dia follows them)")
    prefs.add_argument("--add", metavar="TEXT", help="a preference to keep")
    prefs.add_argument("--accept", nargs="+", metavar="N", help="proposed ones to keep")
    prefs.add_argument("--reject", nargs="+", metavar="N", help="proposed ones to drop")
    prefs.add_argument("--remove", type=int, metavar="N", help="forget a kept one")
    prefs.set_defaults(fn=cmd_preferences)
    quiet = sub.add_parser("quiet", help="quiet mode: text answers only (on/off)")
    quiet.add_argument("state", choices=["on", "off"])
    quiet.set_defaults(fn=cmd_quiet)
    stop = sub.add_parser("stop", help="emergency stop: end all agents, start nothing new")
    stop.add_argument("--resume", action="store_true", help="resume after a stop")
    stop.set_defaults(fn=cmd_stop)
    sub.add_parser("resume", help="resume after an emergency stop").set_defaults(
        fn=cmd_stop, resume=True
    )
    mission = sub.add_parser("mission", help="give Dia a goal: it plans, delegates and tests")
    mission.add_argument("project", nargs="?")
    mission.add_argument("goal", nargs="?")
    mission.add_argument("--calls", type=int, help="budget: agent calls")
    mission.add_argument("--minutes", type=float, help="budget: agent minutes")
    mission.add_argument("--priority", default="normal", choices=["low", "normal", "high"])
    mission.add_argument("--start", metavar="ID", help="start or continue a mission")
    mission.add_argument("--cancel", metavar="ID", help="start no further steps")
    mission.add_argument("-y", "--yes", action="store_true", help="run without asking")
    mission.set_defaults(fn=cmd_mission)
    remember = sub.add_parser("remember", help="add a fact to a project's memory note")
    remember.add_argument("project")
    remember.add_argument("fact")
    remember.set_defaults(fn=cmd_remember)
    learned = sub.add_parser("learned", help="facts Dia proposes to remember ([memory] learn)")
    learned.add_argument("task_id", nargs="?")
    learned.add_argument("--accept", nargs="+", metavar="N", help="numbers to keep, or 'all'")
    learned.add_argument("--reject", nargs="+", metavar="N", help="numbers to drop, or 'all'")
    learned.set_defaults(fn=cmd_learned)
    howto = sub.add_parser("howto", help="how-tos the agents follow (procedural memory)")
    howto.add_argument("task_id", nargs="?", help="write one from how this task was done")
    howto.add_argument("--save", action="store_true", help="keep the proposed how-to")
    howto.set_defaults(fn=cmd_howto)
    limits = sub.add_parser("limits", help="agents that are out of their usage limit")
    limits.add_argument("--clear", metavar="AGENT", help="forget an agent's limit ('all': every)")
    limits.set_defaults(fn=cmd_limits)
    run = sub.add_parser("run", help="give a task to an agent in an isolated worktree")
    run.add_argument("project")
    run.add_argument("prompt")
    run.add_argument("-a", "--agent", help="configured agent name (default: project/global)")
    run.add_argument("--read-only", action="store_true", help="analyse only, no file changes")
    run.add_argument("--no-tests", action="store_true", help="skip the project's test command")
    run.add_argument("--no-memory", action="store_true", help="don't use or update memory")
    run.add_argument("--review", action="store_true", help="have another agent review the changes")
    run.set_defaults(fn=cmd_run)

    tasks = sub.add_parser("tasks", help="list recent tasks")
    tasks.add_argument("-p", "--project")
    tasks.add_argument("-n", "--limit", type=int, default=20)
    tasks.set_defaults(fn=cmd_tasks)

    memory = sub.add_parser("memory", help="inspect memory").add_subparsers(
        dest="memory_command", required=True
    )
    search = memory.add_parser("search", help="notes an agent would get for this query")
    search.add_argument("query")
    search.add_argument("-n", "--limit", type=int, default=5)
    search.set_defaults(fn=cmd_memory_search)
    memory.add_parser("index", help="build the semantic index ([memory] semantic)").set_defaults(
        fn=cmd_memory_index
    )

    plan = sub.add_parser("plan", help="plan work across several agents, confirm, then run it")
    plan.add_argument("project", nargs="?")
    plan.add_argument("goal", nargs="?")
    plan.add_argument(
        "-p", "--pipeline", help="use a [pipelines.<name>] recipe instead of a planner"
    )
    plan.add_argument("--planner", help="agent that proposes the plan (default: [plans] planner)")
    plan.add_argument("--start", metavar="ID", help="run a plan created earlier")
    plan.add_argument("-y", "--yes", action="store_true", help="run without asking")
    plan.add_argument("--review", action="store_true", help="review the result")
    plan.add_argument("--no-memory", action="store_true", help="don't use or update memory")
    plan.set_defaults(fn=cmd_plan)

    review = sub.add_parser("review", help="have another agent review a task's changes")
    review.add_argument("task_id")
    review.add_argument(
        "-a", "--agent", help="reviewer (default: [review] reviewer or another agent)"
    )
    review.add_argument("-r", "--rounds", type=int, help="fix rounds after 'changes requested'")
    review.set_defaults(fn=cmd_review)

    for name, fn, help_text in [
        ("diff", cmd_diff, "show a task's changes"),
        ("merge", cmd_merge, "merge a finished task's branch into its base branch"),
        ("publish", cmd_publish, "push a task's branch and open a pull/merge request"),
        ("discard", cmd_discard, "delete a task's branch and worktree"),
    ]:
        action = sub.add_parser(name, help=help_text)
        action.add_argument("task_id")
        if name in ("merge", "discard"):
            action.add_argument("--reason", help="why (kept in the decision log: dia why)")
        if name == "merge":
            action.add_argument(
                "--override", metavar="WHY", help="merge despite the quality guards, and why"
            )
        action.set_defaults(fn=fn)

    say = sub.add_parser("say", help="ask or tell Dia something in your own words")
    say.add_argument("text")
    say.add_argument("-b", "--brain", help="use only this brain (default: the configured chain)")
    say.add_argument("--dry-run", action="store_true", help="only show how it was understood")
    say.add_argument("--no-memory", action="store_true", help="don't use or update memory")
    say.add_argument("-y", "--yes", action="store_true", help="run a proposed plan without asking")
    say.set_defaults(fn=cmd_say)

    voice = sub.add_parser("voice", help="voice control (bind `dia voice toggle` to a shortcut)")
    voice.add_argument(
        "action",
        choices=[
            "toggle",
            "start",
            "stop",
            "cancel",
            "ping",
            "listen",
            "speak",
            "enroll",
            "speakers",
            "forget",
        ],
        help="toggle/start/stop/cancel/ping control `dia serve`; listen/speak test mic and "
        "voice; enroll/speakers/forget manage the voices Dia recognises",
    )
    voice.add_argument("text", nargs="?", help="speak: what to say; enroll/forget: the name")
    voice.add_argument("-s", "--seconds", type=float, default=5, help="listen: how long to record")
    voice.set_defaults(fn=cmd_voice)

    ci = sub.add_parser("ci", help="CI status of a published task (and fix it)")
    ci.add_argument("task_id")
    ci.add_argument("-w", "--watch", action="store_true", help="wait until CI finishes")
    ci.add_argument("--fix", action="store_true", help="if CI failed, have the author fix it")
    ci.add_argument("--interval", type=float, default=30)
    ci.set_defaults(fn=cmd_ci)

    launch = sub.add_parser("launch", help="start a project (e.g. run the Godot game)")
    launch.add_argument("project")
    launch.set_defaults(fn=cmd_launch)

    runtime_parser = sub.add_parser("runtime", help="desktop services and login policy")
    runtime_parser.add_argument(
        "action", choices=["status", "start", "stop", "restart", "configure"]
    )
    runtime_parser.add_argument("component", nargs="?", choices=["dia", "ollama"], default="dia")
    runtime_parser.add_argument("--autostart", action=argparse.BooleanOptionalAction, default=None)
    runtime_parser.add_argument("--warmup", action=argparse.BooleanOptionalAction, default=None)
    runtime_parser.add_argument("--ollama", choices=["with-dia", "independent", "manual"])
    runtime_parser.add_argument("--report", action="store_true", help=argparse.SUPPRESS)
    runtime_parser.set_defaults(fn=cmd_runtime)

    svc = sub.add_parser("service", help="run `dia serve` as a systemd user service")
    svc.add_argument("action", choices=["install", "uninstall", "status", "logs"])
    svc.add_argument("--no-start", action="store_true", help="install: enable but don't start")
    svc.set_defaults(fn=cmd_service)

    comments = sub.add_parser("comments", help="review comments on a published task's PR/MR")
    comments.add_argument("task_id")
    comments.add_argument("--fix", action="store_true", help="let the author address them")
    comments.set_defaults(fn=cmd_comments)

    ui = sub.add_parser("ui", help="address of the web UI (with the sign-in token)")
    ui.add_argument("--open", action="store_true", help="open it in the browser")
    ui.add_argument("--token", action="store_true", help="print only the API token")
    ui.set_defaults(fn=cmd_ui)

    secret = sub.add_parser("secret", help="API keys and tokens (stored in ~/.config/dia/env)")
    secret.add_argument("action", choices=["set", "list", "rm"])
    secret.add_argument("name", nargs="?", help="e.g. ELEVENLABS_API_KEY")
    secret.set_defaults(fn=cmd_secret)
    mobile = sub.add_parser("mobile", help="pair your phone with Dia (see docs/MOBILE.md)")
    mobile.add_argument("action", choices=["pair", "list", "revoke"])
    mobile.add_argument("device", nargs="?", help="revoke: the device's id or name")
    mobile.add_argument("--name", default="phone", help="pair: a name for the device")
    mobile.set_defaults(fn=cmd_mobile)
    for name, help_text in (
        ("app", "start everything Dia needs (if not running) and open its window"),
        ("up", "the same as `dia app`: one command to start Dia"),
    ):
        app = sub.add_parser(name, help=help_text)
        app.add_argument("--browser", action="store_true", help="a browser window, not Dia's own")
        app.add_argument("--background", action="store_true", help="start Dia, open no window")
        app.add_argument("--view", help="open this tab",
                         choices=["inbox", "tasks", "missions", "chat", "cli", "memory",
                                  "status", "usage", "settings"])  # fmt: skip
        app.add_argument("--task", metavar="ID", help="open this task")
        app.set_defaults(fn=cmd_app)
    shortcut = sub.add_parser("shortcut", help="Dia in the app menu / on the desktop / at login")
    shortcut.add_argument("action", choices=["install", "uninstall"])
    shortcut.add_argument("--no-desktop", action="store_true", help="no icon on the desktop")
    shortcut.add_argument("--autostart", action="store_true", help="start Dia at login")
    shortcut.set_defaults(fn=cmd_shortcut)

    plasmoid = sub.add_parser("plasmoid", help="install the KDE Plasma 6 panel widget")
    plasmoid.add_argument("action", choices=["install", "uninstall"])
    plasmoid.set_defaults(fn=cmd_plasmoid)

    sub.add_parser("serve", help="run the configured channels (e.g. Discord bot)").set_defaults(
        fn=cmd_serve
    )

    show = sub.add_parser("show", help="show one task")
    show.add_argument("task_id")
    show.add_argument("--tests", action="store_true", help="print the full output of the tests")
    show.set_defaults(fn=cmd_show)
    return parser


def version_lines(config: Config | None = None) -> list[str]:
    import platform

    lines = [f"Dia {__version__}", f"Python {platform.python_version()} · {sys.executable}"]
    if config is not None:
        lines.append(f"config: {config.source or '-'}")
        lines.append(f"data:   {config.data_dir}")
    return lines


def cmd_setup(args: argparse.Namespace) -> int:
    """The setup wizard: agents, projects, memory, shortcuts; writes the config."""
    from dia import setup

    return setup.run(assume=args.yes, target=args.config)


def cmd_version(args: argparse.Namespace) -> int:
    """The version (and where this Dia lives), with Dia's ring in a terminal."""
    from dia.banner import banner

    try:
        config: Config | None = load_config(args.config)
    except ConfigError:
        config = None
    from dia.about import snapshot

    print(banner(version_lines(config)))
    info = snapshot(config)
    print(f"\n{info['author']}  {info['website']}\n{info['github']}\n{info['email']}")
    extras = [
        f"{row['name']:<16} {row['version']}" + (f"  {row['detail']}" if row.get("detail") else "")
        for row in info["components"]
        if row["name"] not in ("Dia", "Python")
    ]
    if extras:
        print("\n" + "\n".join(extras))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from dia.secrets import load_into_environment

    load_into_environment()
    if getattr(args, "fn", None) is cmd_secret:  # works without a config
        return cmd_secret(args)
    if getattr(args, "fn", None) is cmd_version:
        return cmd_version(args)
    if getattr(args, "fn", None) is cmd_setup:  # it writes the config
        return cmd_setup(args)
    try:
        config = load_config(args.config)
        return asyncio.run(args.fn(config, args))
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except TaskActionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
