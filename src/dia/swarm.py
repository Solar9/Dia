"""Debugging swarm: several agents look at a bug from different sides, and
their hypotheses are settled by tests, not by vote.

``dia debug nova "po dashu postać czasem przelatuje przez ścianę"``:

1. **Hypotheses.** Agents with roles work in parallel, read-only: *logs*
   (error output, the project's logs and recent test runs), *code* (the
   code paths involved), *history* (recent commits that touched them). Each
   proposes up to three causes: where, why, and what a test would show.
2. **Checks.** The most supported hypotheses (``[debug] max_checks``,
   default 3) each become a test scenario (as ``dia scenario``): an agent
   writes a test that passes if the code behaves correctly there and fails
   if the suspected cause is real. Dia runs it. A failing test confirms the
   hypothesis; a passing one rules it out; how many agents proposed it does
   not matter.
3. **Report.** The bug task lists every hypothesis with its result. A
   confirmed one can be fixed as a task that starts from the branch with
   its test (``dia debug --fix ID``, the Fix button), so the test that
   proved it guards the fix.

    [debug]
    agents = ["claude", "codex"]   # default: every configured agent
    max_checks = 3
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING, Any

from dia.agents import Mode
from dia.store import TaskRecord, now

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from dia.orchestrator import Orchestrator, TaskReport

ROLES = {
    "logs": "Look at the evidence of the failure: error output, the project's log files, "
    "recent test output, anything printed when it happens.",
    "code": "Read the code paths involved in this behaviour and look for the defect.",
    "history": "Look at recent commits that touched the code involved (git log -p) and "
    "find a change that could have introduced it.",
}

HYPOTHESES_PROMPT = """\
A bug in this project:

<bug>
{bug}
</bug>

Your role in finding its cause: {role}

Do not change any files. End with JSON only, at most 3 hypotheses, the most \
likely first:
{{"hypotheses": [{{"cause": "what is wrong", "where": "file:function or line", \
"test": "what an automated test would do to show it"}}]}}"""

CHECK_QUESTION = """\
Does the code behave correctly here, or is this suspected cause of a bug real?

Bug: {bug}
Suspected cause: {cause}
Where: {where}
How to show it: {test}

Write the test so that it PASSES when the code behaves correctly at that \
place and FAILS when the suspected cause is real."""


def parse_hypotheses(text: str) -> list[dict[str, str]]:
    for match in reversed(list(re.finditer(r"\{.*\}", text or "", re.DOTALL))):
        try:
            items = json.loads(match.group(0)).get("hypotheses", [])
        except (ValueError, AttributeError):
            continue
        return [
            {k: str(i.get(k, "")).strip()[:400] for k in ("cause", "where", "test")}
            for i in items
            if isinstance(i, dict) and i.get("cause")
        ][:3]
    return []


def _key(hypothesis: dict[str, str]) -> str:
    """Hypotheses about the same place count as the same one."""
    where = hypothesis.get("where", "").lower()
    place = re.split(r"[\s:(]", where, maxsplit=1)[0] if where else ""
    return place or " ".join(hypothesis["cause"].lower().split()[:4])


def merge(found: list[tuple[str, str, dict[str, str]]]) -> list[dict[str, Any]]:
    """(role, agent, hypothesis) from all agents -> distinct hypotheses, most backed first."""
    merged: dict[str, dict[str, Any]] = {}
    for role, agent, h in found:
        entry = merged.setdefault(_key(h), {**h, "proposed_by": []})
        entry["proposed_by"].append(f"{agent} ({role})")
    return sorted(merged.values(), key=lambda h: len(h["proposed_by"]), reverse=True)


async def debug(
    dia: Orchestrator,
    project_name: str,
    bug: str,
    agents: list[str] | None = None,
    on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
) -> TaskRecord:
    from dia.orchestrator import new_task_id
    from dia.scenario import check_scenario

    dia._ensure_running()
    project = dia.config.project(project_name)
    options = dia.config.section("debug")
    pool = agents or options.get("agents") or list(dia.config.agents)
    roles = list(ROLES)
    parent = TaskRecord(
        id=new_task_id(),
        project=project.name,
        agent="+".join(dict.fromkeys(pool)),
        mode="debug",
        prompt=bug,
        status="running",
    )
    dia.store.save(parent)
    if on_start:
        await on_start(parent)
    dia.audit("debug.start", parent.id, f"{project.name}: {bug[:200]}")
    try:

        async def investigate(i: int, role: str) -> list[tuple[str, str, dict[str, str]]]:
            agent = pool[i % len(pool)]
            report = await dia.run_task(
                project.name,
                HYPOTHESES_PROMPT.format(bug=bug.strip(), role=ROLES[role]),
                agent,
                Mode.READ_ONLY,
                details={"debug": parent.id, "role": role},
            )
            return [(role, report.task.agent, h) for h in parse_hypotheses(report.task.summary)]

        found = await asyncio.gather(*(investigate(i, r) for i, r in enumerate(roles)))
        hypotheses = merge([h for batch in found for h in batch])
        limit = int(options.get("max_checks", 3))

        async def check(h: dict[str, Any]) -> None:
            report = await check_scenario(
                dia,
                project.name,
                CHECK_QUESTION.format(
                    bug=bug.strip(), **{k: h[k] for k in ("cause", "where", "test")}
                ),
            )
            result = report.task.details.get("scenario_result")
            h["result"] = {"broken": "confirmed", "works": "ruled out"}.get(result, "unverified")
            h["check_task"] = report.task.id
            h["branch"] = report.task.branch if report.task.commit_sha else None

        await asyncio.gather(*(check(h) for h in hypotheses[:limit]))
        for h in hypotheses[limit:]:
            h["result"] = "not checked"
        parent.details["hypotheses"] = hypotheses
        lines = []
        for n, h in enumerate(hypotheses, 1):
            who = ", ".join(h["proposed_by"])
            lines.append(f"{n}. [{h['result']}] {h['cause']} ({h['where']}); from {who}")
        confirmed = [h for h in hypotheses if h["result"] == "confirmed"]
        if confirmed:
            lines.append(
                f"\nConfirmed by a failing test: {confirmed[0]['cause']}. "
                f"Fix it from its test's branch: dia debug --fix {parent.id}"
            )
        elif hypotheses:
            lines.append("\nNo hypothesis was confirmed by a test.")
        else:
            lines.append("No agent proposed a cause.")
        parent.summary = "\n".join(lines)
        parent.status = "done"
    except Exception as exc:
        parent.status, parent.error = "failed", str(exc)[:1000]
    finally:
        parent.finished_at = now()
        dia.store.save(parent)
    dia.audit("debug.finish", parent.id, parent.status)
    await dia.emit("debug", parent, (parent.summary or parent.error or "")[:300])
    return parent


async def fix(
    dia: Orchestrator,
    debug_id: str,
    on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
) -> TaskReport:
    """Fix the first confirmed cause, starting from the branch with its test."""
    from dia.orchestrator import TaskActionError

    parent = dia.store.get(debug_id)
    if not parent or parent.mode != "debug":
        raise TaskActionError(f"no debugging task {debug_id}")
    confirmed = [h for h in parent.details.get("hypotheses", []) if h["result"] == "confirmed"]
    if not confirmed:
        raise TaskActionError("no hypothesis was confirmed: nothing proven to fix")
    h = confirmed[0]
    prompt = (
        f"Fix this bug: {parent.prompt.strip()}\n\nIts cause is confirmed by a failing test "
        f"on this branch: {h['cause']} ({h['where']}). Fix the cause in the code so that "
        "test passes; do not weaken or delete the test."
    )
    return await dia.run_task(
        parent.project,
        prompt,
        on_start=on_start,
        start_from=h.get("branch"),
        details={"debug_fix": parent.id},
    )
