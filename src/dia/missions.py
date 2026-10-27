"""Missions: give Dia a goal, it organises the work.

"Przygotuj Nova do zamkniętych testów" → a planner agent splits the goal into
steps with dependencies (a graph, not a list). Steps whose dependencies are
done run in parallel, each as an ordinary task on its own branch, built on
its dependencies' branches. When every step is done, Dia merges the last
steps' branches into the mission's branch, runs the tests, and waits for you:
the mission is then a task like any other, with Review, Merge and PR/MR.

A mission has a budget (agent calls and agent minutes, ``[missions]`` or per
mission); when it is used up, the mission pauses and can be continued. It
also has a priority and a log of what happened. Nothing is merged, pushed or
published without your approval, and the emergency stop pauses missions.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from dia.agents import AgentRequest, Mode
from dia.store import TaskRecord, now
from dia.workspace import GitError, Workspace, git, identity_args, run

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from dia.orchestrator import Orchestrator, TaskReport

MISSION_PROMPT = """\
You are organising a mission for coding agents in the project in the current
directory. Look at the code as needed, but do not change anything.

Goal:
{goal}

Available agents (use only these names):
{agents}

Split the work into 1 to {max_steps} steps. Each step is done by one agent on
its own branch, built on the steps it depends on. Steps that don't depend on
each other run at the same time, so only add a dependency when a step really
needs another's result (e.g. the implementation needs the design). Prefer few,
substantial steps; give each to the agent best suited to it. Each prompt must
be a complete, self-contained instruction.

Answer with JSON only:
{{"steps": [{{"id": "s1", "title": "...", "agent": "...", "prompt": "...",
  "depends_on": []}}]}}
"""

# Missions cancelled while running (their run loop stops starting steps).
_CANCELLED: set[str] = set()


class MissionError(Exception):
    pass


@dataclass
class MissionStep:
    id: str
    title: str
    agent: str
    prompt: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | running | done | failed | skipped
    task_id: str | None = None
    branch: str | None = None  # where its work is (its own, or its base if it changed nothing)
    error: str | None = None


def parse_mission(raw: str, agents: list[str], max_steps: int) -> list[MissionStep]:
    """Validate a planner's mission: known agents, known dependencies, no cycles."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"the planner returned no JSON mission: {raw[:200]!r}")
    data = json.loads(match.group(0))
    by_name = {a.lower(): a for a in agents}
    steps: list[MissionStep] = []
    for i, item in enumerate(data.get("steps", [])[:max_steps], 1):
        agent = by_name.get(str(item.get("agent", "")).strip().lower())
        if not agent:
            raise ValueError(f"the planner chose an unknown agent: {item.get('agent')!r}")
        prompt = str(item.get("prompt", "")).strip()
        if not prompt:
            continue
        steps.append(
            MissionStep(
                id=str(item.get("id") or f"s{i}"),
                title=str(item.get("title") or f"Step {i}").strip(),
                agent=agent,
                prompt=prompt,
                depends_on=[str(d) for d in item.get("depends_on") or []],
            )
        )
    if not steps:
        raise ValueError("the planner returned an empty mission")
    ids = [s.id for s in steps]
    if len(set(ids)) != len(ids):
        raise ValueError("the planner used the same step id twice")
    for step in steps:
        step.depends_on = [d for d in step.depends_on if d != step.id]
        if unknown := [d for d in step.depends_on if d not in ids]:
            raise ValueError(f"step {step.id} depends on unknown steps: {unknown}")
    depth(steps)  # raises on cycles
    return steps


def depth(steps: list[MissionStep]) -> dict[str, int]:
    """Each step's level in the graph (0: no dependencies); ValueError on a cycle."""
    by_id = {s.id: s for s in steps}
    levels: dict[str, int] = {}

    def visit(step_id: str, path: tuple[str, ...]) -> int:
        if step_id in path:
            raise ValueError(f"the mission's steps depend on each other in a cycle: {path}")
        if step_id not in levels:
            deps = by_id[step_id].depends_on
            levels[step_id] = 1 + max((visit(d, (*path, step_id)) for d in deps), default=-1)
        return levels[step_id]

    for step in steps:
        visit(step.id, ())
    return levels


class Missions:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    # ------------------------------------------------------------ helpers ---

    def _steps(self, mission: TaskRecord) -> list[MissionStep]:
        return [MissionStep(**s) for s in mission.details["mission"]["steps"]]

    def _store_steps(self, mission: TaskRecord, steps: list[MissionStep]) -> None:
        mission.details["mission"]["steps"] = [asdict(s) for s in steps]

    async def _log(self, mission: TaskRecord, text: str) -> None:
        mission.details["mission"].setdefault("log", []).append({"at": now(), "text": text})
        self.dia.store.save(mission)
        await self.dia.emit("mission", mission, text)

    def budget(self, mission: TaskRecord) -> dict[str, Any]:
        """The mission's limits and what its steps have used so far."""
        limits = mission.details["mission"].get("budget", {})
        task_ids = [s.task_id for s in self._steps(mission) if s.task_id]
        used = self.dia.store.usage_for(task_ids)
        return {"limits": limits, "used": used}

    def _over_budget(self, mission: TaskRecord) -> str | None:
        info = self.budget(mission)
        limits, used = info["limits"], info["used"]
        if limits.get("calls") and used["calls"] >= limits["calls"]:
            return f"budget used up: {used['calls']} of {limits['calls']} agent calls"
        if limits.get("minutes") and used["minutes"] >= limits["minutes"]:
            return f"budget used up: {used['minutes']:.0f} of {limits['minutes']} agent minutes"
        return None

    # ------------------------------------------------------------- create ---

    async def create(
        self,
        project_name: str,
        goal: str,
        planner: str | None = None,
        budget: dict[str, float] | None = None,
        priority: str = "normal",
    ) -> TaskRecord:
        """Ask the planner for the mission's steps; stored as "planned" until started."""
        from dia.orchestrator import TaskActionError, new_task_id

        self.dia._ensure_running()
        config = self.dia.config
        options = config.section("missions")
        project = config.project(project_name)
        agent = config.agent(
            planner or options.get("planner") or config.plans.get("planner"), project
        )
        roles = {
            name: opts.get("role") or f"{opts.get('type', name)} coding agent"
            for name, opts in config.agents.items()
        }
        listing = "\n".join(f"- {name}: {role}" for name, role in roles.items())
        max_steps = int(options.get("max_steps", 6))
        workspace = await Workspace.create(
            project.path,
            config.data_dir / "worktrees" / project.name,
            f"mission-plan-{new_task_id()}",
            project.base_branch,
        )
        try:
            _, result = await self.dia.call_agent(
                agent,
                AgentRequest(
                    prompt=MISSION_PROMPT.format(goal=goal, agents=listing, max_steps=max_steps),
                    cwd=workspace.path,
                    mode=Mode.READ_ONLY,
                ),
                purpose="plan",
            )
        finally:
            await workspace.remove(delete_branch=True)
        if not result.success:
            raise TaskActionError(f"planner {agent.name} failed: {result.error}")
        try:
            steps = parse_mission(result.summary, list(config.agents), max_steps)
        except ValueError as exc:
            raise TaskActionError(str(exc)) from None
        limits = {
            "calls": (budget or {}).get("calls", options.get("budget_calls", 30)),
            "minutes": (budget or {}).get("minutes", options.get("budget_minutes", 180)),
        }
        mission = TaskRecord(
            id=new_task_id(),
            project=project.name,
            agent="+".join(dict.fromkeys(s.agent for s in steps)),
            mode="mission",
            prompt=goal,
            status="planned",
            details={
                # The plan view every channel already shows (dependencies in the title).
                "plan": [
                    {
                        "agent": s.agent,
                        "prompt": s.prompt,
                        "title": s.title
                        + (f" (after {', '.join(s.depends_on)})" if s.depends_on else ""),
                    }
                    for s in steps
                ],
                "mission": {
                    "steps": [asdict(s) for s in steps],
                    "budget": limits,
                    "priority": priority,
                    "log": [{"at": now(), "text": f"planned by {agent.name}: {len(steps)} steps"}],
                },
            },
        )
        self.dia.store.save(mission)
        from dia.simulation import attach

        attach(self.dia, mission)
        self.dia.audit("mission.create", mission.id, goal[:200])
        await self.dia.emit("mission", mission, f"planned: {len(steps)} steps")
        return mission

    # ---------------------------------------------------------------- run ---

    async def run(
        self,
        mission_id: str,
        on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
    ) -> TaskReport:
        """Start (or continue) a mission and see it through to its integrated branch."""
        from dia.orchestrator import TaskActionError, TaskReport

        self.dia._ensure_running()
        mission = self.dia.store.get(mission_id)
        if not mission or mission.mode != "mission":
            raise TaskActionError(f"no mission {mission_id}")
        if mission.status not in ("planned", "paused", "failed"):
            raise TaskActionError(f"mission {mission_id} is '{mission.status}'")
        steps = self._steps(mission)
        for step in steps:  # continuing: failed and skipped steps get another go
            if step.status in ("failed", "skipped", "running"):
                step.status, step.error = "pending", None
        self._store_steps(mission, steps)
        _CANCELLED.discard(mission.id)
        project = self.dia.config.project(mission.project)
        if "base" not in mission.details:
            mission.details["base"] = project.base_branch or await git(
                project.path, "rev-parse", "--abbrev-ref", "HEAD"
            )
        mission.status, mission.error = "running", None
        self.dia.audit("mission.start", mission.id)
        await self._log(mission, "started" if not mission.finished_at else "continued")
        if on_start:
            await on_start(mission)

        running: dict[str, asyncio.Task] = {}
        stop_reason = None
        while True:
            failed = [s for s in steps if s.status == "failed"]
            if self.dia.halted:
                stop_reason = stop_reason or "emergency stop"
            elif mission.id in _CANCELLED:
                stop_reason = stop_reason or "cancelled"
            elif not failed and not stop_reason:
                stop_reason = self._over_budget(mission)
            if not failed and not stop_reason:
                done = {s.id for s in steps if s.status == "done"}
                for step in steps:
                    if step.status == "pending" and all(d in done for d in step.depends_on):
                        step.status = "running"
                        self._store_steps(mission, steps)
                        await self._log(mission, f"{step.title}: {step.agent} starts")
                        running[step.id] = asyncio.ensure_future(
                            self._run_step(mission, step, steps)
                        )
            if not running:
                break
            finished, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)
            for step_id, job in list(running.items()):
                if job in finished:
                    del running[step_id]
                    step = next(s for s in steps if s.id == step_id)
                    if exc := job.exception():
                        step.status, step.error = "failed", f"{type(exc).__name__}: {exc}"
                    self._store_steps(mission, steps)
                    outcome = step.status + (f" ({step.error})" if step.error else "")
                    await self._log(mission, f"{step.title}: {outcome}")

        mission.finished_at = now()
        if all(s.status == "done" for s in steps):
            await self._integrate(mission, steps, project)
        elif failed := [s for s in steps if s.status == "failed"]:
            mission.status = "failed"
            mission.error = "; ".join(f"{s.title}: {s.error}" for s in failed)[:1000]
            await self._log(mission, "failed")
        else:
            for step in steps:
                if step.status == "pending":
                    step.status = "skipped"
            self._store_steps(mission, steps)
            mission.status, mission.error = "paused", stop_reason
            await self._log(mission, f"paused: {stop_reason}")
        self.dia.store.save(mission)
        self.dia.audit("mission.finish", mission.id, mission.status)
        return TaskReport(task=mission)

    def cancel(self, mission_id: str) -> None:
        """Start no further steps (running ones finish; the emergency stop ends them)."""
        _CANCELLED.add(mission_id)
        self.dia.audit("mission.cancel", mission_id)

    async def _base_for(
        self, mission: TaskRecord, step: MissionStep, steps: list[MissionStep]
    ) -> str:
        """The branch a step builds on: the project's base, its dependency's branch,
        or a fresh merge of several dependencies' branches."""
        by_id = {s.id: s for s in steps}
        branches = list(dict.fromkeys(by_id[d].branch for d in step.depends_on if by_id[d].branch))
        if not branches:
            return mission.details["base"]
        if len(branches) == 1:
            return branches[0]
        project = self.dia.config.project(mission.project)
        name = f"{mission.id}-{step.id}-base"
        await self._drop(project, name)  # left over from an earlier attempt
        workspace = await Workspace.create(
            project.path, self.dia.config.data_dir / "worktrees" / project.name, name, branches[0]
        )
        try:
            await self._merge_into(
                workspace, branches[1:], f"Mission {mission.id}: base of {step.id}"
            )
        finally:
            await workspace.remove(delete_branch=False)
        mission.details["mission"].setdefault("helper_branches", []).append(workspace.branch)
        return workspace.branch

    async def _merge_into(self, workspace: Workspace, branches: list[str], message: str) -> None:
        ident = await identity_args(workspace.path)
        for branch in branches:
            code, out = await run(
                [
                    "git",
                    *ident,
                    "merge",
                    "--no-ff",
                    "--no-edit",
                    "-m",
                    f"{message} ({branch})",
                    branch,
                ],
                workspace.path,
            )
            if code != 0:
                await run(["git", "merge", "--abort"], workspace.path)
                raise MissionError(
                    f"{branch} conflicts with the other steps' work: {out.strip()[-500:]}"
                )

    async def _run_step(
        self, mission: TaskRecord, step: MissionStep, steps: list[MissionStep]
    ) -> None:
        base = await self._base_for(mission, step, steps)
        by_id = {s.id: s for s in steps}
        earlier = [
            f"- {by_id[d].title} ({by_id[d].agent})"
            + (f": {summary[:400]}" if (summary := self._summary(by_id[d])) else "")
            for d in step.depends_on
        ]
        prompt = (
            "You are one step of a larger mission. The work of the steps you depend on "
            "is already committed in this directory; build on it and do only your step.\n\n"
            f"Mission goal:\n{mission.prompt}\n\n"
            + ("Steps you build on:\n" + "\n".join(earlier) + "\n\n" if earlier else "")
            + f"Your step: {step.title}\n{step.prompt}\n"
        )
        report = await self.dia.run_task(
            mission.project,
            prompt,
            step.agent,
            start_from=base,
            review=False,
            # Steps are parts of a whole: the integrated branch is what gets tested,
            # unless [missions] step_tests asks for every step too.
            run_tests=bool(self.dia.config.section("missions").get("step_tests", False)),
            details={"mission": mission.id, "step": step.id},
        )
        task = report.task
        step.task_id = task.id
        step.branch = task.branch if task.commit_sha else base
        if task.status == "done":
            step.status = "done"
        else:
            step.status, step.error = "failed", (task.error or task.status)[:500]

    async def _drop(self, project: Any, name: str) -> None:
        """Remove Dia's own worktree and branch ``dia/<name>`` if they exist."""
        path = self.dia.config.data_dir / "worktrees" / project.name / name
        if path.exists():
            await Workspace(project.path, path, f"dia/{name}", "").remove(delete_branch=True)
        else:
            await run(["git", "branch", "-D", f"dia/{name}"], project.path)

    def _summary(self, step: MissionStep) -> str:
        task = self.dia.store.get(step.task_id) if step.task_id else None
        return (task.summary or "").strip() if task else ""

    async def _integrate(self, mission: TaskRecord, steps: list[MissionStep], project: Any) -> None:
        """Merge the last steps' branches into the mission's branch, then test it."""
        needed = {d for s in steps for d in s.depends_on}
        base = mission.details["base"]
        await self._drop(project, mission.id)  # an earlier integration (e.g. tests failed)
        leaves = list(
            dict.fromkeys(s.branch for s in steps if s.id not in needed and s.branch != base)
        )
        workspace = await Workspace.create(
            project.path, self.dia.config.data_dir / "worktrees" / project.name, mission.id, base
        )
        mission.branch = workspace.branch
        mission.details["worktree"] = str(workspace.path)
        try:
            await self._merge_into(workspace, leaves, f"Mission {mission.id}")
        except (MissionError, GitError) as exc:
            mission.status, mission.error = "failed", str(exc)
            await workspace.remove(delete_branch=True)
            mission.branch = None
            await self._log(mission, f"integration failed: {exc}")
            return
        head = await git(workspace.path, "rev-parse", "HEAD")
        changed = head != await git(project.path, "rev-parse", base)
        mission.summary = "\n\n".join(
            f"### {s.title} ({s.agent})\n{self._summary(s)}" for s in steps if self._summary(s)
        )
        if not changed:
            mission.status = "done"
            await workspace.remove(delete_branch=True)
            mission.branch = None
            await self._log(mission, "done: no changes were needed")
            return
        mission.commit_sha = head
        mission.tests_ok, output = await self.dia._test(project, workspace)
        mission.details["diff_stat"] = await workspace.diff_stat()
        mission.status = "done" if mission.tests_ok is not False else "failed"
        if mission.tests_ok is False:
            mission.error = "tests fail on the integrated branch"
        await self._log(
            mission,
            "ready for your review: merge or open a PR/MR"
            if mission.status == "done"
            else "integrated, but the tests fail",
        )

    async def cleanup(self, mission: TaskRecord) -> None:
        """After the mission is merged or discarded: drop its steps' branches."""
        project = self.dia.config.project(mission.project)
        for step in self._steps(mission):
            task = self.dia.store.get(step.task_id) if step.task_id else None
            if task and task.status == "done" and task.branch:
                try:
                    await self.dia.discard_task(task.id)
                except Exception:
                    pass
        for branch in mission.details["mission"].get("helper_branches", []):
            await run(["git", "branch", "-D", branch], project.path)
