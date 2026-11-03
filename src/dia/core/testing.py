"""ProjectTester: testing for the Orchestrator."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from dia.agents import AgentRequest, Mode
from dia.core import plugins
from dia.core.config import ProjectConfig
from dia.core.forge_flow import Publisher, ci_fix_prompt, comments_prompt, publish_body  # noqa: F401
from dia.core.prompts import EDIT_NOTE, _title, with_context  # noqa: F401
from dia.core.retry import RetryPolicy, test_fix_prompt
from dia.core.store import TaskRecord
from dia.core.task_limits import TaskLimits
from dia.core.types import TaskReport
from dia.core.workspace import (
    Workspace,
)
from dia.toolchains import Toolchain

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia")


class ProjectTester:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    async def _fix_tests(
        self,
        task: TaskRecord,
        project: ProjectConfig,
        workspace: Workspace,
        policy: RetryPolicy,
        report: TaskReport,
    ) -> None:
        """Failed tests go back to the author (``[retry] test_fixes``) until they pass."""
        for round_no in range(1, policy.test_fixes + 1):
            if task.tests_ok is not False or self.dia.halted:
                return
            author = task.details.get("author") or task.agent.split("+")[0]
            task.details.setdefault("retries", []).append(
                {"kind": "tests", "agent": author, "round": round_no}
            )
            self.dia.store.save(task)
            await self.dia.emit(
                "retry", task, f"tests failed; {author} is fixing them ({round_no})"
            )
            await asyncio.sleep(policy.delay_seconds)
            await workspace.mark()
            agent, result = await self.dia.call_agent(
                self.dia.config.agent(author),
                AgentRequest(
                    prompt=test_fix_prompt(task.prompt, report.test_output, round_no) + EDIT_NOTE,
                    cwd=workspace.path,
                    mode=Mode.EDIT,
                ),
                task,
                purpose="test-fix",
            )
            if not result.success:
                await workspace.reset()
                return
            if not (sha := await workspace.commit(f"dia: fix tests ({round_no})")):
                return
            task.commit_sha = sha
            report.diff_stat = await workspace.diff_stat()
            task.tests_ok, report.test_output = await self._test(project, workspace)

    def toolchain_for(self, project: ProjectConfig) -> Toolchain | None:
        """The project's toolchain: ``toolchain`` option, or detected ("auto", the default)."""
        if project.name in self.dia._toolchains:
            return self.dia._toolchains[project.name]
        kind = project.options.get("toolchain", "auto")
        options = project.options.get("toolchain_options", {})
        found = None
        if kind == "auto":
            for name in plugins.available("dia.toolchains"):
                cls = plugins.load("dia.toolchains", name)
                if project.path.is_dir() and cls.detect(project.path):
                    found = cls(project.path, options)
                    break
        elif kind != "none":
            found = plugins.load("dia.toolchains", kind)(project.path, options)
        self.dia._toolchains[project.name] = found
        return found

    def test_log_path(self, task_id: str) -> Path:
        """Where the full output of a task's last test run is kept."""
        return self.dia.config.data_dir / "logs" / f"{task_id}-tests.log"

    async def _test(self, project: ProjectConfig, workspace: Workspace) -> tuple[bool | None, str]:
        """``test_command`` if set, else the toolchain's own test; (None, "") if neither.

        The full output is also written to :meth:`test_log_path`.
        """
        result: tuple[bool | None, str] = (None, "")
        from dia.core.sandbox import for_tests

        box = for_tests(self.dia.config, project)
        if project.test_command:
            nice = TaskLimits.for_project(self.dia.config, project).nice
            command = f"nice -n {nice} {project.test_command}" if nice else project.test_command
            result = await workspace.run_tests(command, sandbox=box)
        elif toolchain := self.toolchain_for(project):
            changed = await workspace.changed_files()
            toolchain.sandbox = box
            try:
                result = await toolchain.test(workspace.path, changed) or (None, "")
            finally:
                toolchain.sandbox = None
        if result[0] is not None:
            path = self.test_log_path(workspace.path.name)  # worktrees are named after tasks
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(result[1])
        return result
