"""Merger: merging for the Orchestrator."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dia.agents import Mode
from dia.core.forge_flow import Publisher, ci_fix_prompt, comments_prompt, publish_body  # noqa: F401
from dia.core.prompts import EDIT_NOTE, _title, with_context  # noqa: F401
from dia.core.store import TaskRecord, now
from dia.core.types import TaskActionError, new_task_id
from dia.core.workspace import (
    GitError,
    Workspace,
    git,
    identity_args,
    run,
)

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia")


class Merger:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    async def merge_task(
        self, task_id: str, reason: str | None = None, override: str | None = None
    ) -> str:
        """Merge a finished task's branch into its base branch in the user's checkout.

        Refuses rather than guessing: the checkout must be on the base branch,
        and a merge that conflicts is aborted, leaving everything as it was.
        ``reason`` (why it is accepted) goes into the decision log. Architecture
        violations and failed verification checks block it, unless ``override``
        says why they are acceptable (dia.quality).
        """
        from dia.quality.quality import blockers

        task, project, workspace = self.dia.reviewer._reviewable(task_id)
        if task.status != "done":
            raise TaskActionError(f"task {task_id} is '{task.status}'; only 'done' tasks merge")
        if blocked := blockers(task):
            if not override:
                raise TaskActionError(
                    "blocked by the quality guards:\n- "
                    + "\n- ".join(blocked)
                    + "\nfix them, or merge with an override that says why they are fine"
                )
            task.details["override"] = override
            self.dia.store.save(task)
            self.dia.audit("task.override", task.id, override)
            self.dia.decide("override", "overridden", task, override, blockers=blocked)
        current = await git(project.path, "rev-parse", "--abbrev-ref", "HEAD")
        if current != workspace.base:
            raise TaskActionError(
                f"{project.path} is on '{current}', not '{workspace.base}'; "
                f"check out '{workspace.base}' there first"
            )
        message = f"Merge Dia task {task.id}: {task.prompt.splitlines()[0][:60]}"
        code, out = await run(
            [
                "git",
                *await identity_args(project.path),
                "merge",
                "--no-ff",
                "--no-edit",
                "-m",
                message,
                task.branch or "",
            ],
            project.path,
        )
        if code != 0:
            await run(["git", "merge", "--abort"], project.path)
            raise TaskActionError(f"merge failed and was aborted, nothing changed:\n{out.strip()}")
        sha = await git(project.path, "rev-parse", "HEAD")
        if task.mode == "mission":
            from dia.work.missions import Missions

            await Missions(self.dia).cleanup(task)
        self.dia.audit("task.merge", task.id, f"{task.branch} into {workspace.base} as {sha[:10]}")
        try:
            files = (await git(project.path, "diff", "--name-only", f"{sha}^1", sha)).split()
        except GitError:
            files = []
        self.dia.decide("merge", "merged", task, reason, sha=sha, branch=task.branch, files=files)
        await workspace.remove(delete_branch=True)
        task.status = "merged"
        task.details["merge_commit"] = sha
        self.dia.store.save(task)
        if project.options.get("benchmark"):  # did it make the numbers worse?
            from dia.quality.benchmarks import after_merge

            self.dia.spawn(after_merge(self.dia, project.name, sha, task.id))
        return sha

    async def rollback_task(self, task_id: str, reason: str | None = None) -> TaskRecord:
        """Undo a merged task: its revert is prepared as a new task on its own
        branch and tested, then merged like any other (your approval)."""
        self.dia._ensure_running()
        original = self.dia.store.get(task_id)
        if not original or original.status != "merged":
            raise TaskActionError(f"task {task_id} is not merged; only merged tasks roll back")
        sha = original.details.get("merge_commit")
        if not sha:
            raise TaskActionError(f"task {task_id} has no recorded merge commit")
        project = self.dia.config.project(original.project)
        task = TaskRecord(
            id=new_task_id(),
            project=project.name,
            agent="-",
            mode=Mode.EDIT,
            prompt=f"Revert: {original.prompt.splitlines()[0][:100]}",
            status="running",
            details={"reverts": original.id},
        )
        self.dia.store.save(task)
        self.dia.audit("task.rollback", original.id, f"prepared as {task.id}")
        self.dia.decide("rollback", "rolled back", original, reason, revert=task.id)
        workspace = await Workspace.create(
            project.path,
            self.dia.config.data_dir / "worktrees" / project.name,
            task.id,
            original.details.get("base") or project.base_branch,
        )
        task.branch = workspace.branch
        task.details.update(base=workspace.base, worktree=str(workspace.path))
        try:
            parents = (await git(project.path, "rev-list", "--parents", "-n", "1", sha)).split()
            argv = ["revert", "--no-edit", *(["-m", "1"] if len(parents) > 2 else []), sha]
            code, out = await run(
                ["git", *await identity_args(workspace.path), *argv], workspace.path
            )
            if code != 0:
                await run(["git", "revert", "--abort"], workspace.path)
                raise TaskActionError(
                    "the revert conflicts with later changes; resolve it by hand "
                    f"(git revert -m 1 {sha[:10]}):\n{out.strip()[-800:]}"
                )
            task.commit_sha = await git(workspace.path, "rev-parse", "HEAD")
            task.tests_ok, _ = await self.dia.tester._test(project, workspace)
            task.summary = f"Reverts {original.id} (merge {sha[:10]}). Merge this task to undo it."
            task.status = "failed" if task.tests_ok is False else "done"
            original.details["reverted_by"] = task.id
            self.dia.store.save(original)
        except Exception as exc:
            task.status, task.error = "failed", str(exc)[:2000]
            if not task.commit_sha:
                await workspace.remove(delete_branch=True)
        finally:
            task.finished_at = now()
            self.dia.store.save(task)
        return task

    async def discard_task(self, task_id: str, reason: str | None = None) -> None:
        """Delete a task's worktree and branch (a plan nobody ran: just drop it).
        ``reason`` (why it is rejected) goes into the decision log."""
        planned = self.dia.store.get(task_id)
        if planned and planned.status == "planned":
            planned.status = "discarded"
            self.dia.store.save(planned)
            self.dia.audit("plan.reject", planned.id, reason or "")
            self.dia.decide("plan", "rejected", planned, reason)
            return
        task, _, workspace = self.dia.reviewer._reviewable(task_id)
        self.dia.audit("task.discard", task.id, task.branch or "")
        if task.mode == "mission":
            from dia.work.missions import Missions

            await Missions(self.dia).cleanup(task)
        await workspace.remove(delete_branch=True)
        task.status = "discarded"
        self.dia.store.save(task)
        self.dia.decide("discard", "discarded", task, reason, branch=task.branch)
