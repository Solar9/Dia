import json
import os
import stat

import pytest

from dia.core.jsonfile import read_json, write_json


def test_roundtrip_creates_parents_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "a" / "b" / "state.json"
    write_json(path, {"x": [1, 2], "ł": "ą"}, ensure_ascii=False, newline=True)
    assert read_json(path) == {"x": [1, 2], "ł": "ą"}
    assert path.read_text().endswith("}\n")
    assert [p.name for p in path.parent.iterdir()] == ["state.json"]


def test_read_defaults_for_missing_and_corrupt_files(tmp_path):
    assert read_json(tmp_path / "none.json", []) == []
    (tmp_path / "bad.json").write_text("{not json")
    assert read_json(tmp_path / "bad.json", {"d": 1}) == {"d": 1}


def test_an_existing_file_keeps_its_mode(tmp_path):
    path = tmp_path / "secret.json"
    path.write_text("{}")
    path.chmod(0o600)
    write_json(path, {"k": 1})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    write_json(tmp_path / "private.json", {"k": 1}, mode=0o600)
    assert stat.S_IMODE((tmp_path / "private.json").stat().st_mode) == 0o600


def test_a_failed_write_keeps_the_old_file(tmp_path):
    path = tmp_path / "state.json"
    write_json(path, {"v": 1})
    with pytest.raises(TypeError):
        write_json(path, {"v": object()})
    assert json.loads(path.read_text()) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]
    assert os.listdir(tmp_path) == ["state.json"]
