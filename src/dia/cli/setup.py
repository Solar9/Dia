"""`dia setup` commands."""

from __future__ import annotations

import argparse
import sys

from dia import __version__
from dia.core.config import Config, ConfigError, load_config


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


def add_version(sub: argparse._SubParsersAction) -> None:
    sub.add_parser("version", help="Dia's version and where it lives").set_defaults(fn=cmd_version)


def add_setup(sub: argparse._SubParsersAction) -> None:
    setup_p = sub.add_parser("setup", help="set Dia up: agents, projects, memory, shortcuts")
    setup_p.add_argument("-y", "--yes", action="store_true", help="accept every proposal")
    setup_p.set_defaults(fn=cmd_setup)


COMMANDS = {
    "version": add_version,
    "setup": add_setup,
}
