"""`dia release` commands."""

from __future__ import annotations

import argparse
import sys

from dia.core.config import Config
from dia.core.orchestrator import Orchestrator, TaskActionError


async def cmd_build(config: Config, args: argparse.Namespace) -> int:
    """Test and build a version of a project (Godot export presets)."""
    from dia.release.release import Releases

    task = await Releases(Orchestrator(config)).build(
        args.project, args.preset or None, args.ref, args.version, write_changelog=args.write
    )
    print(task.summary or task.error)
    if task.status == "done":
        print(f"\nin {task.details['output']}")
    return 0 if task.status == "done" else 1


async def cmd_publish_build(config: Config, args: argparse.Namespace) -> int:
    from dia.release.release import Releases

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
    from dia.release.release import Releases

    print(
        await Releases(Orchestrator(config)).changelog(
            args.project, since=args.since, ref=args.ref, write=args.write
        )
    )
    return 0


def add_build(sub: argparse._SubParsersAction) -> None:
    build = sub.add_parser("build", help="test and build a version (Godot export presets)")
    build.add_argument("project")
    build.add_argument("--preset", action="append", help="only this preset (repeatable)")
    build.add_argument("--ref", help="commit, branch or tag (default: the base branch)")
    build.add_argument("--version", help="version name (default: git describe)")
    build.add_argument("--write", action="store_true", help="let an agent write the changelog")
    build.set_defaults(fn=cmd_build)


def add_publish_build(sub: argparse._SubParsersAction) -> None:
    pub = sub.add_parser("publish-build", help="upload a finished build to itch.io or Steam")
    pub.add_argument("task_id")
    pub.add_argument("--steam", action="store_true", help="to Steam (steamcmd), not itch.io")
    pub.set_defaults(fn=cmd_publish_build)


def add_changelog(sub: argparse._SubParsersAction) -> None:
    changelog = sub.add_parser("changelog", help="changes since the last tag")
    changelog.add_argument("project")
    changelog.add_argument("--since", help="tag or commit (default: the previous tag)")
    changelog.add_argument("--ref", default="HEAD")
    changelog.add_argument("--write", action="store_true", help="let an agent write it for players")
    changelog.set_defaults(fn=cmd_changelog)


COMMANDS = {
    "build": add_build,
    "publish-build": add_publish_build,
    "changelog": add_changelog,
}
