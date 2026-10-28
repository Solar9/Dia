"""Isolated working copies: every task runs in its own git worktree and branch.

This keeps agents from stepping on each other (and on your own checkout) and
makes every change reviewable and reversible as an ordinary branch.
"""

from __future__ import annotations

import asyncio
import shutil
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dia import processes


class GitError(Exception):
    pass


async def run(
    argv: list[str] | str,
    cwd: Path,
    timeout: float | None = None,
    stdin: str | None = None,
    stoppable: bool = False,
) -> tuple[int, str]:
    """Run a command (argv list, or a shell string) and return (exit code, combined output).

    ``stoppable`` commands (tests, builds) run in their own process group and end
    with the emergency stop; git commands are left to finish.
    """
    pipes: dict = {
        "cwd": cwd,
        "start_new_session": stoppable,
        "stdin": asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.STDOUT,
    }
    if isinstance(argv, str):
        proc = await asyncio.create_subprocess_shell(argv, **pipes)
    else:
        proc = await asyncio.create_subprocess_exec(*argv, **pipes)
    if stoppable:
        processes.track(proc.pid, f"{argv if isinstance(argv, str) else argv[0]} in {cwd}")
    try:
        data = stdin.encode() if stdin is not None else None
        out, _ = await asyncio.wait_for(proc.communicate(data), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"timed out after {timeout}s"
    finally:
        processes.untrack(proc.pid)
    if stoppable and processes.was_stopped(proc.pid):
        return -1, "stopped (emergency stop)"
    return proc.returncode or 0, out.decode(errors="replace")


async def git(cwd: Path, *args: str) -> str:
    code, out = await run(["git", *args], cwd)
    if code != 0:
        raise GitError(f"git {' '.join(args)} failed: {out.strip()}")
    return out.strip()


# `git worktree add/remove/prune` on one repository race on git's own files when they run
# together (experiments and missions start several tasks at once), so they take turns.
_WORKTREE_LOCKS: weakref.WeakKeyDictionary[Any, dict[str, asyncio.Lock]] = (
    weakref.WeakKeyDictionary()
)


def _worktree_lock(repo: Path) -> asyncio.Lock:
    locks = _WORKTREE_LOCKS.setdefault(asyncio.get_running_loop(), {})
    return locks.setdefault(str(repo.resolve()), asyncio.Lock())


async def worktree(repo: Path, *args: str) -> str:
    """``git worktree <args>`` in ``repo``, one at a time per repository."""
    async with _worktree_lock(repo):
        return await git(repo, "worktree", *args)


async def uncommitted_files(repo: Path) -> list[str]:
    """Paths with uncommitted changes. Tasks start from the last commit, without them."""
    # Not via git(): stripping would eat the leading status column (" M path").
    code, status = await run(["git", "status", "--porcelain"], repo)
    if code != 0:
        raise GitError(f"git status failed: {status.strip()}")
    return [line[3:] for line in status.splitlines() if line.strip()]


DIA_IDENTITY = ["-c", "user.name=Dia", "-c", "user.email=dia@localhost"]


async def identity_args(repo: Path) -> list[str]:
    """No extra args if git knows who you are; otherwise commit as Dia rather than fail."""
    for key in ("user.name", "user.email"):
        code, _ = await run(["git", "config", key], repo)
        if code != 0:
            return DIA_IDENTITY
    return []


@dataclass
class Workspace:
    repo: Path
    path: Path
    branch: str
    base: str
    head: str | None = None  # last commit seen, to notice new ones

    @classmethod
    async def create(
        cls, repo: Path, root: Path, task_id: str, base: str | None = None
    ) -> Workspace:
        if not (repo / ".git").exists():
            raise GitError(f"{repo} is not a git repository (run 'git init' there first)")
        base = base or await git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        branch = f"dia/{task_id}"
        path = root / task_id
        path.parent.mkdir(parents=True, exist_ok=True)
        await worktree(repo, "add", "-b", branch, str(path), base)
        workspace = cls(repo=repo, path=path, branch=branch, base=base)
        await workspace.mark()
        return workspace

    @classmethod
    async def attach(
        cls, repo: Path, root: Path, task_id: str, branch: str, base: str
    ) -> Workspace:
        """A worktree on an existing task branch (e.g. to fix CI after publishing)."""
        path = root / task_id
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            await worktree(repo, "add", str(path), branch)
        workspace = cls(repo=repo, path=path, branch=branch, base=base)
        await workspace.mark()
        return workspace

    async def mark(self) -> None:
        """Remember the current commit; :meth:`commit` reports anything newer."""
        self.head = await git(self.path, "rev-parse", "HEAD")

    async def reset(self) -> None:
        """Throw away uncommitted changes (what a failed attempt left behind)."""
        await git(self.path, "reset", "--hard", "-q")
        await git(self.path, "clean", "-fdq")

    async def run_tests(
        self, command: str, timeout: float | None = None, sandbox: Any = None
    ) -> tuple[bool, str]:
        argv: list[str] | str = command
        if sandbox is not None:  # what an agent wrote runs here: keep it in the sandbox
            argv = sandbox.wrap(["sh", "-c", command], self.path)
        code, out = await run(argv, self.path, timeout, stoppable=True)
        return code == 0, out

    async def has_changes(self) -> bool:
        return bool(await git(self.path, "status", "--porcelain"))

    async def commit(self, message: str) -> str | None:
        """Commit what the agent changed; returns the new HEAD, or None if nothing changed.

        Agents that commit by themselves count too: any new commit since the
        last call is reported, so their work is never mistaken for no work.
        """
        changed = await self.has_changes()
        if not changed and self.head is None:  # unmarked: only our own commit can count
            return None
        if changed:
            await git(self.path, "add", "--all")
            await git(
                self.path,
                "-c",
                "user.name=Dia",
                "-c",
                "user.email=dia@localhost",
                "commit",
                "--quiet",
                "-m",
                message,
            )
        head = await git(self.path, "rev-parse", "HEAD")
        if head == self.head:
            return None
        self.head = head
        return head

    async def changed_files(self) -> list[str]:
        """Files added or modified on the task branch (relative paths)."""
        out = await git(
            self.path, "diff", "--name-only", "--diff-filter=AMR", f"{self.base}...HEAD"
        )
        return out.splitlines()

    async def diff_stat(self) -> str:
        return await git(self.path, "diff", "--stat", f"{self.base}...HEAD")

    async def remove(self, delete_branch: bool = False) -> None:
        async with _worktree_lock(self.repo):
            await run(["git", "worktree", "remove", "--force", str(self.path)], self.repo)
            if self.path.exists():
                shutil.rmtree(self.path, ignore_errors=True)
                await run(["git", "worktree", "prune"], self.repo)
            if delete_branch:
                await run(["git", "branch", "-D", self.branch], self.repo)
