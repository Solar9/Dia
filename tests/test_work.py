from pathlib import Path

import pytest

from dia import work
from dia.config import parse_config
from dia.orchestrator import Orchestrator


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    marker = tmp_path / "opened.txt"
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", "echo x > x.txt; echo ok"]}},
        "projects": {"uv": {"path": str(repo)}, "other": {"path": str(repo)}},
        "profiles": {
            "starfall": {
                "project": "uv",
                "names": ["ultra"],
                "apps": [f"sh -c 'echo editor > {marker}'"],
            }
        },
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_a_session_is_restored_where_it_was_left(tmp_path, repo) -> None:
    import asyncio

    dia = make(tmp_path, repo)
    text = await work.start(dia, "Ultra")
    assert text.startswith("Work on starfall (uv).") and "Opened: sh" in text
    for _ in range(50):  # the app starts detached
        if (tmp_path / "opened.txt").exists():
            break
        await asyncio.sleep(0.05)
    assert (tmp_path / "opened.txt").read_text().strip() == "editor"

    task = (await dia.run_task("uv", "add the dash")).task
    dia.conversations.add_turn("ui", "czy dash działa?", "tak")
    (repo / "notes.txt").write_text("wip")  # uncommitted
    saved = await work.stop(dia, note="skończyłem na dashu")
    assert "Saved the session on starfall" in saved
    assert "skończyłem na dashu" in saved and "1 task(s) this session" in saved
    assert f"waiting for review: {task.id}" in saved and "uncommitted: notes.txt" in saved
    assert "we talked about: czy dash działa?" in saved

    again = await work.start(dia, "uv", open_apps=False)
    assert "Last time" in again and "skończyłem na dashu" in again
    assert "Waiting for your review (1)" in again


def test_profiles_and_names(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    assert set(work.profiles(dia)) == {"starfall", "other"}  # uv is starfall's project
    assert work.find(dia, "STARFALL")[0] == "starfall"
    assert work.find(dia, "other")[1] == {"project": "other"}
    with pytest.raises(ValueError, match="no profile"):
        work.find(dia, "nope")
