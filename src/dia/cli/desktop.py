"""`dia desktop` commands."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dia.core.config import Config
from dia.core.orchestrator import Orchestrator


async def cmd_screen(config: Config, args: argparse.Namespace) -> int:
    """Screen access on/off, or look now."""
    dia = Orchestrator(config, use_memory=False)
    if args.action in ("on", "off"):
        dia.set_screen(args.action == "on")
        print(f"screen access {args.action}")
        return 0
    from dia.desktop.screen import look

    try:
        print(await look(dia, args.question or ""))
    except PermissionError:
        print("screen access is off: dia screen on", file=sys.stderr)
        return 1
    return 0


async def cmd_balance(config: Config, args: argparse.Namespace) -> int:
    """Balance from playtest data ([projects.<name>] balance.data)."""
    from dia.release.balance import balance_report

    print(await balance_report(Orchestrator(config), args.project, args.agent))
    return 0


async def cmd_analyze(config: Config, args: argparse.Namespace) -> int:
    """Scenes, scripts and textures of a Godot project: likely problems."""
    from dia.release.godot_analysis import analyze_project

    print(await analyze_project(Orchestrator(config), args.project, args.agent))
    return 0


async def cmd_tidy(config: Config, args: argparse.Namespace) -> int:
    """Preview tidying a folder; --apply ID moves, --undo puts back."""
    from dia.desktop.tidy import Tidy, TidyError, summary

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


async def cmd_runtime(config: Config, args: argparse.Namespace) -> int:
    """Local control, also usable by the widget while the HTTP server is stopped."""
    from dia.desktop import runtime

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
    from dia.desktop import service

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


def cmd_secret(args: argparse.Namespace) -> int:
    """API keys and tokens in ~/.config/dia/env (mode 600); values are never shown."""
    from dia import secrets
    from dia.desktop.service import env_path

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


async def cmd_shortcut(config: Config, args: argparse.Namespace) -> int:
    """Dia in the application menu, on the desktop and (optionally) at login."""
    import subprocess

    from dia.desktop import desktop

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


def add_screen(sub: argparse._SubParsersAction) -> None:
    screen = sub.add_parser("screen", help="screen awareness: on, off, or look now")
    screen.add_argument("action", choices=["on", "off", "look"])
    screen.add_argument("question", nargs="?", help="look: what to find out")
    screen.set_defaults(fn=cmd_screen)


def add_balance(sub: argparse._SubParsersAction) -> None:
    balance = sub.add_parser("balance", help="game balance from playtest data")
    balance.add_argument("project")
    balance.add_argument("--agent", action="store_true", help="an agent proposes changes")
    balance.set_defaults(fn=cmd_balance)


def add_analyze(sub: argparse._SubParsersAction) -> None:
    analyze = sub.add_parser("analyze", help="Godot scenes/scripts/textures: likely problems")
    analyze.add_argument("project")
    analyze.add_argument("--agent", action="store_true", help="an agent reads and prioritises")
    analyze.set_defaults(fn=cmd_analyze)


def add_tidy(sub: argparse._SubParsersAction) -> None:
    tidy = sub.add_parser("tidy", help="tidy Downloads: preview, then --apply; --undo")
    tidy.add_argument("folder", nargs="?", help="an allowed folder (default: Downloads)")
    tidy.add_argument("--apply", metavar="ID", help="move the files of a previewed plan")
    tidy.add_argument("--undo", nargs="?", const="last", metavar="ID", help="put them back")
    tidy.set_defaults(fn=cmd_tidy)


def add_runtime(sub: argparse._SubParsersAction) -> None:
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


def add_service(sub: argparse._SubParsersAction) -> None:
    svc = sub.add_parser("service", help="run `dia serve` as a systemd user service")
    svc.add_argument("action", choices=["install", "uninstall", "status", "logs"])
    svc.add_argument("--no-start", action="store_true", help="install: enable but don't start")
    svc.set_defaults(fn=cmd_service)


def add_secret(sub: argparse._SubParsersAction) -> None:
    secret = sub.add_parser("secret", help="API keys and tokens (stored in ~/.config/dia/env)")
    secret.add_argument("action", choices=["set", "list", "rm"])
    secret.add_argument("name", nargs="?", help="e.g. ELEVENLABS_API_KEY")
    secret.set_defaults(fn=cmd_secret)


def add_shortcut(sub: argparse._SubParsersAction) -> None:
    shortcut = sub.add_parser("shortcut", help="Dia in the app menu / on the desktop / at login")
    shortcut.add_argument("action", choices=["install", "uninstall"])
    shortcut.add_argument("--no-desktop", action="store_true", help="no icon on the desktop")
    shortcut.add_argument("--autostart", action="store_true", help="start Dia at login")
    shortcut.set_defaults(fn=cmd_shortcut)


def add_plasmoid(sub: argparse._SubParsersAction) -> None:
    plasmoid = sub.add_parser("plasmoid", help="install the KDE Plasma 6 panel widget")
    plasmoid.add_argument("action", choices=["install", "uninstall"])
    plasmoid.set_defaults(fn=cmd_plasmoid)


COMMANDS = {
    "screen": add_screen,
    "balance": add_balance,
    "analyze": add_analyze,
    "tidy": add_tidy,
    "runtime": add_runtime,
    "service": add_service,
    "secret": add_secret,
    "shortcut": add_shortcut,
    "plasmoid": add_plasmoid,
}
