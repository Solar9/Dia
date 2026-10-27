"""Notes that no longer match the code: "the save system uses JSON" while the
code moved to SQLite months ago.

``dia contradictions nova`` (or "Dia, sprawdź, czy notatki nova są aktualne",
or a schedule) gives an agent, read-only, the project's notes and asks it to
check every concrete claim in them and in the project's docs against the
code. Each contradiction comes back with where the code says otherwise and a
corrected sentence. The corrections are proposals, exactly like facts
learnt after a task: accept them (``dia learned ID --accept all``, the Memory view)
and they are added to the project note; nothing is changed by itself, and
docs in the repository are only reported, never edited.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from dia.agents import Mode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from dia.orchestrator import Orchestrator
    from dia.store import TaskRecord

MAX = 8

PROMPT = """\
Check whether the notes and documentation of this project still match its code.

Notes kept about the project (by the developer and by agents):
{notes}

Also read the project's own documentation (README, docs/, comments at the \
top of the main modules). For every concrete claim in the notes and docs \
(which library, file format, architecture, command, convention, where \
something lives) find what the code actually does. Report only claims the \
code clearly contradicts, with the file that shows it; not style, not \
missing documentation, not things you are unsure about. Change no files.

End your answer with JSON only, on its own lines, at most {max} items:
{{"contradictions": [{{"claim": "what the notes/docs say", "source": "the \
note or doc file", "evidence": "path:line and what the code does", \
"correction": "the corrected sentence for the notes"}}]}}
An empty list is a fine answer."""


def parse(text: str) -> list[dict[str, str]]:
    """The contradictions from an agent's answer ([] when there is no usable JSON)."""
    for match in reversed(list(re.finditer(r"\{.*\}", text or "", re.DOTALL))):
        try:
            items = json.loads(match.group(0)).get("contradictions", [])
        except (ValueError, AttributeError):
            continue
        found = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("claim") and item.get("correction"):
                keys = ("claim", "source", "evidence", "correction")
                found.append({k: str(item.get(k, "")).strip()[:400] for k in keys})
        return found[:MAX]
    return []


def proposal(item: dict[str, str]) -> str:
    """A contradiction as a fact to add to the notes."""
    text = item["correction"]
    if item.get("evidence"):
        text += f" (see {item['evidence']})"
    return f"{text} [corrects: {item['claim']}]"


async def check(
    dia: Orchestrator,
    project_name: str,
    agent: str | None = None,
    on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
) -> TaskRecord:
    project = dia.config.project(project_name)
    notes = dia.memory.context_for(project, "") if dia.memory else ""
    report = await dia.run_task(
        project.name,
        PROMPT.format(notes=notes.strip() or "(no notes: check the docs only)", max=MAX),
        agent or dia.config.section("contradictions").get("agent"),
        Mode.READ_ONLY,
        on_start=on_start,
        details={"check": "contradictions"},
    )
    task = report.task
    found = parse(task.summary or "")
    task.details["contradictions"] = found
    if found:
        task.details["learn"] = [{"fact": proposal(i), "status": "proposed"} for i in found]
        lines = [f"- {i['claim']} → {i['correction']} ({i['evidence']})" for i in found]
        task.summary = f"{len(found)} note(s) contradict the code:\n" + "\n".join(lines)
        if not dia.memory:
            task.summary += "\n(Memory is off: the corrections cannot be stored as notes.)"
        await dia.emit("learn", task, task.summary[:500])
    elif task.status == "done":
        task.summary = "The notes and docs match the code (nothing contradicted)."
    dia.store.save(task)
    return task
