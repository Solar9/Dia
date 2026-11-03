"""Runs a task end to end: isolate, delegate to an agent, verify, record.

The orchestrator only ever touches a task's own branch on its own. Bringing
that branch into the project is a separate, explicit call (:meth:`merge_task`)
that interfaces only make when the user approves it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, TypeVar

from dia.agents import Agent, AgentRequest, AgentResult, Mode
from dia.audit import actor
from dia.core.agent_calls import AgentCaller
from dia.core.config import Config, ProjectConfig
from dia.core.forge_flow import Publisher, ci_fix_prompt, comments_prompt, publish_body  # noqa: F401
from dia.core.inbound import Inbound
from dia.core.learning import Learning
from dia.core.limits import Limits
from dia.core.merging import Merger
from dia.core.planning import Planner
from dia.core.plans import Step, step_prompt
from dia.core.prompts import EDIT_NOTE, _title, with_context  # noqa: F401
from dia.core.retry import RetryPolicy
from dia.core.review import Reviewer
from dia.core.runstate import RunState
from dia.core.store import TaskRecord, TaskStore, now
from dia.core.testing import ProjectTester
from dia.core.types import Event, TaskActionError, TaskReport, new_task_id  # noqa: F401  (re-exported)
from dia.core.workspace import (
    Workspace,
    git,
    uncommitted_files,
)
from dia.forges import CIStatus, Issue, Publication, ReviewComment
from dia.memory import Memory
from dia.toolchains import Toolchain

# Names other modules import from here (the façade also re-exports the small types).
__all__ = [
    "EDIT_NOTE",
    "Event",
    "Orchestrator",
    "TaskActionError",
    "TaskReport",
    "ci_fix_prompt",
    "comments_prompt",
    "new_task_id",
    "publish_body",
    "with_context",
]

T = TypeVar("T")
log = logging.getLogger("dia")


class Orchestrator:
    def __init__(
        self, config: Config, store: TaskStore | None = None, use_memory: bool = True
    ) -> None:
        self.config = config
        self.store = store or TaskStore(config.data_dir / "dia.db")
        self._use_memory = use_memory
        self.memory: Memory | None = config.memory() if use_memory else None
        # Limits how many agents run at once (subscription usage limits, CPU).
        self._slots = asyncio.Semaphore(config.max_parallel_tasks)
        self.listeners: list[Callable[[Event], Awaitable[None]]] = []
        self._toolchains: dict[str, Toolchain | None] = {}
        self._background: set[asyncio.Task[Any]] = set()
        self.runstate = RunState(self)
        self.calls = AgentCaller(self)
        self.reviewer = Reviewer(self)
        self.publisher = Publisher(self)
        self.learner = Learning(self)
        self.merger = Merger(self)
        self.inbound = Inbound(self)
        self.tester = ProjectTester(self)
        self.planner = Planner(self)
        self.halted = bool(self.runstate._read_state().get("halted"))
        self._wake = asyncio.Event()
        self.limits = Limits(
            config.data_dir,
            timedelta(minutes=float(config.limits.get("cooldown_minutes", 60))),
        )

    # ------------------------------------------------------ emergency stop ---

    async def stop_all(self, reason: str = "") -> list[str]:
        """Emergency stop: end every running agent and test now, and start nothing new
        (queued tasks, schedules, watchers) until :meth:`resume`. Survives restarts."""
        return await self.runstate.stop_all(reason=reason)

    async def resume(self) -> None:
        return await self.runstate.resume()

    @property
    def quiet(self) -> bool:
        """Quiet mode: Dia answers in text only (while you work, game or sleep)."""
        return self.runstate.quiet

    def set_quiet(self, on: bool) -> None:
        return self.runstate.set_quiet(on=on)

    @property
    def screen_enabled(self) -> bool:
        """Screen awareness: off unless you switched it on (see dia.screen)."""
        return self.runstate.screen_enabled

    def set_screen(self, on: bool) -> None:
        return self.runstate.set_screen(on=on)

    @property
    def camera_enabled(self) -> bool:
        """The camera: off unless you switched it on (see dia.camera)."""
        return self.runstate.camera_enabled

    def set_camera(self, on: bool) -> None:
        return self.runstate.set_camera(on=on)

    @property
    def conversations(self) -> Any:
        """The conversations every channel shares (dia.conversations)."""
        if getattr(self, "_conversations", None) is None:
            from dia.knowledge.conversations import Conversations

            self._conversations = Conversations(self)
        return self._conversations

    def _ensure_running(self) -> None:
        if self.halted:
            raise TaskActionError("Dia is stopped (emergency stop): resume it first")

    def apply_config(self, config: Config) -> None:
        """Use a changed configuration (settings saved in the UI) without a restart.

        Running tasks keep what they started with; channels that hold their own
        objects (the voice engines, the Discord token) need a restart.
        """
        self.config = config
        self.memory = config.memory() if self._use_memory else None
        self._toolchains.clear()
        self.limits.default_cooldown = timedelta(
            minutes=float(config.limits.get("cooldown_minutes", 60))
        )

    @property
    def busy(self) -> bool:
        """True when a new task would have to wait for a running one to finish."""
        return self._slots.locked()

    async def run_task(
        self,
        project_name: str,
        prompt: str,
        agent_name: str | None = None,
        mode: Mode = Mode.EDIT,
        run_tests: bool = True,
        on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
        review: bool | None = None,
        start_from: str | None = None,
        details: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> TaskReport:
        """Run a task; ``on_start`` is awaited once it is recorded (e.g. to announce its id).

        ``review``: have another agent review the changes (default: the project's
        ``auto_review`` or ``[review] auto``). ``start_from``: a branch to build on
        instead of the project's base (missions chain their steps this way).
        ``model``: this agent's model for this task (default: the agent's own setting).
        """
        self._ensure_running()
        mode = Mode(mode)  # "read-only" from an API or a config works too
        project = self.config.project(project_name)
        routed = ""
        if agent_name:  # "claude:opus": the agent with a model for this task
            agent_name, spec_model = self.config.split_agent(agent_name)
            model = model or spec_model
        if not agent_name:
            from dia.core.routing import route

            agent_name, routed = route(self.config, self.store, project, prompt)
        agent = self.config.agent(agent_name, project)
        task = TaskRecord(
            id=new_task_id(),
            project=project.name,
            agent=agent.name,
            mode=mode,
            prompt=prompt,
            status="queued",
            details={
                **(details or {}),
                **({"start_from": start_from} if start_from else {}),
                **({"routed": routed} if routed else {}),
                **({"model": model} if model else {}),
            },
        )
        self.store.save(task)
        steps = [Step(agent.name, prompt)]
        return await self._execute(task, project, steps, mode, run_tests, on_start, review)

    # -------------------------------------------------------------- plans ---

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
        return await self.planner.create_plan(
            project_name=project_name, goal=goal, pipeline=pipeline, planner=planner
        )

    async def run_plan(
        self,
        task_id: str,
        on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
        review: bool | None = None,
    ) -> TaskReport:
        return await self.planner.run_plan(task_id=task_id, on_start=on_start, review=review)

    async def _execute(
        self,
        task: TaskRecord,
        project: ProjectConfig,
        steps: list[Step],
        mode: Mode,
        run_tests: bool,
        on_start: Callable[[TaskRecord], Awaitable[None]] | None,
        review: bool | None,
    ) -> TaskReport:
        if on_start:
            await on_start(task)
        if self.halted:  # stopped while this task was waiting to start
            task.status, task.error, task.finished_at = "failed", "stopped (emergency stop)", now()
            self.store.save(task)
            return TaskReport(task=task)
        self.audit("task.start", task.id, f"{task.project} [{mode}] {task.prompt[:200]}")
        async with self._slots:
            if self.halted:  # stopped while it was queued
                task.status, task.error = "failed", "stopped (emergency stop)"
                task.finished_at = now()
                self.store.save(task)
                return TaskReport(task=task)
            task.status = "running"
            self.store.save(task)
            report = await self._run(task, project, steps, mode, run_tests)
            if mode is Mode.EDIT and task.status == "done" and task.commit_sha:
                await self._guard_quality(task, project, report)
            self.audit(
                "task.finish", task.id, task.status + (f": {task.error}" if task.error else "")
            )
            if review is None:
                review = bool(project.options.get("auto_review", self.config.review.get("auto")))
            if review and task.commit_sha and not task.error:
                try:
                    await self.reviewer._review(task, project, None, None, report)
                except Exception as exc:  # the task itself succeeded; the review is extra
                    report.warnings.append(f"review: {type(exc).__name__}: {exc}")
        if self.learning and task.status == "done":
            self.spawn(self.learn(task.id, report.diff_stat))
        return report

    async def _guard_quality(self, task: TaskRecord, project: ProjectConfig, report: Any) -> None:
        """Architecture rules and the verification gate (dia.quality)."""
        from dia.quality.quality import after_task

        try:
            _, _, workspace = self.reviewer._reviewable(task.id)
            report.warnings += await after_task(self, task, project, workspace, report.diff_stat)
        except Exception as exc:  # a guard failing must not lose the work
            log.exception("quality guards failed for %s", task.id)
            report.warnings.append(f"quality guards: {type(exc).__name__}: {exc}")

    # ----------------------------------------------------------- learning ---

    @property
    def learning(self) -> bool:
        """``[memory] learn = true``: propose facts for the project note after tasks."""
        return self.learner.learning

    def spawn(self, coro: Awaitable[Any]) -> None:
        """Background work that must not delay a task's report (see :meth:`drain`)."""
        job = asyncio.ensure_future(coro)
        self._background.add(job)
        job.add_done_callback(self._background.discard)

    async def drain(self) -> None:
        """Wait for background work, e.g. before a one-shot CLI command exits."""
        while self._background:
            await asyncio.gather(*list(self._background), return_exceptions=True)

    async def learn(self, task_id: str, diff_stat: str = "") -> list[str]:
        """Ask a (cheap) agent what is worth remembering from a finished task; the
        answer is stored as proposals waiting for a person's approval."""
        return await self.learner.learn(task_id=task_id, diff_stat=diff_stat)

    def pending_facts(self) -> list[TaskRecord]:
        """Tasks with proposed facts nobody has accepted or rejected yet."""
        return self.learner.pending_facts()

    def decide_facts(
        self, task_id: str, accept: list[int] | None = None, reject: list[int] | None = None
    ) -> list[str]:
        """Accept (append to the project note) or reject proposed facts by index;
        ``None`` for ``accept`` with no ``reject`` accepts all. Returns what was stored."""
        return self.learner.decide_facts(task_id=task_id, accept=accept, reject=reject)

    def remember(self, project_name: str, fact: str) -> None:
        """Store a fact a person states directly (`dia remember`)."""
        return self.learner.remember(project_name=project_name, fact=fact)

    async def propose_howto(self, task_id: str) -> dict[str, str]:
        """Have an agent write down how a finished task was done, as a how-to
        proposal; it is kept only when a person accepts it (:meth:`accept_howto`)."""
        return await self.learner.propose_howto(task_id=task_id)

    def accept_howto(self, task_id: str, changes: dict[str, str] | None = None) -> str:
        """Store a task's proposed how-to (with a person's edits); returns its note."""
        return self.learner.accept_howto(task_id=task_id, changes=changes)

    async def _run(
        self,
        task: TaskRecord,
        project: ProjectConfig,
        steps: list[Step],
        mode: Mode,
        run_tests: bool,
    ) -> TaskReport:
        """Run the steps one after another in one worktree, committing after each."""
        report = TaskReport(task=task)
        workspace = None
        try:
            workspace = await Workspace.create(
                project.path,
                self.config.data_dir / "worktrees" / project.name,
                task.id,
                task.details.get("start_from") or project.base_branch,
            )
            task.branch = workspace.branch
            task.details.update(base=workspace.base, worktree=str(workspace.path))
            if dirty := await uncommitted_files(project.path):
                report.warnings.append(
                    f"{len(dirty)} uncommitted file(s) in {project.path} are not visible to "
                    f"the agent (it works from the last commit of '{workspace.base}'): "
                    + ", ".join(dirty[:5])
                    + (" ..." if len(dirty) > 5 else "")
                )
            context = self._memory_call(report, "read notes", self._context, project, task.prompt)
            if context:
                task.details["memory_context_chars"] = len(context)
            if (toolchain := self.toolchain_for(project)) and (
                facts := toolchain.context(workspace.path)
            ):
                context = f"## Project\n\n{facts}" + (f"\n\n{context}" if context else "")

            policy = RetryPolicy.for_project(self.config, project)
            done: list[dict[str, Any]] = []
            for index, step in enumerate(steps):
                prompt = step_prompt(task.prompt, steps, index, done)
                agent, result = await self._attempt(
                    task,
                    workspace,
                    policy,
                    step.agent,
                    AgentRequest(
                        prompt=with_context(prompt, context or "")
                        + (EDIT_NOTE if mode is Mode.EDIT else ""),
                        cwd=workspace.path,
                        mode=mode,
                        model=task.details.get("model"),
                    ),
                )
                record = {
                    "title": step.title or step.agent,
                    "agent": agent.name,
                    "success": result.success,
                    "summary": result.summary,
                    "duration_s": round(result.duration_s, 1),
                }
                if mode is Mode.EDIT and result.success:
                    label = step.title if len(steps) > 1 else task.prompt.splitlines()[0]
                    prefix = f"step {index + 1}: " if len(steps) > 1 else ""
                    if sha := await workspace.commit(f"dia: {prefix}{label}"[:80]):
                        task.commit_sha = record["commit"] = sha
                        task.details["author"] = agent.name  # who fixes review/CI findings
                done.append(record)
                if result.session_id:
                    task.details["session_id"] = result.session_id
                if not result.success:
                    break

            if len(steps) == 1:
                task.summary = result.summary
                task.details.update(agent=result.details, duration_s=done[0]["duration_s"])
            else:
                task.summary = "\n\n".join(
                    f"### {d['title']} ({d['agent']})\n{d['summary']}" for d in done
                )
                task.details["steps"] = done
            task.error = result.error
            succeeded = all(d["success"] for d in done) and len(done) == len(steps)

            if task.commit_sha:
                report.diff_stat = await workspace.diff_stat()
                if run_tests:
                    task.tests_ok, report.test_output = await self.tester._test(project, workspace)
                    if succeeded and mode is Mode.EDIT and not task.details.get("scenario"):
                        await self.tester._fix_tests(task, project, workspace, policy, report)
            elif run_tests and task.details.get("scenario"):
                # The agent found existing tests that cover the scenario: run them as they are.
                task.tests_ok, report.test_output = await self.tester._test(project, workspace)
            task.status = "done" if succeeded and task.tests_ok is not False else "failed"
        except Exception as exc:  # recorded, then surfaced to the caller via the report
            task.status = "failed"
            task.error = f"{type(exc).__name__}: {exc}"
        finally:
            task.finished_at = now()
            self.store.save(task)
            if workspace and not task.commit_sha:
                # Nothing to review: drop the worktree and its empty branch.
                await workspace.remove(delete_branch=True)
            if self.memory:
                self._memory_call(report, "write journal", self.memory.record, project, report)
        return report

    async def _attempt(
        self,
        task: TaskRecord,
        workspace: Workspace,
        policy: RetryPolicy,
        agent_name: str,
        request: AgentRequest,
    ) -> tuple[Agent, AgentResult]:
        """One step, tried again (``[retry] agent_errors``) when the agent fails."""
        tried: list[str] = []
        name = agent_name
        while True:
            agent, result = await self.call_agent(
                self.config.agent(name), request, task, avoid=tuple(tried)
            )
            tried.append(agent.name)
            if result.success or result.limited or self.halted:
                return agent, result
            if len(tried) > policy.agent_errors:  # per step: the first try plus the retries
                return agent, result
            if policy.switch_agent:
                others = self.fallbacks(agent.name, tuple(tried))
                name = others[0] if others else agent.name
                if name != agent.name:
                    request = replace(request, model=None)  # it was chosen for the other agent
            task.details.setdefault("retries", []).append(
                {"kind": "agent", "agent": agent.name, "next": name, "error": result.error or ""}
            )
            self.store.save(task)
            await self.emit("retry", task, f"{agent.name} failed; trying again with {name}")
            await workspace.reset()
            await asyncio.sleep(policy.delay_seconds)

    # ---------------------------------------------------------- toolchain ---

    async def _test(self, project: ProjectConfig, workspace: Workspace) -> tuple[bool | None, str]:
        """Test a workspace (the project's test command or its toolchain)."""
        return await self.tester._test(project, workspace)

    def toolchain_for(self, project: ProjectConfig) -> Toolchain | None:
        """The project's toolchain: ``toolchain`` option, or detected ("auto", the default)."""
        return self.tester.toolchain_for(project=project)

    def test_log_path(self, task_id: str) -> Path:
        """Where the full output of a task's last test run is kept."""
        return self.tester.test_log_path(task_id=task_id)

    # ------------------------------------------------------------- watch ---

    async def import_issue(self, project_name: str, issue: Issue) -> TaskRecord:
        """Turn a forge issue into a plan waiting for approval (status "planned").

        The issue's text was written by someone else, so it only ever becomes
        the description of a task that a person still has to start.
        ``[issues] planner = true`` asks the planner agent for steps; otherwise
        the plan is one step for the project's default agent.
        """
        return await self.inbound.import_issue(project_name=project_name, issue=issue)

    async def project_issues(self, project_name: str) -> list[Issue]:
        return await self.inbound.project_issues(project_name=project_name)

    async def check_commit(self, project_name: str, sha: str) -> TaskRecord:
        """Test a commit of the project (as pushed or committed by a person) in a
        detached worktree; recorded as a task with mode "check"."""
        return await self.inbound.check_commit(project_name=project_name, sha=sha)

    async def fix_build(
        self, task_id: str, on_start: Callable[[TaskRecord], Awaitable[None]] | None = None
    ) -> TaskReport:
        """Give a failed check's test output to an agent as an ordinary edit task."""
        return await self.inbound.fix_build(task_id=task_id, on_start=on_start)

    async def launch(self, project_name: str) -> str:
        """Start the project (e.g. run the game) from your checkout."""
        project = self.config.project(project_name)
        self.audit("project.launch", project.name)
        toolchain = self.toolchain_for(project)
        if not toolchain:
            raise TaskActionError(f"Dia doesn't know how to launch {project.name}")
        try:
            return await toolchain.launch(project.path)
        except (RuntimeError, NotImplementedError) as exc:
            raise TaskActionError(str(exc)) from None

    # ------------------------------------------------------ after a task ---

    def reviewer_for(self, project: ProjectConfig, author: str, name: str | None = None) -> Agent:
        """The requested reviewer, else the configured one, else any agent but the author."""
        return self.reviewer.reviewer_for(project=project, author=author, name=name)

    async def review_task(
        self, task_id: str, reviewer: str | None = None, fix_rounds: int | None = None
    ) -> TaskReport:
        """Review a finished task's branch; see :meth:`_review`."""
        return await self.reviewer.review_task(
            task_id=task_id, reviewer=reviewer, fix_rounds=fix_rounds
        )

    async def diff_stat(self, task: TaskRecord) -> dict[str, int] | None:
        """Files changed and lines added/removed on a task's branch, or None (no branch now)."""
        base = task.details.get("base")
        if not (task.commit_sha and task.branch and base):
            return None
        try:
            project = self.config.project(task.project)
            out = await git(project.path, "diff", "--numstat", f"{base}...{task.branch}")
        except Exception:
            return None
        stat = {"files": 0, "added": 0, "removed": 0}
        for line in out.splitlines():
            added, removed, _ = line.split("\t", 2)
            stat["files"] += 1
            if added != "-":  # "-" for binary files
                stat["added"] += int(added)
                stat["removed"] += int(removed)
        return stat

    async def task_diff(self, task_id: str) -> str:
        """The changes on a task's branch; also after it was published (the PR/MR is still open)."""
        task = self.store.get(task_id)
        if task and task.status == "published" and task.branch and task.details.get("base"):
            project = self.config.project(task.project)
            return await git(project.path, "diff", f"{task.details['base']}...{task.branch}")
        task, _, workspace = self.reviewer._reviewable(task_id)
        return await git(workspace.repo, "diff", f"{workspace.base}...{task.branch}")

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
        return await self.merger.merge_task(task_id=task_id, reason=reason, override=override)

    async def rollback_task(self, task_id: str, reason: str | None = None) -> TaskRecord:
        """Undo a merged task: its revert is prepared as a new task on its own
        branch and tested, then merged like any other (your approval)."""
        return await self.merger.rollback_task(task_id=task_id, reason=reason)

    async def publish_task(self, task_id: str) -> Publication:
        """Push a finished task's branch and open a pull/merge request on the project's forge.

        Per project: ``forge`` ("auto", the default, decides from the remote URL;
        or "github", "gitlab", "git", any plugin) and ``forge_options`` (remote,
        draft, ...).
        """
        return await self.publisher.publish_task(task_id=task_id)

    async def ci_status(self, task_id: str) -> CIStatus:
        """Check the CI of a published task and remember the result."""
        return await self.publisher.ci_status(task_id=task_id)

    async def fix_ci(self, task_id: str) -> TaskReport:
        """Give a failed CI run's log to the task's author, then push its fix to the same branch
        (the open pull/merge request picks it up)."""
        return await self.publisher.fix_ci(task_id=task_id)

    async def review_comments(self, task_id: str) -> list[ReviewComment]:
        """New comments on a published task's pull/merge request since the last check.

        They are remembered as pending until :meth:`address_comments` handles them.
        Comments from bots are ignored unless ``forge_options.include_bots``.
        """
        return await self.publisher.review_comments(task_id=task_id)

    async def address_comments(self, task_id: str) -> TaskReport:
        """Hand the pending review comments to the task's author and push its changes."""
        return await self.publisher.address_comments(task_id=task_id)

    # ------------------------------------------------------------- events ---

    def fallbacks(self, agent: str, avoid: tuple[str, ...] = ()) -> list[str]:
        """Agents that may take over when ``agent`` is out of its usage limit."""
        return self.calls.fallbacks(agent=agent, avoid=avoid)

    async def call_agent(
        self,
        agent: Agent,
        request: AgentRequest,
        task: TaskRecord | None = None,
        avoid: tuple[str, ...] = (),
        purpose: str = "task",
    ) -> tuple[Agent, AgentResult]:
        """Run ``agent``; when it (or Dia already knows it) is out of its usage limit,
        hand the request to a fallback agent, or wait until a limit resets."""
        return await self.calls.call_agent(
            agent=agent, request=request, task=task, avoid=avoid, purpose=purpose
        )

    def sandbox_for(self, agent: Agent, task: TaskRecord | None = None) -> Any:
        """The sandbox ``agent`` runs in (dia.sandbox), or None when it is off."""
        return self.calls.sandbox_for(agent=agent, task=task)

    def limit_status(self) -> dict[str, str]:
        """Agents that are out of their usage limit, with the time it resets (ISO)."""
        return self.calls.limit_status()

    def audit(self, action: str, target: str | None = None, detail: str = "") -> None:
        """Record an action in the audit log, with whoever asked for it."""
        try:
            self.store.log_audit(actor(), action, target, detail)
        except Exception:  # the log must never break the action itself
            log.exception("audit log failed")

    async def emit(
        self, kind: str, task: TaskRecord | None, message: str, data: dict[str, Any] | None = None
    ) -> None:
        """Tell every listening channel (Discord, voice, ...) that something happened."""
        event = Event(kind, task, message, data or {})
        for listener in list(self.listeners):
            try:
                await listener(event)
            except Exception:
                log.exception("event listener failed")

    async def discard_task(self, task_id: str, reason: str | None = None) -> None:
        """Delete a task's worktree and branch (a plan nobody ran: just drop it).
        ``reason`` (why it is rejected) goes into the decision log."""
        return await self.merger.discard_task(task_id=task_id, reason=reason)

    def decide(
        self, kind: str, outcome: str, task: TaskRecord, reason: str | None = None, **detail: Any
    ) -> None:
        """Record a decision about a task (dia.decisions): merges, discards,
        rollbacks, review verdicts, rejected plans."""
        detail.setdefault("agent", task.details.get("author") or task.agent)
        try:
            self.store.log_decision(
                kind,
                outcome,
                task.prompt.strip().splitlines()[0][:300] if task.prompt.strip() else task.id,
                task.project,
                task.id,
                reason,
                actor(),
                {k: v for k, v in detail.items() if v},
            )
        except Exception:  # the log must never break the action itself
            log.exception("decision log failed")

    def _context(self, project: ProjectConfig, prompt: str) -> str:
        from dia.knowledge.preferences import preferences_text
        from dia.knowledge.profile import profile_text

        context = self.memory.context_for(project, prompt) if self.memory else ""
        if style := profile_text(self):
            prefix = f"## How the user works (their working-style profile)\n\n{style}"
            context = f"{prefix}\n\n{context}" if context else prefix
        if prefs := preferences_text(self.config):
            prefix = f"## The user's preferences\n\n{prefs}"
            context = f"{prefix}\n\n{context}" if context else prefix
        return context

    @staticmethod
    def _memory_call(report: TaskReport, what: str, fn: Callable[..., T], *args: Any) -> T | None:
        """Memory is an add-on: its failures become warnings, never failed tasks."""
        try:
            return fn(*args)
        except Exception as exc:
            report.warnings.append(f"memory: could not {what}: {type(exc).__name__}: {exc}")
            return None
