"""Calling agents: usage limits, fallbacks, incidents and usage logging."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.agents import Agent, AgentRequest, AgentResult
from dia.core.store import TaskRecord
from dia.core.task_limits import TaskLimits

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia")


class AgentCaller:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    def fallbacks(self, agent: str, avoid: tuple[str, ...] = ()) -> list[str]:
        """Agents that may take over when ``agent`` is out of its usage limit."""
        option = self.dia.config.limits.get("fallback", True)
        if option is False:
            return []
        names = option if isinstance(option, list) else list(self.dia.config.agents)
        return [n for n in names if n != agent and n not in avoid and n in self.dia.config.agents]

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
        project = self.dia.config.projects.get(task.project) if task is not None else None
        limits = TaskLimits.for_project(self.dia.config, project)
        candidates = [agent.name, *self.fallbacks(agent.name, avoid)]
        max_wait = timedelta(hours=float(self.dia.config.limits.get("max_wait_hours", 6)))
        waited = timedelta()
        while True:
            for name in candidates:
                if not self.dia.limits.available(name):
                    continue
                current = agent if name == agent.name else self.dia.config.agent(name)
                if task is not None and (why := limits.exceeded(self.dia.store, task)):
                    await self.dia.emit("limit", task, why)
                    return current, AgentResult(
                        agent=current.name, success=False, summary="", error=why
                    )
                box, guard = self.sandbox_for(current, task), None
                if box is not None:
                    from dia.core.guard import Guard

                    decoys = self.dia.config.section("sandbox").get("decoys", True)
                    guard = Guard.start(self.dia.config.data_dir / "guard", decoys=bool(decoys))
                    box.decoys = guard.home
                try:
                    result = await current.run(
                        replace(
                            request,
                            # a model name belongs to the agent it was chosen for
                            model=request.model if current is agent else None,
                            sandbox=box,
                            timeout=limits.timeout(
                                self.dia.store,
                                task,
                                request.timeout or current.options.get("timeout"),
                            ),
                            nice=request.nice or limits.nice,
                        )
                    )
                    if guard is not None:
                        result = await self._incidents(guard, result, request.cwd, task)
                finally:
                    if guard is not None:
                        guard.cleanup()
                self.dia.store.log_usage(
                    current.name,
                    purpose,
                    result.duration_s,
                    result.success,
                    result.limited,
                    task,
                )
                if not result.limited:
                    if current is not agent and task is not None:
                        task.details.setdefault("fallbacks", []).append(
                            {"from": agent.name, "to": current.name}
                        )
                    return current, result
                until = self.dia.limits.block(current.name, result.retry_at)
                await self.dia.emit(
                    "limit",
                    task,
                    f"{current.name} is out of its usage limit until {until.astimezone():%H:%M}",
                )
            resets = [u for n in candidates if (u := self.dia.limits.blocked_until(n))]
            soonest = min(resets) if resets else datetime.now(UTC)
            delay = soonest - datetime.now(UTC) + timedelta(seconds=30)
            # Interactive CLI sessions must not sleep for hours on a usage limit.
            if (
                purpose == "cli-session"
                or not self.dia.config.limits.get("wait", True)
                or waited + delay > max_wait
            ):
                names = ", ".join(candidates)
                return agent, AgentResult(
                    agent=agent.name,
                    success=False,
                    summary="",
                    limited=True,
                    retry_at=soonest,
                    error=f"usage limit reached ({names}); resets at {soonest.astimezone():%H:%M}",
                )
            if task is not None:
                previous = task.status
                task.status = "waiting"
                task.details["waiting_until"] = soonest.isoformat()
                self.dia.store.save(task)
            await self.dia.emit("limit", task, f"waiting until {soonest.astimezone():%H:%M}")
            try:  # the emergency stop wakes it early
                await asyncio.wait_for(self.dia._wake.wait(), max(delay.total_seconds(), 1))
            except TimeoutError:
                pass
            if self.dia.halted:
                if task is not None:
                    task.status = previous
                    self.dia.store.save(task)
                return agent, AgentResult(
                    agent=agent.name, success=False, summary="", error="stopped (emergency stop)"
                )
            waited += delay
            if task is not None:
                task.status = previous
                task.details.pop("waiting_until", None)
                self.dia.store.save(task)

    async def _incidents(
        self, guard: Any, result: AgentResult, cwd: Path, task: TaskRecord | None
    ) -> AgentResult:
        """Record what the guard found; a decoy secret read stops the agent's work."""
        from dia.core.guard import describe

        incidents = guard.check(result, Path(cwd))
        if not incidents:
            return result
        text = describe(incidents)
        if task is not None:
            task.details.setdefault("incidents", []).extend(
                {**i.to_dict(), "agent": result.agent} for i in incidents
            )
            self.dia.store.save(task)
        self.dia.audit("guard.incident", task.id if task else None, f"{result.agent}: {text}"[:500])
        await self.dia.emit("security", task, f"{result.agent}: {text}"[:400])
        if any(i.severity == "high" for i in incidents):
            return replace(
                result,
                success=False,
                error=f"stopped by the guard: {result.agent} read a decoy secret ({text})"[:1000],
            )
        return result

    def sandbox_for(self, agent: Agent, task: TaskRecord | None = None) -> Any:
        """The sandbox ``agent`` runs in (dia.sandbox), or None when it is off."""
        from dia.core.sandbox import for_agent

        project = self.dia.config.projects.get(task.project) if task is not None else None
        return for_agent(self.dia.config, agent.kind, agent.options, project)

    def limit_status(self) -> dict[str, str]:
        """Agents that are out of their usage limit, with the time it resets (ISO)."""
        return {
            name: until.isoformat()
            for name in self.dia.config.agents
            if (until := self.dia.limits.blocked_until(name))
        }
