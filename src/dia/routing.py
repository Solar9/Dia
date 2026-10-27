"""Which agent takes a task when you don't name one.

    [routing]
    rules = [
      { match = "test|gut|testy", agent = "codex" },          # a regular expression
      { match = "shader|ui|menu", agent = "cursor", project = "nova" },
    ]
    auto = true        # else: the agent that gets this project's tasks done most often
    min_tasks = 5      # ... once it has done at least this many

Order: the agent you name; a matching rule; with ``auto``, the agent with the
best record on this project (from Usage → How agents do); the project's
``default_agent``; ``[dia] default_agent``. The task records why its agent was
chosen (``details.routed``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dia.config import Config, ProjectConfig
    from dia.store import TaskStore


def route(
    config: Config, store: TaskStore, project: ProjectConfig, prompt: str
) -> tuple[str | None, str]:
    """(agent, why) for a task nobody assigned; (None, "") leaves the defaults."""
    options = config.section("routing")
    for rule in options.get("rules", []):
        if rule.get("project") and rule["project"] != project.name:
            continue
        agent = rule.get("agent")
        if agent in config.agents and re.search(rule.get("match", "$^"), prompt, re.IGNORECASE):
            return agent, f"rule '{rule['match']}'"
    if options.get("auto"):
        from dia.benchmark import agent_stats, rank, why

        min_tasks = int(options.get("min_tasks", 5))
        rows = [
            r
            for r in agent_stats(store)
            if r["project"] == project.name
            and r["agent"] in config.agents
            and r["tasks"] >= min_tasks
        ]
        if rows:
            best = max(rows, key=lambda r: (*rank(r), -r["minutes"]))
            return best["agent"], f"best record on {project.name}: {why(best)}"
    return None, ""
