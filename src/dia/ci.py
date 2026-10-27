"""Watches published tasks while `dia serve` runs: their CI and review comments.

Every ``interval`` seconds it checks published tasks whose CI has not finished,
tells the channels when a result arrives, and (with ``autofix``) hands a
failed run's log to the task's author to fix, up to ``fix_rounds`` times.
It also looks for new comments on their pull/merge requests (``watch_comments``)
and, with ``autofix_comments``, lets the author address them right away.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from dia.audit import ACTOR
from dia.orchestrator import Orchestrator, TaskActionError

log = logging.getLogger("dia.ci")


class CIWatcher:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        options = dia.config.ci
        self.interval = float(options.get("interval", 60))
        self.max_age = timedelta(hours=float(options.get("max_age_hours", 48)))

    def _autofix(self, project: str) -> tuple[bool, int]:
        options = self.dia.config.ci
        project_options = self.dia.config.project(project).options
        autofix = project_options.get("ci_autofix", options.get("autofix", False))
        return bool(autofix), int(options.get("fix_rounds", 1))

    async def run(self) -> None:
        ACTOR.set("ci")
        log.info("watching CI of published tasks every %ss", self.interval)
        while True:
            await self.poll()
            await asyncio.sleep(self.interval)

    async def poll(self) -> None:
        if self.dia.halted:
            return
        now = datetime.now(UTC)
        for task in self.dia.store.by_status("published"):
            if now - datetime.fromisoformat(task.created_at) > self.max_age:
                continue
            if self.dia.config.ci.get("watch_comments", True):
                await self._check_comments(task.id)
            if task.details.get("ci", {}).get("state") != "pending":
                continue
            try:
                status = await self.dia.ci_status(task.id)
            except (TaskActionError, LookupError) as exc:
                log.warning("CI of %s: %s", task.id, exc)
                continue
            if status.state in ("pending",):
                continue
            task = self.dia.store.get(task.id)
            autofix, rounds = self._autofix(task.project)
            fixes = task.details.get("ci_fixes", 0)
            if status.state == "failed" and autofix and fixes < rounds:
                await self.dia.emit("ci", task, "failed; asking the author to fix it")
                try:
                    await self.dia.fix_ci(task.id)
                    await self.dia.emit("ci", self.dia.store.get(task.id), "fix pushed")
                except TaskActionError as exc:
                    await self.dia.emit("ci", task, f"automatic fix failed: {exc}")
            elif status.state != "none":
                await self.dia.emit("ci", task, status.state)

    async def _check_comments(self, task_id: str) -> None:
        try:
            new = await self.dia.review_comments(task_id)
        except (TaskActionError, LookupError) as exc:
            log.warning("comments of %s: %s", task_id, exc)
            return
        if not new:
            return
        task = self.dia.store.get(task_id)
        authors = ", ".join(sorted({c.author for c in new}))
        await self.dia.emit("review", task, f"{len(new)} new comment(s) from {authors}")
        if self.dia.config.ci.get("autofix_comments", False):
            try:
                await self.dia.address_comments(task_id)
                await self.dia.emit("review", self.dia.store.get(task_id), "comments addressed")
            except TaskActionError as exc:
                await self.dia.emit("review", task, f"addressing comments failed: {exc}")
