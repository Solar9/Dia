import subprocess
from pathlib import Path

from dia.impact import analyze, describe, find_targets, graph


def write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def commit(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message],
        cwd=root,
        check=True,
    )


def godot(repo: Path) -> Path:
    write(
        repo,
        {
            "project.godot": '[autoload]\nEvents="*res://autoload/events.gd"\n',
            "autoload/events.gd": "extends Node\nsignal dashed\n",
            "player/movement.gd": "class_name Movement\nextends Node\nfunc dash():\n"
            "\tEvents.dashed.emit()\n",
            "player/player.gd": "extends CharacterBody2D\nvar m := Movement.new()\n"
            'const FX = preload("res://fx/dash_fx.tscn")\n',
            "player/player.tscn": '[ext_resource type="Script" path="res://player/player.gd"]\n'
            '[node name="Player" type="CharacterBody2D"]\n',
            "levels/level1.tscn": '[ext_resource path="res://player/player.tscn"]\n',
            "fx/dash_fx.tscn": '[node name="DashFx" type="GPUParticles2D"]\n',
            "hud/hud.gd": "extends Control\n",
            "test/test_movement.gd": "extends GutTest\nfunc test_dash():\n"
            "\tvar m = Movement.new()\n",
        },
    )
    commit(repo, "game")
    for i in range(3):  # the HUD always changes along with the movement
        movement = f"class_name Movement\n# {i}\nfunc dash():\n\tEvents.dashed.emit()\n"
        write(repo, {"player/movement.gd": movement, "hud/hud.gd": f"extends Control\n# {i}\n"})
        commit(repo, f"tweak {i}")
    return repo


def test_graph_follows_godot_references(repo) -> None:
    uses = graph(godot(repo))
    assert "player/movement.gd" in uses["player/player.gd"]  # class_name by name
    assert "fx/dash_fx.tscn" in uses["player/player.gd"]  # preload
    assert "player/player.gd" in uses["player/player.tscn"]  # ext_resource
    assert "autoload/events.gd" in uses["player/movement.gd"]  # autoload


async def test_what_could_break_if_dash_changes(repo) -> None:
    root = godot(repo)
    assert find_targets(root, "dash")[:1] == ["fx/dash_fx.tscn"]  # by name first
    result = await analyze(root, "movement")
    assert result.targets == ["player/movement.gd"]
    chain = {d["file"]: d["depth"] for d in result.dependents}
    assert chain["player/player.gd"] == 1 and chain["player/player.tscn"] == 2
    assert chain["levels/level1.tscn"] == 3
    assert result.cochanged[0] == {"file": "hud/hud.gd", "together": 4, "of": 4}
    assert result.tests == ["test/test_movement.gd"]
    text = describe(result)
    assert "levels/level1.tscn  (via player/player.tscn)" in text
    assert "hud/hud.gd  (4 of 4 commits)" in text


async def test_a_function_name_and_nothing(repo) -> None:
    root = godot(repo)
    by_func = await analyze(root, "dash")
    assert "player/movement.gd" in by_func.targets  # func dash()
    nothing = await analyze(root, "teleport")
    assert nothing.targets == [] and "Nothing in the project matches" in describe(nothing)
