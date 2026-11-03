"""Issues to tasks: while `dia serve` runs, open issues labelled for Dia
(``[issues] label``, default "dia") on GitHub or GitLab become plans waiting
for your approval. Run one with its button (UI, Discord) or ``dia plan --start``;
the pull/merge request it opens says "Closes #N".

Only people who can label issues (a project's maintainers, on both forges)
can hand work to Dia this way, and nothing runs until you approve it.
"""

from __future__ import annotations

import asyncio
import logging

from dia.audit import ACTOR
from dia.core.jsonfile import read_json, write_json
from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia.issues")


class IssueWatcher:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        options = dia.config.section("issues")
        self.interval = float(options.get("interval", 600))
        self.names = options.get("projects")
        self.path = dia.config.data_dir / "issues.json"

    def _load(self) -> dict[str, list[int]]:
        return read_json(self.path, {})

    async def run(self) -> None:
        ACTOR.set("issues")
        log.info("importing issues labelled for Dia every %ss", self.interval)
        while True:
            await self.poll()
            await asyncio.sleep(self.interval)

    async def poll(self) -> int:
        if self.dia.halted:
            return 0
        seen = self._load()
        imported = 0
        for name, project in self.dia.config.projects.items():
            if not project.options.get("issues", self.names is None or name in self.names):
                continue
            try:
                issues = await self.dia.project_issues(name)
            except Exception as exc:  # no gh/glab, not logged in, no network...
                log.warning("issues of %s: %s", name, exc)
                continue
            known = set(seen.get(name, []))
            for issue in issues:
                if issue.number in known:
                    continue
                await self.dia.import_issue(name, issue)
                known.add(issue.number)
                imported += 1
            seen[name] = sorted(known)
        write_json(self.path, seen)
        return imported
