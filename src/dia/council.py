"""AI Council: several agents answer the same question, a moderator weighs them.

"Dia, zwołaj radę: jak zrobić sieć dla co-opa na 4 graczy w Godocie?" Every
member (``[council] members``, default: every agent) answers on its own,
read-only and at the same time, in the project when one is named; then the
moderator (default: the default agent) sets out where they agree, where and
why they disagree, and its recommendation. It costs one call per member plus
one, and agreement is not proof: the answers stay visible next to the summary.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from dia.agents import AgentRequest, Mode
from dia.store import TaskRecord, now
from dia.workspace import Workspace

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

MEMBER_PROMPT = """\
You are one member of a council of AI agents advising the user. Others answer
the same question independently; be yourself, not diplomatic.
{where}
Question:
{question}

Give your recommendation and the reasons for it, the main risks or costs, and
what would change your mind. Be concrete and brief (at most ~300 words).
"""

MODERATOR_PROMPT = """\
You moderate a council of AI agents. They answered this question independently:

{question}

{answers}

Write, in {language}, for the user:
1. Where they agree.
2. Where they disagree, and why (whose reasons are stronger).
3. Your recommendation, and what to check before acting on it.
Do not invent facts none of them gave. Be brief.
"""


async def convene(
    dia: Orchestrator,
    question: str,
    project_name: str | None = None,
    members: list[str] | None = None,
    moderator: str | None = None,
) -> TaskRecord:
    from dia.orchestrator import TaskActionError, new_task_id

    dia._ensure_running()
    options = dia.config.section("council")
    members = members or options.get("members") or list(dia.config.agents)
    if len(members) < 2:
        raise TaskActionError("a council needs at least two agents ([council] members)")
    project = dia.config.project(project_name) if project_name else None
    task = TaskRecord(
        id=new_task_id(),
        project=project.name if project else "-",
        agent="+".join(members),
        mode="council",
        prompt=question,
        status="running",
    )
    dia.store.save(task)
    dia.audit("council.start", task.id, question[:200])

    workspace, scratch = None, None
    try:
        if project:
            workspace = await Workspace.create(
                project.path,
                dia.config.data_dir / "worktrees" / project.name,
                f"council-{task.id}",
                project.base_branch,
            )
            cwd, where = (
                workspace.path,
                f"\nThe project is in the current directory ({project.name}); "
                "look at it as needed, read-only.\n",
            )
        else:
            scratch = tempfile.TemporaryDirectory(prefix="dia-council-")
            cwd, where = Path(scratch.name), ""

        async def ask(name: str) -> dict[str, object]:
            agent, result = await dia.call_agent(
                dia.config.agent(name),
                AgentRequest(
                    prompt=MEMBER_PROMPT.format(where=where, question=question),
                    cwd=cwd,
                    mode=Mode.READ_ONLY,
                ),
                task,
                avoid=tuple(m for m in members if m != name),
                purpose="council",
            )
            return {
                "agent": agent.name,
                "success": result.success,
                "answer": result.summary.strip() if result.success else (result.error or ""),
            }

        answers = await asyncio.gather(*(ask(name) for name in members))
        task.details["council"] = answers
        valid = [a for a in answers if a["success"] and a["answer"]]
        if not valid:
            raise TaskActionError("no member of the council answered")
        listing = "\n\n".join(f"### {a['agent']}\n{a['answer']}" for a in valid)
        language = {"pl": "Polish", "en": "English"}.get(dia.config.language, "English")
        judge = dia.config.agent(moderator or options.get("moderator"), project)
        _, verdict = await dia.call_agent(
            judge,
            AgentRequest(
                prompt=MODERATOR_PROMPT.format(
                    question=question, answers=listing, language=language
                ),
                cwd=cwd,
                mode=Mode.READ_ONLY,
                tools=False,
            ),
            task,
            purpose="council",
        )
        task.details["moderator"] = judge.name
        task.summary = verdict.summary.strip() if verdict.success else listing
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
    dia.audit("council.finish", task.id, task.status)
    return task
