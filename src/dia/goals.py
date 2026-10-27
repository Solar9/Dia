"""Goals over weeks: "Starfall do Early Access".

A goal is broken into milestones (by a planner agent, read-only, looking at
the project); milestones are reached through missions. Once a week (``dia
serve``; or ``dia goal review ID`` any time) Dia reviews it: what the
missions and tasks for it did, what blocks it (failed work, regressions,
security incidents, rolled-back merges), what changed in the repository.
The review proposes the next iteration: which milestones look done and the
next mission. Nothing starts by itself: ``dia goal approve ID`` (or the
button) records the milestones as done and prepares that mission, which you
start like any mission.

    [goals]
    review_days = 7
    planner = "claude"      # default: [missions] planner, then the default agent
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from dia.agents import AgentRequest, Mode
from dia.store import TaskRecord, now
from dia.workspace import GitError, git

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.goals")

PLAN_PROMPT = """\
A goal for this project, to reach over the coming weeks{deadline}:

<goal>
{goal}
</goal>

Look at the project and break the goal into at most {max} milestones, in \
order. Each is a result someone can check ("the inventory saves and \
loads", not "work on saving"), small enough for one or two missions. \
Change no files.

Answer with JSON only:
{{"milestones": [{{"title": "...", "done_when": "how to tell it is reached"}}]}}"""

REVIEW_PROMPT = """\
You review progress on a goal for this project, once a week.

Goal: {goal}{deadline}

Milestones:
{milestones}

Work done for it so far (missions and tasks, newest first):
{work}

Blockers Dia knows of:
{blockers}

Commits on the main line in the last {days} days:
{commits}

Look at the project where needed. Change no files. Answer with JSON only:
{{"progress": "two or three sentences: where the goal stands",
 "done": [numbers of milestones that are now reached],
 "blockers": ["what stands in the way, most important first"],
 "next": {{"milestone": number, "mission": "the next mission's goal, concrete and \
reachable in a week"}}}}"""


def _json(text: str) -> dict[str, Any]:
    for match in reversed(list(re.finditer(r"\{.*\}", text or "", re.DOTALL))):
        try:
            data = json.loads(match.group(0))
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return {}


def _planner(dia: Orchestrator, project: Any, name: str | None = None) -> Any:
    name = (
        name
        or dia.config.section("goals").get("planner")
        or dia.config.section("missions").get("planner")
        or dia.config.plans.get("planner")
    )
    return dia.config.agent(name, project)


async def _ask(dia: Orchestrator, project: Any, prompt: str, task: TaskRecord, purpose: str) -> str:
    agent = _planner(dia, project)
    _, result = await dia.call_agent(
        agent,
        AgentRequest(prompt=prompt, cwd=project.path, mode=Mode.READ_ONLY),
        task,
        purpose=purpose,
    )
    if not result.success:
        raise RuntimeError(f"{agent.name} failed: {result.error}")
    return result.summary


async def create(
    dia: Orchestrator, project_name: str, goal: str, weeks: int | None = None
) -> TaskRecord:
    from dia.orchestrator import new_task_id

    dia._ensure_running()
    project = dia.config.project(project_name)
    deadline = (datetime.now(UTC) + timedelta(weeks=weeks)).date().isoformat() if weeks else None
    record = TaskRecord(
        id=new_task_id(),
        project=project.name,
        agent="-",
        mode="goal",
        prompt=goal.strip(),
        status="running",
        details={"deadline": deadline, "milestones": [], "reviews": []},
    )
    dia.store.save(record)
    max_milestones = int(dia.config.section("goals").get("max_milestones", 6))
    answer = await _ask(
        dia,
        project,
        PLAN_PROMPT.format(
            goal=goal.strip(),
            deadline=f" (by {deadline})" if deadline else "",
            max=max_milestones,
        ),
        record,
        "plan",
    )
    milestones = [
        {"title": str(m["title"])[:200], "done_when": str(m.get("done_when", ""))[:300],
         "status": "open", "missions": []}
        for m in _json(answer).get("milestones", [])
        if isinstance(m, dict) and m.get("title")
    ][:max_milestones]  # fmt: skip
    if not milestones:
        record.status, record.error = "failed", "the planner proposed no milestones"
    else:
        record.status = "active"
        record.details["milestones"] = milestones
        record.details["last_review"] = now()  # the first review comes in a week
    dia.store.save(record)
    dia.audit("goal.create", record.id, f"{project.name}: {goal[:200]}")
    return record


def goals(dia: Orchestrator, active: bool = True) -> list[TaskRecord]:
    found = [t for t in dia.store.recent(1000) if t.mode == "goal"]
    return [t for t in found if t.status == "active"] if active else found


def _work(dia: Orchestrator, goal: TaskRecord) -> list[TaskRecord]:
    """Missions and tasks done for the goal (and the steps of those missions)."""
    linked = [t for t in dia.store.recent(2000) if t.details.get("goal") == goal.id]
    missions = {t.id for t in linked}
    linked += [t for t in dia.store.recent(2000) if t.details.get("mission") in missions]
    return linked


def blockers(dia: Orchestrator, goal: TaskRecord) -> list[str]:
    found = []
    for t in _work(dia, goal):
        title = t.prompt.splitlines()[0][:80] if t.prompt else t.id
        if t.status == "failed":
            found.append(f"failed: {title} ({t.id}): {(t.error or '')[:120]}")
        if t.details.get("reverted_by"):
            found.append(f"rolled back: {title} ({t.id})")
        for c in t.details.get("regression", []):
            found.append(f"made {c['metric']} worse: {title} ({t.id})")
        if t.details.get("incidents"):
            found.append(f"security incident: {title} ({t.id})")
    return found


async def review(dia: Orchestrator, goal_id: str) -> dict[str, Any]:
    goal = dia.store.get(goal_id)
    if not goal or goal.mode != "goal":
        raise ValueError(f"no goal {goal_id}")
    project = dia.config.project(goal.project)
    days = int(dia.config.section("goals").get("review_days", 7))
    milestones = goal.details["milestones"]
    listing = "\n".join(
        f"{i}. [{m['status']}] {m['title']} (done when: {m['done_when']})"
        for i, m in enumerate(milestones, 1)
    )
    work = "\n".join(
        f"- [{t.status}] {t.mode} {t.id}: {(t.prompt or '').splitlines()[0][:100]}"
        for t in _work(dia, goal)[:30]
    )
    try:
        commits = await git(
            project.path, "log", "--oneline", "--no-merges", f"--since={days} days ago", "-n", "40"
        )
    except GitError:
        commits = ""
    found = blockers(dia, goal)
    answer = await _ask(
        dia,
        project,
        REVIEW_PROMPT.format(
            goal=goal.prompt,
            deadline=f" (deadline {goal.details['deadline']})"
            if goal.details.get("deadline")
            else "",
            milestones=listing,
            work=work or "(nothing yet)",
            blockers="\n".join(f"- {b}" for b in found) or "(none)",
            days=days,
            commits=commits or "(none)",
        ),
        goal,
        "review",
    )
    data = _json(answer)
    done = [
        int(n) for n in data.get("done", []) if str(n).isdigit() and 0 < int(n) <= len(milestones)
    ]
    following = data.get("next") if isinstance(data.get("next"), dict) else None
    result = {
        "at": now(),
        "progress": str(data.get("progress", answer[:600])),
        "blockers": [str(b) for b in data.get("blockers", [])][:8] or found[:8],
        "done": done,
        "next": following if following and following.get("mission") else None,
        "status": "proposed",
    }
    goal = dia.store.get(goal_id) or goal
    goal.details["reviews"] = [*goal.details.get("reviews", []), result][-20:]
    goal.details["last_review"] = result["at"]
    dia.store.save(goal)
    dia.audit("goal.review", goal.id, result["progress"][:200])
    await dia.emit("goal", goal, f"{goal.prompt[:60]}: {result['progress'][:300]}")
    return result


async def approve(dia: Orchestrator, goal_id: str) -> TaskRecord | None:
    """Accept the latest review: milestones done, the next mission prepared."""
    from dia.missions import Missions

    goal = dia.store.get(goal_id)
    if not goal or goal.mode != "goal" or not goal.details.get("reviews"):
        raise ValueError(f"goal {goal_id} has no review to approve")
    latest = goal.details["reviews"][-1]
    if latest["status"] != "proposed":
        raise ValueError("the latest review was already decided")
    milestones = goal.details["milestones"]
    for n in latest["done"]:
        milestones[n - 1]["status"] = "done"
    mission = None
    if latest.get("next"):
        mission = await Missions(dia).create(goal.project, latest["next"]["mission"])
        mission.details["goal"] = goal.id
        dia.store.save(mission)
        n = int(latest["next"].get("milestone") or 0)
        if 0 < n <= len(milestones):
            milestones[n - 1]["missions"].append(mission.id)
    latest["status"] = "approved"
    if all(m["status"] == "done" for m in milestones):
        goal.status = "done"
        goal.finished_at = now()
    dia.store.save(goal)
    dia.audit("goal.approve", goal.id, mission.id if mission else "no mission")
    return mission


def close(dia: Orchestrator, goal_id: str, status: str = "done") -> None:
    goal = dia.store.get(goal_id)
    if not goal or goal.mode != "goal":
        raise ValueError(f"no goal {goal_id}")
    goal.status, goal.finished_at = status, now()
    dia.store.save(goal)
    dia.audit("goal.close", goal.id, status)


def due(dia: Orchestrator, at: datetime | None = None) -> list[TaskRecord]:
    at = at or datetime.now(UTC)
    days = int(dia.config.section("goals").get("review_days", 7))
    return [
        g
        for g in goals(dia)
        if at - datetime.fromisoformat(g.details.get("last_review") or g.created_at)
        >= timedelta(days=days)
    ]


class GoalWatcher:
    """Reviews active goals once a week while `dia serve` runs."""

    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    async def run(self) -> None:
        while True:
            for goal in due(self.dia):
                try:
                    await review(self.dia, goal.id)
                except Exception:
                    log.exception("weekly review of goal %s failed", goal.id)
            await asyncio.sleep(3600)


def describe(goal: TaskRecord) -> str:
    lines = [f"{goal.prompt}  [{goal.status}]" + (
        f", by {goal.details['deadline']}" if goal.details.get("deadline") else "")]  # fmt: skip
    for i, m in enumerate(goal.details.get("milestones", []), 1):
        mark = "x" if m["status"] == "done" else " "
        lines.append(f"  [{mark}] {i}. {m['title']}")
    if reviews := goal.details.get("reviews"):
        r = reviews[-1]
        lines.append(f"latest review ({r['at'][:10]}, {r['status']}): {r['progress']}")
        lines += [f"  blocker: {b}" for b in r["blockers"]]
        if r.get("next"):
            lines.append(f"  next mission: {r['next']['mission']}")
    return "\n".join(lines)
