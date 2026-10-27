import json
import sys
from pathlib import Path

import pytest

from dia.config import parse_config
from dia.lab import Lab
from dia.orchestrator import Orchestrator

# A stand-in for podman/docker: records its arguments, then runs the command
# in the mounted directory the way the container would.
FAKE_ENGINE = """
import json, os, subprocess, sys
args = sys.argv[1:]
json.dump(args, open(os.environ["LOG"], "w"))
if args[0] != "run":
    sys.exit(0)
volume = args[args.index("--volume") + 1].split(":")[0]
sys.exit(subprocess.run(args[-3:], cwd=volume).returncode)
"""


@pytest.fixture
def dia(tmp_path: Path, repo: Path, monkeypatch) -> Orchestrator:
    engine = tmp_path / "engine.py"
    engine.write_text(FAKE_ENGINE)
    monkeypatch.setenv("LOG", str(tmp_path / "engine.log"))
    raw = {
        "dia": {"data_dir": str(tmp_path / "data")},
        "projects": {"demo": {"path": str(repo)}},
        "lab": {"command": [sys.executable, str(engine)], "image": "img:1"},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_a_command_runs_on_a_copy_of_the_project(dia, tmp_path, repo) -> None:
    result = await Lab(dia).run("cat README.md; echo changed > README.md", "demo")
    assert result.ok and result.output.strip() == "hello"
    assert (repo / "README.md").read_text() == "hello\n"  # the project is untouched
    args = json.loads((tmp_path / "engine.log").read_text())
    assert args[:2] == ["run", "--rm"]
    assert args[args.index("--network") + 1] == "none"
    assert ["--cap-drop", "ALL"] == args[args.index("--cap-drop") : args.index("--cap-drop") + 2]
    assert args[-4:] == ["img:1", "sh", "-c", "cat README.md; echo changed > README.md"]
    assert not list((tmp_path / "data" / "lab").iterdir())  # thrown away
    assert dia.store.audit(action="lab.run")[0]["detail"].startswith("img:1 demo@")


async def test_failure_network_and_keep(dia, tmp_path) -> None:
    result = await Lab(dia).run("exit 3", network=True, keep=True)
    assert result.code == 3 and not result.ok and Path(result.kept).is_dir()
    args = json.loads((tmp_path / "engine.log").read_text())
    assert args[args.index("--network") + 1] == "bridge"


def test_no_engine(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    dia = Orchestrator(parse_config({"dia": {"data_dir": str(tmp_path)}}), use_memory=False)
    assert "podman" in Lab(dia).check()
