import struct
import zlib
from pathlib import Path

from dia.godot_analysis import _depth, analyze, describe, frame_lookups, image_size


def png(path: Path, width: int, height: int) -> None:
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + header
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(header))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk))
    )


def test_depth() -> None:
    assert [_depth(p) for p in ("", ".", "Player", "Player/Body")] == [1, 2, 3, 4]


def test_frame_lookups() -> None:
    source = (
        "extends Node\n\n"
        "@onready var hp = $HP\n\n"
        "func _process(delta):\n"
        "\tvar label = $UI/Label\n"
        "\tlabel.text = str(get_node('HP').value)\n\n"
        "func _ready():\n"
        "\t$UI.show()\n"
    )
    assert frame_lookups(source) == 2


def test_analysis_of_a_project(tmp_path: Path) -> None:
    (tmp_path / "project.godot").write_text("config_version=5\n")
    nodes = ['[node name="Level" type="Node3D"]']
    nodes += [f'[node name="L{i}" type="OmniLight3D" parent="."]' for i in range(10)]
    nodes += [f'[node name="N{i}" type="Node3D" parent="."]' for i in range(5)]
    (tmp_path / "level.tscn").write_text("[gd_scene format=3]\n\n" + "\n\n".join(nodes))
    (tmp_path / "small.tscn").write_text('[node name="Root" type="Node2D"]\n')
    (tmp_path / "player.gd").write_text(
        "extends Node\nfunc _process(delta):\n\tget_node('Gun').aim()\n"
    )
    (tmp_path / "idle.gd").write_text("extends Node\nfunc _process(delta):\n\tpass\n")
    png(tmp_path / "sky.png", 8192, 4096)
    png(tmp_path / "icon.png", 64, 64)
    (tmp_path / ".godot").mkdir()
    png(tmp_path / ".godot" / "cache.png", 9000, 9000)  # the import cache is skipped

    result = analyze(tmp_path)
    assert (result.scenes, result.scripts, result.textures) == (2, 2, 2)
    assert result.biggest_scenes[0] == {"scene": "level.tscn", "nodes": 16, "depth": 2}
    found = [(f.severity, f.file) for f in result.findings]
    assert found == [
        ("high", "level.tscn"),
        ("medium", "player.gd"),
        ("medium", "sky.png"),
        ("info", "idle.gd"),
    ]
    assert image_size(tmp_path / "sky.png") == (8192, 4096)
    text = describe(result, "pl")
    assert text.startswith("Sceny: 2, skrypty: 2, tekstury: 2.") and "10 real-time lights" in text
