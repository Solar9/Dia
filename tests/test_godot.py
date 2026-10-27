import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.toolchains.godot import GodotToolchain, read_project

PROJECT_GODOT = """\
config_version=5

[application]

config/name="Nova"
run/main_scene="res://scenes/main.tscn"
config/features=PackedStringArray("4.3", "Forward Plus")
"""


@pytest.fixture
def game(tmp_path: Path, repo: Path) -> Path:
    (repo / "project.godot").write_text(PROJECT_GODOT)
    (repo / ".gitignore").write_text(".godot/\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "godot"],
        cwd=repo,
        check=True,
    )
    (repo / ".godot").mkdir()
    (repo / ".godot" / "imported.marker").write_text("cache")
    return repo


@pytest.fixture
def godot(tmp_path: Path) -> tuple[Path, Path]:
    """A fake Godot that behaves like the real one where it matters: the import can
    fail (exit 7 when ``import_fails`` exists), ``--check-only`` parses one script
    (``func (`` is a parse error), and the smoke run never loads unused scripts."""
    log = tmp_path / "godot.log"
    binary = tmp_path / "godot4"
    binary.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> {log}\n'
        f'case "$*" in *--editor*) [ -f {tmp_path}/import_fails ] && exit 7; exit 0;; esac\n'
        'case "$*" in *--check-only*)\n'
        '  script=$(echo "$*" | sed "s|.*res://||")\n'
        '  if grep -q "func (" "$script"; then\n'
        '    echo "SCRIPT ERROR: Parse Error: Expected function name after func."; exit 1\n'
        "  fi; exit 0;;\n"
        "esac\n"
        'echo "done"\n'
    )
    binary.chmod(0o755)
    return binary, log


def orchestrator(
    tmp_path: Path, repo: Path, godot: Path, agent: list[str], **extra
) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": agent}},
        "projects": {"nova": {"path": str(repo), "toolchain_options": {"command": [str(godot)]}}},
        **extra,
    }
    return Orchestrator(parse_config(raw))


def test_reads_project_godot(game: Path) -> None:
    assert read_project(game) == {
        "name": "Nova",
        "main_scene": "res://scenes/main.tscn",
        "version": "4.3",
    }
    assert GodotToolchain.detect(game)


async def test_godot_project_is_tested_and_described(tmp_path, game, godot) -> None:
    binary, log = godot
    # The agent echoes the prompt it got, and adds a (valid) script.
    agent = ["sh", "-c", 'echo "extends Node" > player.gd; echo "$0"', "{prompt}"]
    orch = orchestrator(tmp_path, game, binary, agent)
    assert orch.toolchain_for(orch.config.project("nova")).describe() == "godot 4.3, smoke run"

    report = await orch.run_task("nova", "add a player script")
    task = report.task
    assert task.status == "done" and task.tests_ok is True
    assert "This is a Godot 4.3 project ('Nova'" in task.summary  # context reached the agent
    assert "Never edit the .godot/ folder" in task.summary
    calls = log.read_text().splitlines()
    assert "--headless --path" in calls[0] and calls[0].endswith("--editor --quit")
    assert calls[1].endswith("--check-only --script res://player.gd")  # the changed script
    assert calls[2].endswith("--quit-after 120")  # no test framework: smoke run
    assert report.test_output.startswith(
        "Godot: import OK; 1 changed script(s) parsed; smoke run OK"
    )
    worktree = Path(task.details["worktree"])
    assert (worktree / ".godot" / "imported.marker").read_text() == "cache"  # cache reused


async def test_script_errors_fail_even_with_exit_zero(tmp_path, game, godot) -> None:
    binary, _ = godot
    agent = ["sh", "-c", "echo 'func (' > broken.gd; echo wrote"]
    report = await orchestrator(tmp_path, game, binary, agent).run_task("nova", "break it")
    # The smoke run passes (nothing loads broken.gd); parsing changed scripts catches it.
    assert report.task.status == "failed" and report.task.tests_ok is False
    assert "1 changed script(s) parsed, 1 with errors; smoke run OK" in report.test_output
    assert "Errors found:\nSCRIPT ERROR: Parse Error" in report.test_output


async def test_failed_import_fails_the_run(tmp_path, game, godot) -> None:
    binary, _ = godot
    (tmp_path / "import_fails").write_text("")
    agent = ["sh", "-c", "echo 'extends Node' > ok.gd"]
    report = await orchestrator(tmp_path, game, binary, agent).run_task("nova", "x")
    assert report.task.tests_ok is False
    assert report.test_output.startswith("Godot: import FAILED (exit 7)")


async def test_gut_is_used_when_present(tmp_path, game, godot) -> None:
    binary, log = godot
    (game / "addons" / "gut").mkdir(parents=True)
    (game / "addons" / "gut" / "gut_cmdln.gd").write_text("extends SceneTree")
    subprocess.run(["git", "add", "."], cwd=game, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "gut"],
        cwd=game,
        check=True,
    )
    agent = ["sh", "-c", "echo x > x.gd; echo ok"]
    orch = orchestrator(tmp_path, game, binary, agent)
    assert (await orch.run_task("nova", "x")).task.tests_ok is True
    assert log.read_text().splitlines()[-1].endswith("-s addons/gut/gut_cmdln.gd -gexit")


async def test_explicit_test_command_wins(tmp_path, game, godot) -> None:
    binary, log = godot
    orch = orchestrator(tmp_path, game, binary, ["sh", "-c", "echo x > x.gd"])
    orch.config.projects["nova"].test_command = "true"
    assert (await orch.run_task("nova", "x")).task.tests_ok is True
    assert not log.exists()


async def test_launch_by_voice_or_text(tmp_path, game, godot) -> None:
    binary, log = godot
    intent = {"action": "launch", "project": "nova", "reply": ""}
    orch = orchestrator(
        tmp_path,
        game,
        binary,
        ["true"],
        brains={"router": {"type": "agent", "agent": "llm"}},
    )
    orch.config.agents["llm"] = {"type": "command", "argv": ["echo", json.dumps(intent)]}
    orch.config.brain_order = ["router"]
    response = await Assistant(orch).handle("Jarvis, odpal Nova")
    assert response.text == "started Nova"
    for _ in range(50):
        if log.exists():
            break
        await asyncio.sleep(0.05)
    assert log.read_text().strip() == f"--path {game}"  # windowed, not headless


def test_projects_without_godot_have_no_toolchain(tmp_path, repo) -> None:
    orch = Orchestrator(parse_config({"projects": {"x": {"path": str(repo)}}}))
    assert orch.toolchain_for(orch.config.project("x")) is None


GUT_OUTPUT = """\
res://test/test_combat.gd
* test_parry_blocks_damage
    [Failed]: expected 0 but got 12
* test_dodge
---- Totals ----
Scripts           1
Tests             2
  Passing tests   1
  Failing tests   1
"""

GDUNIT_OUTPUT = """\
Run Test Suite: res://test/combat_test.gd
  combat_test > test_parry FAILED 12ms
Overall Summary: 7 test cases | 0 errors | 1 failure | 0 flaky | 0 skipped | 0 orphans |
"""


def test_test_reports() -> None:
    from dia.toolchains.godot import test_counts

    gut = test_counts(GUT_OUTPUT)
    assert (gut["passed"], gut["failed"], gut["total"]) == (1, 1, 2)
    gd = test_counts(GDUNIT_OUTPUT)
    assert (gd["passed"], gd["failed"], gd["total"]) == (6, 1, 7)
    assert gd["failing"] == ["test_parry"]
    assert test_counts("done") is None


EXPORT_PRESETS = """\
[preset.0]

name="Linux"
platform="Linux"
export_path="build/nova.x86_64"

[preset.0.options]

custom_template/debug=""

[preset.1]

name="Windows Desktop"
platform="Windows Desktop"
export_path="build/nova.exe"
"""


async def test_build_and_changelog(tmp_path, game, godot) -> None:
    import subprocess as sp

    from dia.release import Releases

    binary, log = godot
    # The fake Godot "exports" by writing the target file.
    binary.write_text(
        binary.read_text().replace(
            'echo "done"\n',
            'case "$*" in *--export-release*) eval "last=\\${$#}"; echo bin > "$last";; esac\n'
            'echo "done"\n',
        )
    )
    (game / "export_presets.cfg").write_text(EXPORT_PRESETS)

    def commit(message: str) -> None:
        sp.run(["git", "add", "."], cwd=game, check=True)
        sp.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message],
            cwd=game,
            check=True,
        )

    commit("Add export presets")
    sp.run(["git", "tag", "v0.1"], cwd=game, check=True)
    (game / "parry.gd").write_text("extends Node\n")
    commit("Add parrying")
    (game / "coop.gd").write_text("extends Node\n")
    commit("Add 4-player co-op")

    dia = orchestrator(tmp_path, game, binary, ["true"])
    releases = Releases(dia)
    assert GodotToolchain(game).presets(game) == ["Linux", "Windows Desktop"]
    text = await releases.changelog("nova")
    assert text == "Since v0.1:\n\n- Add 4-player co-op\n- Add parrying"

    task = await releases.build("nova", ["Linux"], version="0.2-test")
    assert task.status == "done", task.error
    assert task.mode == "build" and task.details["builds"][0]["preset"] == "Linux"
    out = Path(task.details["output"])
    assert (out / "Linux" / "nova.x86_64").read_text() == "bin\n"
    assert "Add parrying" in (out / "CHANGELOG.md").read_text()
    assert not Path(dia.config.data_dir / "worktrees" / "nova" / task.id).exists()

    again = await releases.build("nova", ["Linux"], version="0.2-test")
    assert again.status == "done", again.error  # overwriting the same files is a build too

    failed = await releases.build("nova", ["Mac"])
    assert failed.status == "failed" and "no export preset 'Mac'" in failed.error
