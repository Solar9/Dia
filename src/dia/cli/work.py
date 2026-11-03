"""`dia work` commands."""

from __future__ import annotations

import argparse
import sys

from dia.cli._common import print_report, skill_args
from dia.core.config import Config
from dia.core.orchestrator import Orchestrator, TaskActionError


async def cmd_schedule(config: Config, args: argparse.Namespace) -> int:
    from dia.work.schedule import Scheduler, Schedules

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
        wanted = next((j for j in schedules.list() if j.id == args.cron), None)
        if not wanted:
            print(f"no schedule {args.cron}", file=sys.stderr)
            return 1
        job = wanted
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
    from dia.work.issues import IssueWatcher

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


async def cmd_goal(config: Config, args: argparse.Namespace) -> int:
    """Goals over weeks: milestones, weekly reviews, the next mission for your approval."""
    from dia.work import goals

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
            reviewed = dia.store.get(goal_id)
            if reviewed is None:
                print(f"error: no goal {goal_id}", file=sys.stderr)
                return 1
            print(goals.describe(reviewed))
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
    from dia.work import work

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


async def cmd_skill(config: Config, args: argparse.Namespace) -> int:
    """Run one skill (weather, crypto, briefing...) or list them."""
    from dia.skills import NeedsConfirmation, enabled_skills

    dia = Orchestrator(config)
    skills = enabled_skills(dia)
    if not args.name:
        for name, listed in sorted(skills.items()):
            spec = " ".join(f"[{k}=...]" for k in listed.args)
            print(f"{name:12} {listed.description}" + (f"\n{'':12} {spec}" if spec else ""))
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
    from dia.knowledge.suggestions import Suggestions

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


async def cmd_mission(config: Config, args: argparse.Namespace) -> int:
    """Create, run, continue, cancel or list missions."""
    from dia.work.missions import Missions

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


def add_schedule(sub: argparse._SubParsersAction) -> None:
    sched = sub.add_parser("schedule", help="recurring jobs: briefing, checks, tasks")
    sched.add_argument("action", choices=["list", "add", "rm", "run"], nargs="?", default="list")
    sched.add_argument("cron", nargs="?", help="add: cron expression; rm/run: the job's id")
    sched.add_argument("text", nargs="?", help="add: what to ask Dia (or a skill with --skill)")
    sched.add_argument("--skill", action="store_true", help="add: text is a skill name")
    sched.add_argument("--speak", action="store_true", help="add: also say the answer aloud")
    sched.set_defaults(fn=cmd_schedule)


def add_issues(sub: argparse._SubParsersAction) -> None:
    issues = sub.add_parser("issues", help="import issues labelled for Dia as plans")
    issues.add_argument("project", nargs="?")
    issues.set_defaults(fn=cmd_issues)


def add_goal(sub: argparse._SubParsersAction) -> None:
    goal_p = sub.add_parser("goal", help="goals over weeks: milestones and weekly reviews")
    goal_p.add_argument("action", choices=["new", "list", "review", "approve", "close"])
    goal_p.add_argument("project", nargs="?", help="the project (new) or the goal's id")
    goal_p.add_argument("text", nargs="?", help="the goal (new)")
    goal_p.add_argument("--weeks", type=int, help="by when (new)")
    goal_p.set_defaults(fn=cmd_goal)


def add_work(sub: argparse._SubParsersAction) -> None:
    work_p = sub.add_parser("work", help="start or stop work on a profile (apps, session)")
    work_p.add_argument("action", choices=["start", "stop", "list"])
    work_p.add_argument("name", nargs="?", help="profile or project (stop: the current one)")
    work_p.add_argument("--note", help="stop: a note for next time")
    work_p.add_argument("--no-apps", action="store_true", help="start: don't open the apps")
    work_p.set_defaults(fn=cmd_work)


def add_skill(sub: argparse._SubParsersAction) -> None:
    skill = sub.add_parser("skill", help="run a skill: weather, news, stocks, crypto, briefing...")
    skill.add_argument("name", nargs="?", help="the skill; without it, the list")
    skill.add_argument("args", nargs="*", help="key=value, or words for its first argument")
    skill.add_argument("-y", "--yes", action="store_true", help="confirm without asking")
    skill.set_defaults(fn=cmd_skill)


def add_suggestions(sub: argparse._SubParsersAction) -> None:
    sug = sub.add_parser("suggestions", help="what Dia would suggest, from its history")
    sug.add_argument("--check", action="store_true", help="look for new ones now")
    sug.add_argument("--accept", metavar="KEY")
    sug.add_argument("--dismiss", metavar="KEY")
    sug.set_defaults(fn=cmd_suggestions)


def add_mission(sub: argparse._SubParsersAction) -> None:
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


COMMANDS = {
    "schedule": add_schedule,
    "issues": add_issues,
    "goal": add_goal,
    "work": add_work,
    "skill": add_skill,
    "suggestions": add_suggestions,
    "mission": add_mission,
}
