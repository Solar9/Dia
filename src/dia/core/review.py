"""Cross-review of a task's changes by another agent, with fix rounds."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from dia.agents import Agent, AgentRequest, Mode
from dia.core.config import ProjectConfig
from dia.core.prompts import EDIT_NOTE
from dia.core.review_prompts import CHANGES_REQUESTED, fix_prompt, parse_verdict, review_prompt
from dia.core.store import TaskRecord
from dia.core.types import TaskActionError, TaskReport
from dia.core.workspace import (
    Workspace,
    git,
)
from dia.quality.quality import parse_violations, review_rules, rules_text

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia")


class Reviewer:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    def _reviewable(self, task_id: str) -> tuple[TaskRecord, ProjectConfig, Workspace]:
        task = self.dia.store.get(task_id)
        if not task:
            raise TaskActionError(f"no task {task_id}")
        if task.status in ("merged", "discarded", "published"):
            raise TaskActionError(f"task {task_id} is already {task.status}")
        if not task.commit_sha or not task.branch:
            raise TaskActionError(f"task {task_id} has no changes to review")
        project = self.dia.config.project(task.project)
        base = task.details.get("base")
        if not base:
            raise TaskActionError(f"task {task_id} does not record its base branch")
        worktree = task.details.get("worktree") or str(
            self.dia.config.data_dir / "worktrees" / project.name / task.id
        )
        workspace = Workspace(repo=project.path, path=Path(worktree), branch=task.branch, base=base)
        return task, project, workspace

    def reviewer_for(self, project: ProjectConfig, author: str, name: str | None = None) -> Agent:
        """The requested reviewer, else the configured one, else any agent but the author."""
        name = name or project.options.get("reviewer") or self.dia.config.review.get("reviewer")
        if not name:
            others = [a for a in self.dia.config.agents if a != author]
            if not others:
                raise TaskActionError("cross-review needs a second agent in [agents]")
            name = others[0]
        return self.dia.config.agent(name)

    async def review_task(
        self, task_id: str, reviewer: str | None = None, fix_rounds: int | None = None
    ) -> TaskReport:
        """Review a finished task's branch; see :meth:`_review`."""
        self.dia._ensure_running()
        task, project, _ = self._reviewable(task_id)
        self.dia.audit("task.review", task.id, reviewer or "")
        async with self.dia._slots:
            report = TaskReport(task=task)
            await self._review(task, project, reviewer, fix_rounds, report)
            return report

    async def _review(
        self,
        task: TaskRecord,
        project: ProjectConfig,
        reviewer_name: str | None,
        fix_rounds: int | None,
        report: TaskReport,
    ) -> None:
        """Reviewer reviews; on "changes requested" the author fixes, tests rerun, and the
        reviewer looks again, up to ``fix_rounds`` times."""
        _, _, workspace = self._reviewable(task.id)
        if not workspace.path.exists():
            raise TaskActionError(f"the worktree of task {task.id} no longer exists")
        reviewer = self.reviewer_for(project, task.agent, reviewer_name)
        author = self.dia.config.agent(task.details.get("author", task.agent))
        rounds = int(
            fix_rounds if fix_rounds is not None else self.dia.config.review.get("fix_rounds", 1)
        )
        max_diff = int(self.dia.config.review.get("max_diff_chars", 60000))
        reviews = task.details.setdefault("reviews", [])

        for round_no in range(rounds + 1):
            diff = await git(workspace.path, "diff", f"{workspace.base}...HEAD")
            reviewer, result = await self.dia.call_agent(
                reviewer,
                AgentRequest(
                    prompt=review_prompt(task.prompt, diff, workspace.base, max_diff)
                    + review_rules(rules_text(project, workspace.path)),
                    cwd=workspace.path,
                    mode=Mode.READ_ONLY,
                ),
                task,
                avoid=(author.name,),
                purpose="review",
            )
            if not result.success:
                raise TaskActionError(f"review by {reviewer.name} failed: {result.error}")
            verdict = parse_verdict(result.summary)
            reviews.append(
                {
                    "reviewer": reviewer.name,
                    "verdict": verdict,
                    "round": round_no,
                    "findings": result.summary,
                }
            )
            task.details["review"] = verdict
            static = [v for v in task.details.get("violations", []) if v["by"] == "static"]
            task.details["violations"] = static + parse_violations(result.summary)
            if not task.details["violations"]:
                task.details.pop("violations")
            self.dia.store.save(task)
            self.dia.decide(
                "review",
                verdict,
                task,
                result.summary.strip()[:600],
                reviewer=reviewer.name,
                round=round_no,
            )
            if verdict != CHANGES_REQUESTED or round_no == rounds:
                break

            await workspace.mark()
            _, fix = await self.dia.call_agent(
                author,
                AgentRequest(
                    prompt=fix_prompt(task.prompt, reviewer.name, result.summary) + EDIT_NOTE,
                    cwd=workspace.path,
                    mode=Mode.EDIT,
                ),
                task,
                avoid=(reviewer.name,),
                purpose="fix",
            )
            if not fix.success:
                report.warnings.append(f"fixing review findings failed: {fix.error}")
                break
            sha = await workspace.commit(f"dia: address review by {reviewer.name}")
            if not sha:  # the author disagreed with everything; its answer says why
                reviews[-1]["author_reply"] = fix.summary
                break
            task.commit_sha = sha
            task.summary = fix.summary or task.summary
            task.tests_ok, report.test_output = await self.dia._test(project, workspace)
            if task.tests_ok is not None:
                task.status = "done" if task.tests_ok else "failed"
            self.dia.store.save(task)
        report.diff_stat = await workspace.diff_stat()
