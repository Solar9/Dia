"""Watches projects while `dia serve` runs: tests every new commit.

Every ``interval`` seconds it looks at the watched branch of each project
(``[watch] branch``, else the project's ``base_branch``, else what the
checkout is on). A new commit, yours or pulled from others, is tested in a
detached worktree (:meth:`Orchestrator.check_commit`). A failure is reported
to the channels with a button that hands the log to an agent
(:meth:`Orchestrator.fix_build`); the next passing commit reports "fixed".
The last commit seen per project is kept in ``<data_dir>/watch.json``.
"""

from __future__ import annotations

import asyncio
import json
import logging

from dia.audit import ACTOR
from dia.config import ProjectConfig
from dia.orchestrator import Orchestrator
from dia.workspace import GitError, git

log = logging.getLogger("dia.watch")


class ProjectWatcher:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self.options = dia.config.watch
        self.interval = float(self.options.get("interval", 300))
        self.path = dia.config.data_dir / "watch.json"

    def projects(self) -> list[ProjectConfig]:
        names = self.options.get("projects")
        return [
            p
            for p in self.dia.config.projects.values()
            if p.options.get("watch", names is None or p.name in names)
        ]

    def _load(self) -> dict[str, dict[str, str | bool]]:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2))

    async def run(self) -> None:
        ACTOR.set("watch")
        log.info("watching %s every %ss", ", ".join(p.name for p in self.projects()), self.interval)
        while True:
            await self.poll()
            await asyncio.sleep(self.interval)

    async def head(self, project: ProjectConfig) -> str:
        branch = self.options.get("branch") or project.base_branch or "HEAD"
        return await git(project.path, "rev-parse", "--verify", f"{branch}^{{commit}}")

    async def poll(self) -> None:
        if self.dia.halted:
            return
        state = self._load()
        for project in self.projects():
            try:
                sha = await self.head(project)
            except GitError as exc:
                log.warning("watch %s: %s", project.name, exc)
                continue
            seen = state.get(project.name, {})
            if seen.get("sha") == sha:
                continue
            if not seen:  # first look: remember where we are, don't test history
                state[project.name] = {"sha": sha, "ok": True}
                self._save(state)
                continue
            check = await self.dia.check_commit(project.name, sha)
            was_ok = seen.get("ok", True)
            ok = check.tests_ok is not False
            state[project.name] = {"sha": sha, "ok": ok}
            self._save(state)
            if not ok:
                await self.dia.emit("watch", check, "failed" if was_ok else "still failing")
            elif not was_ok and check.tests_ok:
                await self.dia.emit("watch", check, "fixed")
