"""Facts and how-tos Dia proposes to remember after a task."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from dia.agents import AgentRequest, Mode
from dia.core.store import TaskRecord
from dia.core.types import TaskActionError
from dia.core.workspace import (
    GitError,
    git,
)
from dia.knowledge.learn import howto_prompt, learn_prompt, parse_facts, parse_howto

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia")


class Learning:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    @property
    def learning(self) -> bool:
        """``[memory] learn = true``: propose facts for the project note after tasks."""
        return bool(self.dia.memory and (self.dia.config.memory_options or {}).get("learn"))

    async def learn(self, task_id: str, diff_stat: str = "") -> list[str]:
        """Ask a (cheap) agent what is worth remembering from a finished task; the
        answer is stored as proposals waiting for a person's approval."""
        task = self.dia.store.get(task_id)
        if not task or not self.dia.memory:
            return []
        project = self.dia.config.project(task.project)
        options = self.dia.config.memory_options or {}
        try:
            notes = self.dia._context(project, task.prompt)
            agent = self.dia.config.agent(options.get("learn_agent"), project)
            _, result = await self.dia.call_agent(
                agent,
                AgentRequest(
                    prompt=learn_prompt(
                        project.name, task.prompt, task.status, task.summary or "", diff_stat, notes
                    ),
                    cwd=project.path,
                    mode=Mode.READ_ONLY,
                    model=options.get("learn_model"),
                    tools=False,
                    timeout=int(options.get("learn_timeout", 180)),
                ),
                task,
                purpose="learn",
            )
        except Exception:
            log.exception("learning from task %s failed", task_id)
            return []
        facts = parse_facts(result.summary) if result.success else []
        if facts:
            task = self.dia.store.get(task_id) or task  # the task may have changed meanwhile
            task.details["learn"] = [{"fact": f, "status": "proposed"} for f in facts]
            self.dia.store.save(task)
            await self.dia.emit("learn", task, "\n".join(facts))
        return facts

    def pending_facts(self) -> list[TaskRecord]:
        """Tasks with proposed facts nobody has accepted or rejected yet."""
        return [
            t
            for t in self.dia.store.recent(200)
            if any(f["status"] == "proposed" for f in t.details.get("learn", []))
        ]

    def decide_facts(
        self, task_id: str, accept: list[int] | None = None, reject: list[int] | None = None
    ) -> list[str]:
        """Accept (append to the project note) or reject proposed facts by index;
        ``None`` for ``accept`` with no ``reject`` accepts all. Returns what was stored."""
        task = self.dia.store.get(task_id)
        if not task or not task.details.get("learn"):
            raise TaskActionError(f"task {task_id} has no proposed facts")
        if not self.dia.memory:
            raise TaskActionError("memory is off ([memory] in the config)")
        proposals = task.details["learn"]
        if accept is None and reject is None:
            accept = list(range(len(proposals)))
        open_ = {i for i, p in enumerate(proposals) if p["status"] == "proposed"}
        chosen = [i for i in accept or [] if i in open_]
        facts = [proposals[i]["fact"] for i in chosen]
        if facts:
            try:
                self.dia.memory.remember(self.dia.config.project(task.project), facts)
            except Exception as exc:
                raise TaskActionError(f"could not store the facts: {exc}") from None
        for i in chosen:
            proposals[i]["status"] = "accepted"
            self.dia.audit("memory.accept", task.id, proposals[i]["fact"])
        for i in reject or []:
            if i in open_ and i not in chosen:
                proposals[i]["status"] = "rejected"
        self.dia.store.save(task)
        return facts

    def remember(self, project_name: str, fact: str) -> None:
        """Store a fact a person states directly (`dia remember`)."""
        if not self.dia.memory:
            raise TaskActionError("memory is off ([memory] in the config)")
        project = self.dia.config.project(project_name)
        self.dia.audit("memory.remember", project.name, fact)
        try:
            self.dia.memory.remember(project, [" ".join(fact.split())])
        except Exception as exc:
            raise TaskActionError(f"could not store the fact: {exc}") from None

    async def propose_howto(self, task_id: str) -> dict[str, str]:
        """Have an agent write down how a finished task was done, as a how-to
        proposal; it is kept only when a person accepts it (:meth:`accept_howto`)."""
        task = self.dia.store.get(task_id)
        if not task or task.status not in ("done", "merged", "published"):
            raise TaskActionError(f"task {task_id} is not a finished task")
        if not self.dia.memory:
            raise TaskActionError("memory is off ([memory] in the config)")
        project = self.dia.config.project(task.project)
        options = self.dia.config.memory_options or {}
        diff_stat = ""
        if task.branch and task.details.get("base"):
            try:
                diff_stat = await git(
                    project.path, "diff", "--stat", f"{task.details['base']}...{task.branch}"
                )
            except GitError:
                pass
        _, result = await self.dia.call_agent(
            self.dia.config.agent(options.get("learn_agent"), project),
            AgentRequest(
                prompt=howto_prompt(project.name, task.prompt, task.summary or "", diff_stat),
                cwd=project.path,
                mode=Mode.READ_ONLY,
                model=options.get("learn_model"),
                tools=False,
            ),
            task,
            purpose="learn",
        )
        howto = parse_howto(result.summary) if result.success else None
        if not howto:
            raise TaskActionError(f"no how-to came back: {result.error or result.summary[:200]}")
        task.details["howto"] = {**howto, "status": "proposed"}
        self.dia.store.save(task)
        return howto

    def accept_howto(self, task_id: str, changes: dict[str, str] | None = None) -> str:
        """Store a task's proposed how-to (with a person's edits); returns its note."""
        task = self.dia.store.get(task_id)
        proposal = task.details.get("howto") if task else None
        if task is None or not proposal or proposal.get("status") != "proposed":
            raise TaskActionError(f"task {task_id} has no proposed how-to")
        if not self.dia.memory:
            raise TaskActionError("memory is off ([memory] in the config)")
        howto = {**proposal, **{k: v for k, v in (changes or {}).items() if v}}
        try:
            path = self.dia.memory.save_howto(
                howto["title"], howto.get("when", ""), howto["steps"], [task.project]
            )
        except Exception as exc:
            raise TaskActionError(f"could not store the how-to: {exc}") from None
        task.details["howto"] = {**howto, "status": "accepted", "path": path}
        self.dia.store.save(task)
        self.dia.audit("memory.howto", task.id, path)
        return path
