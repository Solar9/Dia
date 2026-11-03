"""The `dia` command line."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dia import __version__
from dia.cli import agents, desktop, memory, quality, release, serve, setup, tasks, voice, work
from dia.cli._common import skill_args  # noqa: F401  (re-exported: tests import it from dia.cli)
from dia.cli.desktop import cmd_secret
from dia.cli.setup import cmd_setup, cmd_version, version_lines  # noqa: F401
from dia.core.config import ConfigError, load_config
from dia.core.orchestrator import TaskActionError

# `dia --help` lists commands in this order; each module registers its own.
ORDER = [
    "version",
    "setup",
    "doctor",
    "agents",
    "check",
    "fix-build",
    "schedule",
    "issues",
    "usage",
    "brains",
    "audit",
    "screen",
    "build",
    "publish-build",
    "changelog",
    "security",
    "council",
    "research",
    "scorecard",
    "bench",
    "experiment",
    "lab",
    "redteam",
    "sandbox",
    "balance",
    "analyze",
    "tidy",
    "rollback",
    "why",
    "profile",
    "contradictions",
    "impact",
    "debt",
    "debug",
    "goal",
    "work",
    "skill",
    "suggestions",
    "decisions",
    "scenario",
    "preferences",
    "quiet",
    "stop",
    "resume",
    "mission",
    "remember",
    "learned",
    "howto",
    "limits",
    "run",
    "tasks",
    "memory",
    "plan",
    "review",
    "diff",
    "say",
    "voice",
    "ci",
    "launch",
    "runtime",
    "service",
    "comments",
    "ui",
    "secret",
    "mobile",
    "app",
    "shortcut",
    "plasmoid",
    "serve",
    "show",
]
REGISTRY = {
    **agents.COMMANDS,
    **desktop.COMMANDS,
    **memory.COMMANDS,
    **quality.COMMANDS,
    **release.COMMANDS,
    **serve.COMMANDS,
    **setup.COMMANDS,
    **tasks.COMMANDS,
    **voice.COMMANDS,
    **work.COMMANDS,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dia", description="Dia: your coding-agent orchestrator")
    parser.add_argument("--version", action="version", version=f"dia {__version__}")
    parser.add_argument("-c", "--config", type=Path, help="path to config TOML")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ORDER:
        REGISTRY[name](sub)
    return parser


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
