"""Multi-step plans: several agents work one after another on the same branch.

A plan is a list of steps, each with its own agent and instruction. It comes
either from a pipeline in the config (a fixed recipe such as "Claude designs,
Codex implements, Cursor builds the UI") or from a planner agent that reads
the project and the goal and proposes the steps itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Step:
    agent: str
    prompt: str
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def pipeline_steps(pipeline: dict[str, Any], goal: str) -> list[Step]:
    """Steps of a ``[pipelines.<name>]`` recipe, with ``{goal}`` filled in."""
    steps = []
    for i, raw in enumerate(pipeline.get("steps", []), 1):
        if "agent" not in raw or "prompt" not in raw:
            raise ValueError(f"pipeline step {i} needs 'agent' and 'prompt'")
        steps.append(
            Step(raw["agent"], raw["prompt"].replace("{goal}", goal), raw.get("title", f"Step {i}"))
        )
    if not steps:
        raise ValueError("the pipeline has no steps")
    return steps


def step_prompt(goal: str, steps: list[Step], index: int, done: list[dict[str, Any]]) -> str:
    """What one agent is told: the whole goal, what earlier steps did, and its own step."""
    step = steps[index]
    if len(steps) == 1:
        return step.prompt
    previous = (
        "\n".join(f"- {d['title']} ({d['agent']}): {d['summary'][:500]}" for d in done)
        or "(you are the first step)"
    )
    return f"""\
You are one step of a multi-agent plan. Earlier steps' changes are already
committed in this directory; build on them and do only your own step.

Overall goal:
{goal}

Earlier steps:
{previous}

Your step ({index + 1} of {len(steps)}): {step.title}
{step.prompt}
"""


PLANNER_PROMPT = """\
You are planning how coding agents will reach this goal in the project in the
current directory. Look at the code as needed, but do not change anything.

Goal:
{goal}

Available agents (use only these names):
{agents}

Split the work into 1 to {max_steps} sequential steps, each done by one agent
on the same branch. Use several agents only where it helps (e.g. one designs,
another implements, another builds the UI or writes tests); a small goal is
one step. Each step's prompt must be a complete, self-contained instruction.

Answer with JSON only:
{{"steps": [{{"title": "...", "agent": "...", "prompt": "..."}}]}}
"""


def planner_prompt(goal: str, agents: dict[str, str], max_steps: int) -> str:
    listing = "\n".join(f"- {name}: {role}" for name, role in agents.items())
    return PLANNER_PROMPT.format(goal=goal, agents=listing, max_steps=max_steps)


def parse_plan(raw: str, agents: list[str], max_steps: int) -> list[Step]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"the planner returned no JSON plan: {raw[:200]!r}")
    data = json.loads(match.group(0))
    by_name = {a.lower(): a for a in agents}
    steps = []
    for raw_step in data.get("steps", [])[:max_steps]:
        agent = by_name.get(str(raw_step.get("agent", "")).strip().lower())
        prompt = str(raw_step.get("prompt", "")).strip()
        if not agent:
            raise ValueError(f"the planner chose an unknown agent: {raw_step.get('agent')!r}")
        if prompt:
            steps.append(Step(agent, prompt, str(raw_step.get("title", "")).strip()))
    if not steps:
        raise ValueError("the planner returned an empty plan")
    return steps
