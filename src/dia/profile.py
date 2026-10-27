"""Your working style, learnt from your decisions, in a note you can edit.

The evidence is what you did, not what you said once: which agents' work
you merged and which you threw away (with your reasons), the plans you
turned down, what you rolled back, and the commits you made yourself on
files an agent had just changed: what you fix after agents. ``dia profile
--update`` hands that to an agent, which drafts a short profile (patterns
you accept and reject, what you correct, your priorities) keeping what the
current one says and anything you wrote into it. The draft waits for you:
``dia profile --accept`` (or the Memory view) makes it the profile, and you
can edit it any time.

Agents get the profile with every task, next to your preferences, and "jak
ja bym to zaprojektował?" is answered from it, with an alternative.

The profile is the note ``Working style.md`` in Dia's memory folder when
memory is on, else ``profile.md`` in Dia's data directory.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.agents import AgentRequest, Mode
from dia.workspace import GitError, git

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.profile")

NOTE = "Working style.md"

PROFILE_PROMPT = """\
You keep a short profile of how one developer works, for the coding agents \
that work for them. Below is the current profile (they may have edited it \
themselves: keep what they wrote) and the evidence of their recent decisions.

Write the updated profile in Markdown, at most about 25 bullet points under \
these headings: "## Accepts", "## Rejects", "## Fixes after agents", \
"## Priorities". Only patterns the evidence supports (two or more cases, or \
an explicit reason), phrased as guidance for an agent ("Prefers small \
changes over rewrites"). No names of tasks, no dates, nothing you guess.

## Current profile

{profile}

## Evidence

{evidence}

Answer with the profile only, starting with "## Accepts"."""


def _path(dia: Orchestrator) -> Path:
    return dia.config.data_dir / "profile.md"


def read(dia: Orchestrator) -> str:
    """The current profile ('' when there is none)."""
    try:
        if dia.memory:
            return dia.memory.read_note(NOTE)
        return _path(dia).read_text()
    except (OSError, ValueError):
        return ""


def write(dia: Orchestrator, text: str) -> None:
    text = text.strip() + "\n"
    if dia.memory:
        dia.memory.write_note(NOTE, text)
    else:
        _path(dia).parent.mkdir(parents=True, exist_ok=True)
        _path(dia).write_text(text)
    dia.audit("profile.write", None, f"{len(text)} characters")


def proposal(dia: Orchestrator) -> str:
    try:
        return (dia.config.data_dir / "profile.proposed.md").read_text()
    except OSError:
        return ""


def accept(dia: Orchestrator) -> str:
    draft = proposal(dia)
    if not draft.strip():
        raise ValueError("no proposed profile: dia profile --update first")
    write(dia, draft)
    (dia.config.data_dir / "profile.proposed.md").unlink()
    return draft


def profile_text(dia: Orchestrator) -> str:
    """The profile as a prompt section for agents ('' when there is none)."""
    try:
        return read(dia).strip()
    except Exception:  # never break a prompt over this
        log.exception("could not read the profile")
        return ""


async def fixes_after_agents(
    dia: Orchestrator, decision: dict[str, Any], days: int = 7
) -> list[str]:
    """Your own commits touching a merged task's files in the days after it."""
    project = dia.config.projects.get(decision["project"] or "")
    files = decision["detail"].get("files") or []
    sha = decision["detail"].get("sha")
    if not project or not files or not sha:
        return []
    until = datetime.fromisoformat(decision["at"]) + timedelta(days=days)
    try:
        out = await git(
            project.path,
            "log",
            "--no-merges",
            f"--until={until.isoformat()}",
            "--format=%ae%x09%s",
            f"{sha}..HEAD",
            "--",
            *files[:50],
        )
    except GitError:
        return []
    return [
        subject
        for line in out.splitlines()
        if "\t" in line
        for author, subject in [line.split("\t", 1)]
        if author != "dia@localhost"
    ]


async def evidence(dia: Orchestrator, days: int = 120, limit: int = 120) -> str:
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    lines = []
    for d in dia.store.decisions(limit=limit * 3):
        if d["at"] < since or d["kind"] == "review":
            continue
        agent = d["detail"].get("agent", "?")
        line = f"- {d['kind']} → {d['outcome']} ({agent}, {d['project']}): {d['title']}"
        if d["reason"]:
            line += f"\n  their reason: {d['reason'][:300]}"
        if d["kind"] == "merge":
            fixes = await fixes_after_agents(dia, d)
            if fixes:
                line += "\n  they then fixed it themselves: " + "; ".join(fixes[:4])
        lines.append(line)
        if len(lines) >= limit:
            break
    return "\n".join(lines)


async def update(dia: Orchestrator, agent_name: str | None = None) -> str:
    """Draft an updated profile from the evidence; it waits for your approval."""
    found = await evidence(dia)
    if not found:
        raise ValueError("no decisions recorded yet: merge or discard some tasks first")
    options = dia.config.section("profile")
    agent = dia.config.agent(agent_name or options.get("agent"))
    with tempfile.TemporaryDirectory(prefix="dia-profile-") as empty:
        _, result = await dia.call_agent(
            agent,
            AgentRequest(
                prompt=PROFILE_PROMPT.format(profile=read(dia) or "(none yet)", evidence=found),
                cwd=Path(empty),
                mode=Mode.READ_ONLY,
                model=options.get("model"),
                tools=False,
                timeout=int(options.get("timeout", 300)),
            ),
            purpose="profile",
        )
    if not result.success:
        raise RuntimeError(f"{agent.name} could not draft the profile: {result.error}")
    text = result.summary.strip()
    if "## " in text:
        text = text[text.index("## ") :]
    path = dia.config.data_dir / "profile.proposed.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    dia.audit("profile.propose", None, f"by {agent.name}")
    return text
