"""Publishing a task: pull/merge request, CI status and fixes, review comments."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import TYPE_CHECKING

from dia.agents import AgentRequest, Mode
from dia.core import plugins
from dia.core.config import ProjectConfig
from dia.core.prompts import EDIT_NOTE, _title
from dia.core.store import TaskRecord, now
from dia.core.types import TaskActionError, TaskReport
from dia.core.workspace import (
    GitError,
    Workspace,
)
from dia.forges import CIStatus, Forge, Publication, ReviewComment, detect

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia")


def _branch(task: TaskRecord) -> str:
    if not task.branch:
        raise TaskActionError(f"task {task.id} has no branch")
    return task.branch


def comments_prompt(task_prompt: str, comments: list[ReviewComment]) -> str:
    listing = "\n\n".join(
        f"- {c.author}"
        + (f" on {c.path}" + (f":{c.line}" if c.line else "") if c.path else "")
        + f":\n{c.body.strip()}"
        for c in comments
    )
    return f"""\
You implemented this task earlier; your changes are committed here and a
pull/merge request is open:

<task>
{task_prompt}
</task>

Reviewers left these comments on it:

<comments>
{listing}
</comments>

Address each comment you agree with, directly in the code. For a question
or a comment you disagree with, change nothing and answer it in your final
message, naming the reviewer.
"""


def ci_fix_prompt(task_prompt: str, failed: str, log_text: str) -> str:
    return f"""\
You implemented this task earlier; your changes are committed here and a
pull/merge request is open:

<task>
{task_prompt}
</task>

Its CI failed ({failed}). Find the cause and fix it in the code. Do not
disable or skip checks to make them pass.

<ci-log>
{log_text or "(no log available; reproduce the checks locally if you can)"}
</ci-log>
"""


def publish_body(task: TaskRecord) -> str:
    """Description for a pull/merge request."""
    tests = {None: "not run", True: "passed", False: "failed"}[task.tests_ok]
    parts = [f"**Task:** {task.prompt}", f"**Agent:** {task.agent} · **Tests:** {tests}"]
    if reviews := task.details.get("reviews"):
        last = reviews[-1]
        parts.append(f"**Review:** {last['verdict'].replace('_', ' ')} by {last['reviewer']}")
    if task.summary:
        parts.append(f"## Summary\n\n{task.summary}")
    if issue := task.details.get("issue"):
        parts.append(f"Closes #{issue['number']}")
    parts.append(f"---\n_Created by Dia, task `{task.id}`._")
    return "\n\n".join(parts)


class Publisher:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    async def publish_task(self, task_id: str) -> Publication:
        """Push a finished task's branch and open a pull/merge request on the project's forge.

        Per project: ``forge`` ("auto", the default, decides from the remote URL;
        or "github", "gitlab", "git", any plugin) and ``forge_options`` (remote,
        draft, ...).
        """
        task, project, workspace = self.dia.reviewer._reviewable(task_id)
        if task.status != "done":
            raise TaskActionError(f"task {task_id} is '{task.status}'; only 'done' tasks publish")
        try:
            kind, forge = await self._forge(project)
            publication = await forge.publish(
                project.path, _branch(task), workspace.base, _title(task.prompt), publish_body(task)
            )
        except (GitError, RuntimeError, LookupError) as exc:
            raise TaskActionError(str(exc)) from None
        self.dia.audit("task.publish", task.id, f"{kind}: {publication.url or publication.message}")
        await workspace.remove(delete_branch=False)  # the branch now lives on the remote too
        task.status = "published"
        task.details["published"] = {"forge": kind, "url": publication.url}
        # "pending" until the first check says otherwise; forges without CI: "none"
        task.details["ci"] = {"state": "pending" if forge.has_ci else "none"}
        self.dia.store.save(task)
        return publication

    async def _forge(self, project: ProjectConfig) -> tuple[str, Forge]:
        options = dict(project.options.get("forge_options", {}))
        kind = project.options.get("forge", "auto")
        if kind == "auto":
            kind = await detect(project.path, options.get("remote", "origin"))
        return kind, plugins.load("dia.forges", kind)(options)

    def _published(self, task_id: str) -> tuple[TaskRecord, ProjectConfig]:
        task = self.dia.store.get(task_id)
        if not task:
            raise TaskActionError(f"no task {task_id}")
        if task.status != "published":
            raise TaskActionError(f"task {task_id} is '{task.status}', not published")
        return task, self.dia.config.project(task.project)

    async def ci_status(self, task_id: str) -> CIStatus:
        """Check the CI of a published task and remember the result."""
        task, project = self._published(task_id)
        try:
            _, forge = await self._forge(project)
            status = await forge.ci_status(project.path, _branch(task))
        except (GitError, RuntimeError, LookupError, ValueError) as exc:
            raise TaskActionError(f"cannot read CI: {exc}") from None
        task.details["ci"] = {**task.details.get("ci", {}), **asdict(status), "checked_at": now()}
        self.dia.store.save(task)
        return status

    async def fix_ci(self, task_id: str) -> TaskReport:
        """Give a failed CI run's log to the task's author, then push its fix to the same branch
        (the open pull/merge request picks it up)."""
        self.dia._ensure_running()
        task, project = self._published(task_id)
        ci = task.details.get("ci", {})
        if ci.get("state") != "failed":
            raise TaskActionError(f"CI of task {task_id} has not failed (state: {ci.get('state')})")
        _, forge = await self._forge(project)
        status = CIStatus(ci["state"], ci.get("url"), ci.get("failed", []))
        log_text = await forge.ci_log(project.path, status)
        failed = ", ".join(str(f.get("name")) for f in status.failed) or "the pipeline"
        self.dia.audit("task.fix_ci", task.id, failed)
        report = await self._push_fix(
            task, project, forge, ci_fix_prompt(task.prompt, failed, log_text), f"fix CI ({failed})"
        )
        task.details["ci_fixes"] = task.details.get("ci_fixes", 0) + 1
        self.dia.store.save(task)
        return report

    async def review_comments(self, task_id: str) -> list[ReviewComment]:
        """New comments on a published task's pull/merge request since the last check.

        They are remembered as pending until :meth:`address_comments` handles them.
        Comments from bots are ignored unless ``forge_options.include_bots``.
        """
        task, project = self._published(task_id)
        try:
            _, forge = await self._forge(project)
            comments = await forge.review_comments(project.path, _branch(task))
        except (GitError, RuntimeError, LookupError, ValueError, KeyError) as exc:
            raise TaskActionError(f"cannot read review comments: {exc}") from None
        include_bots = project.options.get("forge_options", {}).get("include_bots", False)
        seen = set(task.details.get("comments_seen", []))
        new = [c for c in comments if c.id not in seen and (include_bots or not c.is_bot)]
        if new:
            task.details["comments_seen"] = sorted(seen | {c.id for c in comments})
            pending = task.details.setdefault("comments_pending", [])
            pending += [asdict(c) for c in new]
            self.dia.store.save(task)
        return new

    async def address_comments(self, task_id: str) -> TaskReport:
        """Hand the pending review comments to the task's author and push its changes."""
        self.dia._ensure_running()
        task, project = self._published(task_id)
        pending = task.details.get("comments_pending", [])
        if not pending:
            raise TaskActionError(f"task {task_id} has no pending review comments")
        self.dia.audit("task.address_comments", task.id, f"{len(pending)} comment(s)")
        _, forge = await self._forge(project)
        report = await self._push_fix(
            task,
            project,
            forge,
            comments_prompt(task.prompt, [ReviewComment(**c) for c in pending]),
            f"address review comments ({len(pending)})",
        )
        task.details["comments_addressed"] = task.details.get("comments_addressed", []) + [
            c["id"] for c in pending
        ]
        task.details["comments_pending"] = []
        self.dia.store.save(task)
        return report

    async def _push_fix(
        self, task: TaskRecord, project: ProjectConfig, forge: Forge, prompt: str, what: str
    ) -> TaskReport:
        """Re-open the task's branch, let its author change it, test, and push (the open
        pull/merge request updates; its CI starts again)."""
        report = TaskReport(task=task)
        async with self.dia._slots:
            workspace = await Workspace.attach(
                project.path,
                self.dia.config.data_dir / "worktrees" / project.name,
                task.id,
                _branch(task),
                task.details.get("base", "main"),
            )
            try:
                author = self.dia.config.agent(task.details.get("author", task.agent))
                author, result = await self.dia.call_agent(
                    author,
                    AgentRequest(prompt=prompt + EDIT_NOTE, cwd=workspace.path, mode=Mode.EDIT),
                    task,
                    purpose="fix",
                )
                if not result.success:
                    raise TaskActionError(f"{author.name} failed to {what}: {result.error}")
                sha = await workspace.commit(f"dia: {what}"[:72])
                if not sha:
                    raise TaskActionError(f"{author.name} made no changes: {result.summary}")
                task.tests_ok, report.test_output = await self.dia._test(project, workspace)
                await forge.push(project.path, _branch(task))
            except (GitError, RuntimeError) as exc:
                raise TaskActionError(str(exc)) from None
            finally:
                await workspace.remove(delete_branch=False)
        task.commit_sha = sha
        task.summary = result.summary
        task.details["ci"] = {"state": "pending" if forge.has_ci else "none"}
        self.dia.store.save(task)
        return report
