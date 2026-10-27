"""Plan simulation: what a plan will likely touch, cost and risk, before it runs.

Every plan and mission is shown with:

- **files** it will likely touch: files the goal and the steps name (paths,
  file names, functions; as ``dia impact`` finds them) and files that past
  tasks about the same things changed (the decision log);
- **expected cost** from history: each step's agent's average minutes on
  this project, and the agent calls (with the retries the policy allows);
- **risks**: likely files that were rolled back or made a benchmark worse
  before, that carry technical debt, that an architecture rule guards, or
  that no test names; a change large enough for the verification gate;
- **approvals**: the points where it waits for you.

All of it is read from the project and Dia's own history: no agent runs.
Nothing of the plan runs before you accept it, as before.
"""

from __future__ import annotations

import fnmatch
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator
    from dia.store import TaskRecord


def _likely_files(dia: Orchestrator, project_name: str, text: str) -> list[dict[str, str]]:
    from dia.decisions import terms
    from dia.impact import find_targets

    project = dia.config.project(project_name)
    found: dict[str, str] = {}
    for path in re.findall(r"[\w./-]+\.(?:gd|tscn|tres|py|js|ts|cs|rs|go|md|json)\b", text):
        if (project.path / path).is_file():
            found.setdefault(path, "named in the plan")
    for term in terms(text)[:12]:
        if len(term) < 4:
            continue
        for path in find_targets(project.path, term)[:3]:
            found.setdefault(path, f"matches '{term}'")
    # Files earlier tasks about the same things changed.
    stems = terms(text)
    counts: Counter[str] = Counter()
    for d in dia.store.decisions(project.name, limit=500):
        if d["kind"] == "merge" and sum(s in d["title"].lower() for s in stems) >= 2:
            counts.update(d["detail"].get("files", []))
    for path, n in counts.most_common(5):
        found.setdefault(path, f"changed by {n} similar task(s) before")
    return [{"file": f, "why": w} for f, w in list(found.items())[:12]]


def _cost(dia: Orchestrator, project_name: str, agents: list[str]) -> dict[str, Any]:
    from dia.benchmark import agent_stats
    from dia.retry import RetryPolicy

    project = dia.config.project(project_name)
    stats = {r["agent"]: r for r in agent_stats(dia.store) if r["project"] == project_name}
    known = [stats[a]["minutes"] for a in agents if a in stats]
    fallback = sum(known) / len(known) if known else None
    minutes = [stats[a]["minutes"] if a in stats else fallback for a in agents]
    policy = RetryPolicy.for_project(dia.config, project)
    worst = len(agents) * (1 + policy.agent_errors + policy.test_fixes)
    return {
        "minutes": round(sum(m for m in minutes if m is not None), 1) if known else None,
        "calls": len(agents),
        "calls_worst": worst,
        "from_tasks": sum(stats[a]["tasks"] for a in set(agents) if a in stats),
    }


def _risks(dia: Orchestrator, project_name: str, files: list[str]) -> list[str]:
    from dia.debt import saved
    from dia.quality import forbidden

    project = dia.config.project(project_name)
    risks = []
    rolled: Counter[str] = Counter()
    for d in dia.store.decisions(project_name, limit=1000):
        task = dia.store.get(d["task_id"]) if d["kind"] == "merge" and d["task_id"] else None
        if task and (task.details.get("reverted_by") or task.details.get("regression")):
            rolled.update(set(d["detail"].get("files", [])) & set(files))
    for path, n in rolled.most_common(3):
        risks.append(f"{path}: {n} earlier change(s) rolled back or made a benchmark worse")
    debt = {i["file"]: i for i in saved(dia, project_name)}
    for path in files:
        if path in debt:
            risks.append(f"{path}: technical debt ({debt[path]['kind']}: {debt[path]['detail']})")
    for rule in forbidden(project):
        if any(fnmatch.fnmatch(f, rule["from"]) for f in files):
            risks.append(f"architecture rule in play: {rule.get('why') or rule['from']}")
    tests = [p for p in files if "test" in p.lower()]
    code = [p for p in files if "test" not in p.lower() and Path(p).suffix in (".gd", ".py")]
    if code and not tests:
        risks.append("no tests among the likely files: consider a scenario first")
    if len(files) >= 8:
        risks.append(f"touches many files ({len(files)}+): the verification gate will likely run")
    return risks


def simulate(dia: Orchestrator, plan: TaskRecord) -> dict[str, Any]:
    steps = plan.details.get("plan", [])
    text = " ".join([plan.prompt, *(s.get("prompt", "") for s in steps)])
    files = _likely_files(dia, plan.project, text)
    agents = [s["agent"] for s in steps] or [plan.agent]
    approvals = ["you accept the plan (nothing runs before)"]
    approvals.append(
        "you review and merge the mission's result"
        if plan.mode == "mission"
        else "you review and merge each finished step"
    )
    publishing = re.compile(r"publish|release|itch|steam|deploy", re.I)
    if any(publishing.search(s.get("prompt", "")) for s in steps):
        approvals.append("publishing stays a separate approval")
    return {
        "files": files,
        "cost": _cost(dia, plan.project, agents),
        "risks": _risks(dia, plan.project, [f["file"] for f in files]),
        "approvals": approvals,
    }


def attach(dia: Orchestrator, plan: TaskRecord) -> None:
    """Add the simulation to a stored plan; a failure only leaves it out."""
    try:
        plan.details["simulation"] = simulate(dia, plan)
        dia.store.save(plan)
    except Exception:
        import logging

        logging.getLogger("dia.simulation").exception("plan simulation failed")


def describe(sim: dict[str, Any] | None) -> str:
    if not sim:
        return ""
    cost = sim["cost"]
    lines = []
    if sim["files"]:
        lines.append("Likely files: " + ", ".join(f["file"] for f in sim["files"][:8]))
    if cost["minutes"] is not None:
        lines.append(
            f"Expected: ~{cost['minutes']:g} agent minutes, {cost['calls']} call(s) "
            f"(up to {cost['calls_worst']} with retries; from {cost['from_tasks']} past tasks)"
        )
    else:
        calls = f"{cost['calls']} call(s), up to {cost['calls_worst']}"
        lines.append(f"Expected: {calls}; no history yet")
    if sim["risks"]:
        lines.append("Risks: " + "; ".join(sim["risks"]))
    lines.append("Waits for you: " + "; ".join(sim["approvals"]))
    return "\n".join(lines)
