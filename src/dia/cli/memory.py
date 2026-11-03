"""`dia memory` commands."""

from __future__ import annotations

import argparse
import asyncio
import sys

from dia.cli._common import print_facts
from dia.core.config import Config, ConfigError
from dia.core.orchestrator import Orchestrator, TaskActionError


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


async def cmd_why(config: Config, args: argparse.Namespace) -> int:
    """Why was something decided: decisions, what came of them, notes, commits."""
    from dia.knowledge.decisions import describe, why

    print(describe(await why(Orchestrator(config), args.question, args.project)))
    return 0


async def cmd_profile(config: Config, args: argparse.Namespace) -> int:
    """Your working style, learnt from your decisions: show, draft an update, accept."""
    from dia.knowledge import profile

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
    from dia.quality.contradictions import check

    print("an agent compares the notes and docs with the code ...", file=sys.stderr)
    task = await check(Orchestrator(config), args.project, args.agent)
    print(task.summary or task.error)
    if task.details.get("learn"):
        print(f"\naccept the corrections: dia learned {task.id} --accept all", file=sys.stderr)
    return 0 if task.status == "done" else 1


async def cmd_decisions(config: Config, args: argparse.Namespace) -> int:
    from dia.knowledge.decisions import describe

    rows = Orchestrator(config, use_memory=False).store.decisions(args.project, limit=args.limit)
    found = {"terms": ["*"], "decisions": [{**r, "consequences": []} for r in rows]}
    print(describe({**found, "notes": [], "commits": []}))
    return 0


async def cmd_preferences(config: Config, args: argparse.Namespace) -> int:
    """What Dia knows about how you like things done."""
    from dia.knowledge.preferences import Preferences
    from dia.persona import add_preference

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


async def cmd_remember(config: Config, args: argparse.Namespace) -> int:
    try:
        Orchestrator(config).remember(args.project, args.fact)
    except (TaskActionError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"remembered for {args.project}: {args.fact}")
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


def add_why(sub: argparse._SubParsersAction) -> None:
    why_p = sub.add_parser("why", help="why was something decided? decisions, notes, commits")
    why_p.add_argument("question", help='e.g. "dlaczego zrezygnowaliśmy z ECS?"')
    why_p.add_argument("-p", "--project")
    why_p.set_defaults(fn=cmd_why)


def add_profile(sub: argparse._SubParsersAction) -> None:
    prof = sub.add_parser("profile", help="your working style, learnt from your decisions")
    prof.add_argument("--update", action="store_true", help="draft an update (waits for you)")
    prof.add_argument("--accept", action="store_true", help="make the draft the profile")
    prof.add_argument("-a", "--agent", help="who drafts it ([profile] agent)")
    prof.set_defaults(fn=cmd_profile)


def add_contradictions(sub: argparse._SubParsersAction) -> None:
    con = sub.add_parser("contradictions", help="do the notes and docs still match the code?")
    con.add_argument("project")
    con.add_argument("-a", "--agent")
    con.set_defaults(fn=cmd_contradictions)


def add_decisions(sub: argparse._SubParsersAction) -> None:
    dec = sub.add_parser("decisions", help="the decision log, newest first")
    dec.add_argument("-p", "--project")
    dec.add_argument("-n", "--limit", type=int, default=30)
    dec.set_defaults(fn=cmd_decisions)


def add_preferences(sub: argparse._SubParsersAction) -> None:
    prefs = sub.add_parser("preferences", help="how you like things done (Dia follows them)")
    prefs.add_argument("--add", metavar="TEXT", help="a preference to keep")
    prefs.add_argument("--accept", nargs="+", metavar="N", help="proposed ones to keep")
    prefs.add_argument("--reject", nargs="+", metavar="N", help="proposed ones to drop")
    prefs.add_argument("--remove", type=int, metavar="N", help="forget a kept one")
    prefs.set_defaults(fn=cmd_preferences)


def add_remember(sub: argparse._SubParsersAction) -> None:
    remember = sub.add_parser("remember", help="add a fact to a project's memory note")
    remember.add_argument("project")
    remember.add_argument("fact")
    remember.set_defaults(fn=cmd_remember)


def add_learned(sub: argparse._SubParsersAction) -> None:
    learned = sub.add_parser("learned", help="facts Dia proposes to remember ([memory] learn)")
    learned.add_argument("task_id", nargs="?")
    learned.add_argument("--accept", nargs="+", metavar="N", help="numbers to keep, or 'all'")
    learned.add_argument("--reject", nargs="+", metavar="N", help="numbers to drop, or 'all'")
    learned.set_defaults(fn=cmd_learned)


def add_howto(sub: argparse._SubParsersAction) -> None:
    howto = sub.add_parser("howto", help="how-tos the agents follow (procedural memory)")
    howto.add_argument("task_id", nargs="?", help="write one from how this task was done")
    howto.add_argument("--save", action="store_true", help="keep the proposed how-to")
    howto.set_defaults(fn=cmd_howto)


def add_memory(sub: argparse._SubParsersAction) -> None:
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


COMMANDS = {
    "why": add_why,
    "profile": add_profile,
    "contradictions": add_contradictions,
    "decisions": add_decisions,
    "preferences": add_preferences,
    "remember": add_remember,
    "learned": add_learned,
    "howto": add_howto,
    "memory": add_memory,
}
