"""Dia proposes what is worth remembering about a project after a task.

A cheap model call reads the task's request and outcome and proposes up to a
few facts that will help future tasks (conventions, architecture, pitfalls).
Nothing is written until a person accepts a proposal; accepted facts are
appended to the project's memory note.
"""

from __future__ import annotations

import json
import re

MAX_FACTS = 3

LEARN_PROMPT = """\
You keep the notes that coding agents read before working on the project \
"{project}". A task on it has just finished.

Task: {task}

Outcome ({status}):
{summary}

Changed files:
{diff_stat}

The project's notes so far:
{notes}

Propose at most {max_facts} short facts that a future agent working on this \
project should know: conventions, architecture, commands, pitfalls, decisions. \
Only lasting knowledge about the project, nothing about this one task, nothing \
the notes already say, nothing you are unsure of. Proposing nothing is fine \
and usual.

Answer with JSON only: {{"facts": ["...", "..."]}}"""


def learn_prompt(
    project: str, task: str, status: str, summary: str, diff_stat: str, notes: str
) -> str:
    return LEARN_PROMPT.format(
        project=project,
        task=task.strip()[:2000],
        status=status,
        summary=(summary or "(none)").strip()[:4000],
        diff_stat=(diff_stat or "(none)").strip()[:1500],
        notes=(notes or "(none)").strip()[:4000],
        max_facts=MAX_FACTS,
    )


def parse_facts(text: str) -> list[str]:
    """The facts from a model's answer; nothing when it is not the expected JSON."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return []
    try:
        facts = json.loads(match.group(0)).get("facts", [])
    except (ValueError, AttributeError):
        return []
    clean = [" ".join(str(f).split()) for f in facts if isinstance(f, str)]
    return [f[:300] for f in clean if f][:MAX_FACTS]


HOWTO_PROMPT = """\
A task on the project "{project}" has just been done. Turn how it was done
into a how-to that coding agents will follow the next time a similar task
comes up (procedural memory).

Task: {task}

What the agent did:
{summary}

Changed files:
{diff_stat}

Write a reusable procedure, not a report on this one task: the steps, the
commands, which files are involved, what to check at the end. Leave out
anything specific to this task alone. Answer with JSON only:
{{"title": "short name, e.g. Adding an enemy type",
  "when": "words describing the tasks it applies to",
  "steps": "Markdown, numbered steps"}}"""


def howto_prompt(project: str, task: str, summary: str, diff_stat: str) -> str:
    return HOWTO_PROMPT.format(
        project=project,
        task=task.strip()[:2000],
        summary=(summary or "(none)").strip()[:6000],
        diff_stat=(diff_stat or "(none)").strip()[:1500],
    )


def parse_howto(text: str) -> dict[str, str] | None:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    try:
        data = json.loads(match.group(0), strict=False) if match else {}  # raw newlines
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    howto = {k: str(data.get(k) or "").strip() for k in ("title", "when", "steps")}
    return howto if howto["title"] and howto["steps"] else None
