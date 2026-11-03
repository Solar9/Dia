import argparse
from pathlib import Path

from dia.cli.tasks import cmd_comments
from dia.core.config import parse_config
from dia.core.orchestrator import Orchestrator


async def test_comments_of_an_unknown_task_do_not_crash(
    tmp_path: Path, repo: Path, capsys, monkeypatch
) -> None:
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a"},
            "agents": {"a": {"type": "command", "argv": ["true"]}},
            "projects": {"demo": {"path": str(repo)}},
        },
        tmp_path / "dia.toml",
    )

    async def nothing_new(self, task_id):
        return []  # the task is not in the store: nothing new, and nothing pending to look up

    monkeypatch.setattr(Orchestrator, "review_comments", nothing_new)
    assert await cmd_comments(config, argparse.Namespace(task_id="nope", fix=False)) == 0
    assert capsys.readouterr().out.startswith("0 new, 0 not yet addressed")


def _config(tmp_path: Path, repo: Path):
    return parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a"},
            "agents": {"a": {"type": "command", "argv": ["true"]}},
            "projects": {"demo": {"path": str(repo)}},
        },
        tmp_path / "dia.toml",
    )


async def test_reviewing_an_unknown_goal_says_so_instead_of_crashing(
    tmp_path: Path, repo: Path, capsys, monkeypatch
) -> None:
    from dia.cli.work import cmd_goal
    from dia.work import goals

    async def review(dia, goal_id):
        return {}

    monkeypatch.setattr(goals, "review", review)
    args = argparse.Namespace(action="review", project="no-such-goal", text=None, weeks=None)
    assert await cmd_goal(_config(tmp_path, repo), args) == 1
    assert "error: no goal no-such-goal" in capsys.readouterr().err


async def test_the_index_refresher_copes_with_a_memory_that_has_no_semantic_index(
    tmp_path: Path, repo: Path, monkeypatch
) -> None:
    import asyncio
    from types import SimpleNamespace

    from dia.cli import serve

    updated = []
    dia = SimpleNamespace(memory=SimpleNamespace())  # a backend without semantic_index()

    async def stop(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(serve.asyncio, "sleep", stop)
    try:
        await serve._keep_index_fresh(dia)
    except asyncio.CancelledError:
        pass
    assert updated == []  # reached the sleep without an AttributeError
    index = SimpleNamespace(update=lambda: updated.append(1))
    dia.memory = SimpleNamespace(semantic_index=lambda: index)
    try:
        await serve._keep_index_fresh(dia)
    except asyncio.CancelledError:
        pass
    assert updated == [1]
