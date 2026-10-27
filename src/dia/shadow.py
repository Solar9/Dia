"""Shadow brain: try another brain on real requests before trusting it.

Every request the assistant understood is kept (``intents`` in the task
store: the text, the action, the project, the skill, which brain). ``dia
brains --replay 50 --brain local`` gives the last 50 of them to another brain
and compares: does it pick the same action, the same project, the same skill?
Nothing is executed; the candidate only interprets. When a local model agrees
with the cloud one on 95 % of your own requests, it can go first in the chain.

Only the request text is replayed, without the conversation around it, so a
follow-up like "and for nova too" may legitimately differ.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dia.brains import Brain, BrainContext
    from dia.store import TaskStore


async def replay(
    brain: Brain, store: TaskStore, ctx: BrainContext, limit: int = 50
) -> dict[str, Any]:
    """How often ``brain`` agrees with what was decided before."""
    logged = [i for i in store.intents(limit * 2) if i["brain"] != brain.name][:limit]
    rows = []
    for old in reversed(logged):
        try:
            new = await brain.interpret(old["text"], ctx)
            got: dict[str, Any] = (
                {"action": new.action, "project": new.project, "skill": new.skill}
                if new
                else {"action": None, "project": None, "skill": None, "passed": True}
            )
        except Exception as exc:
            got = {"action": None, "project": None, "skill": None, "error": str(exc)[:200]}
        same = (
            got["action"] == old["action"]
            and got["project"] == old["project"]
            and got["skill"] == old["skill"]
        )
        rows.append({"text": old["text"], "before": old, "now": got, "same": same})
    agreed = sum(r["same"] for r in rows)
    return {
        "brain": brain.name,
        "requests": len(rows),
        "agreed": agreed,
        "agreement": round(agreed / len(rows), 2) if rows else None,
        "same_action": sum(r["now"]["action"] == r["before"]["action"] for r in rows),
        "errors": sum("error" in r["now"] for r in rows),
        "differences": [r for r in rows if not r["same"]],
    }


def describe_difference(row: dict[str, Any]) -> str:
    def what(d: dict[str, Any]) -> str:
        if d.get("error"):
            return f"error: {d['error']}"
        if d.get("passed"):
            return "(passes)"
        return " ".join(str(d[k]) for k in ("action", "project", "skill") if d.get(k))

    return f'"{row["text"][:70]}": was {what(row["before"])}, now {what(row["now"])}'
