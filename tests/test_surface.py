"""Pins the public surface (CLI, HTTP routes, entry points) during the refactor.

Snapshots live in tests/snapshots/. After an intentional change to the surface,
regenerate them with ``DIA_UPDATE_SNAPSHOTS=1 pytest tests/test_surface.py``.
"""

import argparse
import importlib
import json
import os
import tomllib
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from dia.cli import build_parser
from dia.core.config import parse_config
from dia.core.orchestrator import Orchestrator

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = Path(__file__).parent / "snapshots"


def check_snapshot(name: str, actual: list) -> None:
    path = SNAPSHOTS / name
    if os.environ.get("DIA_UPDATE_SNAPSHOTS"):
        SNAPSHOTS.mkdir(exist_ok=True)
        path.write_text(json.dumps(actual, indent=1, ensure_ascii=False) + "\n")
    expected = json.loads(path.read_text())
    assert actual == expected, f"{name} changed; the public surface must stay the same"


def walk_parser(parser: argparse.ArgumentParser, prefix: str = "") -> list[list]:
    """(command path, sorted option strings, positional names) for every subcommand."""
    rows: list[list] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                path = f"{prefix} {name}".strip()
                options = sorted(o for a in sub._actions for o in a.option_strings)
                positionals = [
                    a.dest
                    for a in sub._actions
                    if not a.option_strings and not isinstance(a, argparse._SubParsersAction)
                ]
                rows.append([path, options, positionals])
                rows.extend(walk_parser(sub, path))
    return sorted(rows)


def test_cli_surface():
    top = sorted(o for a in build_parser()._actions for o in a.option_strings)
    check_snapshot("cli.json", [["", top, []], *walk_parser(build_parser())])


@pytest.fixture
def api_channel(tmp_path):
    pytest.importorskip("aiohttp")
    from dia.channels.api import ApiChannel

    (tmp_path / "dia.toml").write_text("[dia]\n")
    config = parse_config({"dia": {"data_dir": str(tmp_path / "data")}}, tmp_path / "dia.toml")
    return ApiChannel("ui", {"port": 0}, Orchestrator(config))


def test_api_routes(api_channel):
    routes = sorted(
        {
            (r.method, r.resource.canonical)
            for r in api_channel.app().router.routes()
            if r.resource is not None
        }
    )
    check_snapshot("routes.json", [list(r) for r in routes])


def test_no_route_is_shadowed_by_another(api_channel):
    """Registration order matters for dynamic routes: every route must still be the
    one aiohttp picks for its own path."""
    import asyncio
    import re

    from aiohttp.test_utils import make_mocked_request

    async def check() -> list[str]:
        router = api_channel.app().router
        wrong = []
        for route in router.routes():
            if route.resource is None or route.method == "HEAD":
                continue
            path = re.sub(r"\{[^}]+\}", "x", route.resource.canonical)
            request = make_mocked_request(route.method, path)
            match = await router.resolve(request)
            if match.route.resource is not route.resource:
                wrong.append(f"{route.method} {path} -> {match.route.resource.canonical}")
        return wrong

    assert asyncio.run(check()) == []


def pyproject_entry_points() -> list[tuple[str, str, str]]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return [
        (group, name, target)
        for group, items in data["project"]["entry-points"].items()
        if group.startswith("dia.")
        for name, target in items.items()
    ]


def test_entry_point_targets_resolve():
    """Every target declared in pyproject.toml imports (modules with missing
    optional extras are skipped: CI installs only `.[dev]`)."""
    for group, name, target in pyproject_entry_points():
        module, _, attr = target.partition(":")
        try:
            obj = importlib.import_module(module)
        except ImportError as exc:  # optional extra not installed
            if exc.name and exc.name.split(".")[0] != "dia":
                continue
            raise
        for part in attr.split("."):
            assert hasattr(obj, part), f"{group}:{name} -> {target} does not resolve"
            obj = getattr(obj, part)


def test_installed_entry_points_match_pyproject():
    declared = {(g, n): t for g, n, t in pyproject_entry_points()}
    for group in {g for g, _ in declared}:
        installed = {ep.name: ep.value for ep in entry_points(group=group)}
        for (g, name), target in declared.items():
            if g == group and installed.get(name) is not None:
                assert installed[name] == target, f"{group}:{name} differs from pyproject"


def test_console_script_unchanged():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"] == {"dia": "dia.cli:main"}


def test_json_typed_dicts_match_their_dataclasses():
    """TaskJson / DeviceJson (the API's shapes) must follow TaskRecord and Device."""
    import dataclasses

    from dia.channels.api._util import DeviceJson, TaskJson
    from dia.core.devices import Device
    from dia.core.store import TaskRecord

    assert set(TaskJson.__required_keys__) == {f.name for f in dataclasses.fields(TaskRecord)}
    assert set(DeviceJson.__annotations__) == {
        f.name for f in dataclasses.fields(Device) if f.name != "token_hash"
    }
