"""Research reports: "Dia, zrób research: jak inne gry roguelike robią co-op?"

An agent that can search and read the web (Claude Code: WebSearch/WebFetch;
Codex: its web search) looks into the topic, compares sources and writes a
report with links to them. It works read-only in an empty directory, or in a
project's worktree when the question is about one (then it may read the
code too). The report is a task (mode "research") and, with memory on, a note
in ``<vault>/Dia/Research/``, so later tasks can find it.

    [research]
    agent = "claude"       # an agent with web access (default: the default agent)
    model = "..."          # optional
    timeout = 1800

Treat what it finds as leads, not facts: the report lists its sources so you
can check them.
"""

from __future__ import annotations

import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dia.agents import AgentRequest, Mode
from dia.store import TaskRecord, now
from dia.workspace import Workspace

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from dia.orchestrator import Orchestrator

PROMPT = """\
Research this for the user, today being {today}:

<topic>
{topic}
</topic>
{where}
Search the web and read the most relevant, recent and trustworthy sources
(official docs, papers, postmortems, well-known authors; not SEO spam).
Compare them; note where they disagree. Then write a report in {language},
in Markdown:

# <a short title>
## Summary (3-6 sentences: the answer)
## Findings (the details, each with its source as [n])
## What it means here (concrete recommendations{for_project})
## Open questions
## Sources (numbered: title, URL, date if known)

Cite only pages you actually read. Say clearly when something is uncertain.
"""


def _slug(text: str) -> str:
    words = re.sub(r"[^\w\s-]", "", text).split()
    return " ".join(words[:8])[:70] or "research"


async def research(
    dia: Orchestrator,
    topic: str,
    project_name: str | None = None,
    agent_name: str | None = None,
    on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
) -> TaskRecord:
    from dia.orchestrator import TaskActionError, new_task_id

    dia._ensure_running()
    options = dia.config.section("research")
    project = dia.config.project(project_name) if project_name else None
    agent = dia.config.agent(agent_name or options.get("agent"), project)
    task = TaskRecord(
        id=new_task_id(),
        project=project.name if project else "-",
        agent=agent.name,
        mode="research",
        prompt=topic,
        status="running",
    )
    dia.store.save(task)
    if on_start:
        await on_start(task)
    dia.audit("research.start", task.id, topic[:200])
    workspace, scratch = None, None
    try:
        if project:
            workspace = await Workspace.create(
                project.path,
                dia.config.data_dir / "worktrees" / project.name,
                f"research-{task.id}",
                project.base_branch,
            )
            cwd = workspace.path
            where = f"\nIt is for the project {project.name} in the current directory.\n"
        else:
            scratch = tempfile.TemporaryDirectory(prefix="dia-research-")
            cwd, where = Path(scratch.name), ""
        language = {"pl": "Polish", "en": "English"}.get(dia.config.language, "English")
        _, result = await dia.call_agent(
            agent,
            AgentRequest(
                prompt=PROMPT.format(
                    topic=topic.strip(),
                    today=f"{datetime.now():%Y-%m-%d}",
                    where=where,
                    language=language,
                    for_project=f" for {project.name}" if project else "",
                ),
                cwd=cwd,
                mode=Mode.READ_ONLY,
                model=options.get("model"),
                timeout=float(options.get("timeout", 1800)),
                web=True,
            ),
            task,
            purpose="research",
        )
        if not result.success or not result.summary.strip():
            raise TaskActionError(result.error or "the agent returned no report")
        task.summary = result.summary.strip()
        if dia.memory:
            name = f"Research/{datetime.now():%Y-%m-%d} {_slug(topic)}"
            taken = {n["path"] for n in dia.memory.notes()}
            path, n = f"{name}.md", 2
            while path in taken:  # the same topic again (another agent, later): a new note
                path, n = f"{name} ({n}).md", n + 1
            front = f'---\ntags: [dia/research]\ntopic: "{topic[:200]}"\n---\n'
            try:
                dia.memory.write_note(path, front + task.summary + "\n")
                task.details["note"] = path
            except Exception as exc:  # the report itself is in the task anyway
                task.details["note_error"] = str(exc)
        task.status = "done"
    except Exception as exc:
        task.status, task.error = "failed", str(exc)[:1000]
    finally:
        task.finished_at = now()
        dia.store.save(task)
        if workspace:
            await workspace.remove(delete_branch=True)
        if scratch:
            scratch.cleanup()
    dia.audit("research.finish", task.id, task.status)
    await dia.emit("research", task, (task.summary or task.error or "").splitlines()[0][:200])
    return task
