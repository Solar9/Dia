import asyncio

from dia.workspace import Workspace


async def test_concurrent_worktrees_of_one_repository_do_not_collide(tmp_path, repo) -> None:
    # Parallel tasks (experiments, missions) create worktrees of the same repository at
    # once; unserialised, `git worktree add` fails now and then on git's own lock files.
    for round_ in range(5):
        root = tmp_path / f"w{round_}"
        spaces = await asyncio.gather(
            *(Workspace.create(repo, root, f"t{i}", "main") for i in range(12))
        )
        assert len({w.path for w in spaces}) == 12
        await asyncio.gather(*(w.remove(delete_branch=True) for w in spaces))
