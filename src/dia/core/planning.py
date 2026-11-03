"""Planner: planning for the Orchestrator."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from dia.agents import AgentRequest, Mode
from dia.core.config import ConfigError, ProjectConfig
from dia.core.forge_flow import Publisher, ci_fix_prompt, comments_prompt, publish_body  # noqa: F401
from dia.core.plans import Step, parse_plan, pipeline_steps, planner_prompt
from dia.core.prompts import EDIT_NOTE, _title, with_context  # noqa: F401
from dia.core.store import TaskRecord
from dia.core.types import TaskActionError, TaskReport, new_task_id
from dia.core.workspace import (
    Workspace,
)

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia")


class Planner:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    async def create_plan(
        self,
        project_name: str,
        goal: str,
        pipeline: str | None = None,
        planner: str | None = None,
    ) -> TaskRecord:
        """Prepare a multi-step plan (from a pipeline, or proposed by a planner agent).

        The plan is stored as a task with status "planned"; :meth:`run_plan` executes it.
        """
        self.dia._ensure_running()
        project = self.dia.config.project(project_name)
        try:
            if pipeline:
                if pipeline not in self.dia.config.pipelines:
                    known = ", ".join(self.dia.config.pipelines) or "none"
                    raise TaskActionError(f"unknown pipeline '{pipeline}' (configured: {known})")
                steps = pipeline_steps(self.dia.config.pipelines[pipeline], goal)
            else:
                steps = await self._propose_plan(project, goal, planner)
            for step in steps:
                self.dia.config.agent(step.agent)  # every agent must exist
        except (ValueError, ConfigError) as exc:
            raise TaskActionError(str(exc)) from None
        agents = list(dict.fromkeys(step.agent for step in steps))
        task = TaskRecord(
            id=new_task_id(),
            project=project.name,
            agent="+".join(agents),
            mode=Mode.EDIT,
            prompt=goal,
            status="planned",
            details={"plan": [step.to_dict() for step in steps], "pipeline": pipeline},
        )
        self.dia.store.save(task)
        from dia.quality.simulation import attach

        attach(self.dia, task)
        return task

    async def _propose_plan(
        self, project: ProjectConfig, goal: str, planner_name: str | None
    ) -> list[Step]:
        options = self.dia.config.plans
        planner = self.dia.config.agent(planner_name or options.get("planner"), project)
        max_steps = int(options.get("max_steps", 4))
        roles = {
            name: opts.get("role") or f"{opts.get('type', name)} coding agent"
            for name, opts in self.dia.config.agents.items()
        }
        workspace = await Workspace.create(
            project.path,
            self.dia.config.data_dir / "worktrees" / project.name,
            f"plan-{new_task_id()}",
            project.base_branch,
        )
        try:
            result = await planner.run(
                AgentRequest(
                    prompt=planner_prompt(goal, roles, max_steps),
                    cwd=workspace.path,
                    mode=Mode.READ_ONLY,
                )
            )
        finally:
            await workspace.remove(delete_branch=True)
        if not result.success:
            raise TaskActionError(f"planner {planner.name} failed: {result.error}")
        return parse_plan(result.summary, list(self.dia.config.agents), max_steps)

    async def run_plan(
        self,
        task_id: str,
        on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
        review: bool | None = None,
    ) -> TaskReport:
        self.dia._ensure_running()
        task = self.dia.store.get(task_id)
        if not task:
            raise TaskActionError(f"no task {task_id}")
        if task.mode == "mission":
            from dia.work.missions import Missions

            return await Missions(self.dia).run(task_id, on_start)
        if task.status != "planned":
            raise TaskActionError(f"task {task_id} is '{task.status}', not a plan waiting to run")
        project = self.dia.config.project(task.project)
        steps = [Step(**raw) for raw in task.details["plan"]]
        task.status = "queued"
        self.dia.store.save(task)
        return await self.dia._execute(task, project, steps, Mode.EDIT, True, on_start, review)
