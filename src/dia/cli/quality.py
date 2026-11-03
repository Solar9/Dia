"""`dia quality` commands."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dia.cli._common import finish_learning, print_report
from dia.core.config import Config, ConfigError
from dia.core.orchestrator import Orchestrator, TaskActionError
from dia.core.store import TaskRecord
from dia.core.workspace import GitError, git


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


async def cmd_scorecard(config: Config, args: argparse.Namespace) -> int:
    """Dia's own numbers, week by week: is it getting better?"""
    from dia.quality.scorecard import format_table, scorecard

    rows = scorecard(Orchestrator(config, use_memory=False).store, args.weeks)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(format_table(rows))
    return 0


async def cmd_bench(config: Config, args: argparse.Namespace) -> int:
    """Run a project's benchmark, compare with the last result; or its history."""
    from dia.quality.benchmarks import bench, compare, describe, options

    dia = Orchestrator(config, use_memory=False)
    project = config.project(args.project)
    if args.history:
        for row in dia.store.benchmarks(project.name, limit=args.history):
            values = ", ".join(f"{k}={v:g}" for k, v in row["metrics"].items())
            print(f"{row['at'][:16]}  {row['sha'][:10]}  {row['ref'] or '-':12} {values}")
        return 0
    from dia.quality.benchmarks import base_branch

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
    from dia.quality.experiments import run_experiment

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
    from dia.quality.lab import Lab

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
    from dia.quality import redteam

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
    from dia.core import sandbox
    from dia.core.workspace import run

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
        if box is None:  # switched off while we looked
            continue
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


async def cmd_impact(config: Config, args: argparse.Namespace) -> int:
    """What could break if this changes: dependents, files changed with it, tests."""
    from dia.quality.impact import impact

    _, text = await impact(Orchestrator(config), args.project, args.target, args.agent)
    print(text)
    return 0


async def cmd_debt(config: Config, args: argparse.Namespace) -> int:
    """The technical debt register; --fix N pays an item off as a task."""
    from dia.quality import debt

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
    from dia.work import swarm

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


def add_check(sub: argparse._SubParsersAction) -> None:
    check = sub.add_parser("check", help="test a commit of a project (what `[watch]` does)")
    check.add_argument("project")
    check.add_argument("ref", nargs="?", default="HEAD")
    check.set_defaults(fn=cmd_check)


def add_fix_build(sub: argparse._SubParsersAction) -> None:
    fix_build = sub.add_parser("fix-build", help="let an agent fix what a failed check broke")
    fix_build.add_argument("task_id")
    fix_build.set_defaults(fn=cmd_fix_build)


def add_audit(sub: argparse._SubParsersAction) -> None:
    audit = sub.add_parser("audit", help="who did what (merges, tasks, settings...)")
    audit.add_argument("-n", "--limit", type=int, default=50)
    audit.add_argument("--action", help="e.g. task.merge, or a prefix: task.")
    audit.add_argument("--target", help="e.g. a task id")
    audit.set_defaults(fn=cmd_audit)


def add_security(sub: argparse._SubParsersAction) -> None:
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


def add_scorecard(sub: argparse._SubParsersAction) -> None:
    card = sub.add_parser("scorecard", help="Dia's own numbers, week by week")
    card.add_argument("--weeks", type=int, default=8)
    card.add_argument("--json", action="store_true")
    card.set_defaults(fn=cmd_scorecard)


def add_bench(sub: argparse._SubParsersAction) -> None:
    bench_p = sub.add_parser("bench", help="a project's benchmark: run, compare, history")
    bench_p.add_argument("project")
    bench_p.add_argument("--ref", help="which commit (default: the base branch)")
    bench_p.add_argument("--history", type=int, nargs="?", const=20, metavar="N")
    bench_p.set_defaults(fn=cmd_bench)


def add_experiment(sub: argparse._SubParsersAction) -> None:
    exp = sub.add_parser("experiment", help="try a change several ways and measure each")
    exp.add_argument("project")
    exp.add_argument("question", help='e.g. "rewrite the inventory as ECS: is it faster?"')
    exp.add_argument("-a", "--agent", action="append", help="a variant per agent (repeatable)")
    exp.add_argument("--approach", action="append", help="a variant per approach (repeatable)")
    exp.set_defaults(fn=cmd_experiment)


def add_lab(sub: argparse._SubParsersAction) -> None:
    lab = sub.add_parser("lab", help="run a command in a throwaway container")
    lab.add_argument("project", help="a project to copy in, or the command")
    lab.add_argument("command", nargs="?")
    lab.add_argument("--ref", help="which commit of the project (default: its base branch)")
    lab.add_argument("--image", help="container image ([lab] image)")
    lab.add_argument("--network", action="store_true", help="allow network access")
    lab.add_argument("--keep", action="store_true", help="keep the work directory")
    lab.set_defaults(fn=cmd_lab)


def add_redteam(sub: argparse._SubParsersAction) -> None:
    red = sub.add_parser("redteam", help="hostile instructions in a throwaway repo: does Dia hold?")
    red.add_argument("-a", "--agent", action="append", help="only these agents (repeatable)")
    red.set_defaults(fn=cmd_redteam)


def add_sandbox(sub: argparse._SubParsersAction) -> None:
    sbx = sub.add_parser("sandbox", help="what agents see in the sandbox; do they start?")
    sbx.add_argument("action", choices=["check"])
    sbx.set_defaults(fn=cmd_sandbox)


def add_impact(sub: argparse._SubParsersAction) -> None:
    imp = sub.add_parser("impact", help="what could break if this changes?")
    imp.add_argument("project")
    imp.add_argument("target", help="a path, file name or name (e.g. dash)")
    imp.add_argument("--agent", action="store_true", help="an agent reads the code and advises")
    imp.set_defaults(fn=cmd_impact)


def add_debt(sub: argparse._SubParsersAction) -> None:
    debt_p = sub.add_parser("debt", help="technical debt, ranked by cost and benefit")
    debt_p.add_argument("project")
    debt_p.add_argument("--deps", action="store_true", help="also audit dependencies")
    debt_p.add_argument("--fix", type=int, metavar="N", help="pay off item N as a task")
    debt_p.add_argument("-n", "--limit", type=int, default=20)
    debt_p.set_defaults(fn=cmd_debt)


def add_debug(sub: argparse._SubParsersAction) -> None:
    dbg = sub.add_parser("debug", help="a bug for a swarm: hypotheses checked by tests")
    dbg.add_argument("project", nargs="?")
    dbg.add_argument("bug", nargs="?")
    dbg.add_argument("-a", "--agent", action="append", help="agents to use (repeatable)")
    dbg.add_argument("--fix", metavar="ID", help="fix the confirmed cause of a debugging task")
    dbg.set_defaults(fn=cmd_debug)


COMMANDS = {
    "check": add_check,
    "fix-build": add_fix_build,
    "audit": add_audit,
    "security": add_security,
    "scorecard": add_scorecard,
    "bench": add_bench,
    "experiment": add_experiment,
    "lab": add_lab,
    "redteam": add_redteam,
    "sandbox": add_sandbox,
    "impact": add_impact,
    "debt": add_debt,
    "debug": add_debug,
}
