"""`dia tasks` commands."""

from __future__ import annotations

import argparse
import asyncio
import sys

from dia.agents import Mode
from dia.cli._common import _call_serve, finish_learning, print_report
from dia.core.config import Config
from dia.core.orchestrator import Orchestrator, TaskActionError


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
    from dia.quality.simulation import describe

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
    task = dia.store.get(args.task_id)
    pending = task.details.get("comments_pending", []) if task else []
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


def add_rollback(sub: argparse._SubParsersAction) -> None:
    rollback = sub.add_parser("rollback", help="undo a merged task (as a new task to merge)")
    rollback.add_argument("task_id")
    rollback.add_argument("--reason", help="why (kept in the decision log: dia why)")
    rollback.set_defaults(fn=cmd_rollback)


def add_quiet(sub: argparse._SubParsersAction) -> None:
    quiet = sub.add_parser("quiet", help="quiet mode: text answers only (on/off)")
    quiet.add_argument("state", choices=["on", "off"])
    quiet.set_defaults(fn=cmd_quiet)


def add_stop(sub: argparse._SubParsersAction) -> None:
    stop = sub.add_parser("stop", help="emergency stop: end all agents, start nothing new")
    stop.add_argument("--resume", action="store_true", help="resume after a stop")
    stop.set_defaults(fn=cmd_stop)


def add_resume(sub: argparse._SubParsersAction) -> None:
    sub.add_parser("resume", help="resume after an emergency stop").set_defaults(
        fn=cmd_stop, resume=True
    )


def add_run(sub: argparse._SubParsersAction) -> None:
    run = sub.add_parser("run", help="give a task to an agent in an isolated worktree")
    run.add_argument("project")
    run.add_argument("prompt")
    run.add_argument("-a", "--agent", help="configured agent name (default: project/global)")
    run.add_argument("--read-only", action="store_true", help="analyse only, no file changes")
    run.add_argument("--no-tests", action="store_true", help="skip the project's test command")
    run.add_argument("--no-memory", action="store_true", help="don't use or update memory")
    run.add_argument("--review", action="store_true", help="have another agent review the changes")
    run.set_defaults(fn=cmd_run)


def add_tasks(sub: argparse._SubParsersAction) -> None:
    tasks = sub.add_parser("tasks", help="list recent tasks")
    tasks.add_argument("-p", "--project")
    tasks.add_argument("-n", "--limit", type=int, default=20)
    tasks.set_defaults(fn=cmd_tasks)


def add_plan(sub: argparse._SubParsersAction) -> None:
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


def add_review(sub: argparse._SubParsersAction) -> None:
    review = sub.add_parser("review", help="have another agent review a task's changes")
    review.add_argument("task_id")
    review.add_argument(
        "-a", "--agent", help="reviewer (default: [review] reviewer or another agent)"
    )
    review.add_argument("-r", "--rounds", type=int, help="fix rounds after 'changes requested'")
    review.set_defaults(fn=cmd_review)


def add_diff(sub: argparse._SubParsersAction) -> None:
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


def add_ci(sub: argparse._SubParsersAction) -> None:
    ci = sub.add_parser("ci", help="CI status of a published task (and fix it)")
    ci.add_argument("task_id")
    ci.add_argument("-w", "--watch", action="store_true", help="wait until CI finishes")
    ci.add_argument("--fix", action="store_true", help="if CI failed, have the author fix it")
    ci.add_argument("--interval", type=float, default=30)
    ci.set_defaults(fn=cmd_ci)


def add_launch(sub: argparse._SubParsersAction) -> None:
    launch = sub.add_parser("launch", help="start a project (e.g. run the Godot game)")
    launch.add_argument("project")
    launch.set_defaults(fn=cmd_launch)


def add_comments(sub: argparse._SubParsersAction) -> None:
    comments = sub.add_parser("comments", help="review comments on a published task's PR/MR")
    comments.add_argument("task_id")
    comments.add_argument("--fix", action="store_true", help="let the author address them")
    comments.set_defaults(fn=cmd_comments)


def add_show(sub: argparse._SubParsersAction) -> None:
    show = sub.add_parser("show", help="show one task")
    show.add_argument("task_id")
    show.add_argument("--tests", action="store_true", help="print the full output of the tests")
    show.set_defaults(fn=cmd_show)


COMMANDS = {
    "rollback": add_rollback,
    "quiet": add_quiet,
    "stop": add_stop,
    "resume": add_resume,
    "run": add_run,
    "tasks": add_tasks,
    "plan": add_plan,
    "review": add_review,
    "diff": add_diff,
    "ci": add_ci,
    "launch": add_launch,
    "comments": add_comments,
    "show": add_show,
}
