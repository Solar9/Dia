"""What Dia does when a step fails: try again, hand it to another agent, or
let the agent fix the tests it broke.

    [retry]
    agent_errors = 1       # another attempt when an agent fails (crash, timeout)
    switch_agent = true    # ... by a different agent (the usage-limit fallbacks)
    test_fixes = 1         # failed tests go back to the author with the output
    delay_seconds = 10     # pause before an attempt

    [projects.nova]
    retry = { test_fixes = 2 }   # per project, over [retry]

All default to 0: without ``[retry]`` a failure is reported straight away.
Usage limits are not failures here; they have their own fallback and waiting
(``[limits]``). Every attempt is recorded in the task (``details.retries``)
and counts towards a mission's budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dia.config import Config, ProjectConfig


@dataclass(frozen=True)
class RetryPolicy:
    agent_errors: int = 0
    switch_agent: bool = False
    test_fixes: int = 0
    delay_seconds: float = 0

    @classmethod
    def for_project(cls, config: Config, project: ProjectConfig) -> RetryPolicy:
        options = {**config.section("retry"), **(project.options.get("retry") or {})}
        return cls(
            agent_errors=max(0, int(options.get("agent_errors", 0))),
            switch_agent=bool(options.get("switch_agent", False)),
            test_fixes=max(0, int(options.get("test_fixes", 0))),
            delay_seconds=max(0.0, float(options.get("delay_seconds", 0))),
        )


def test_fix_prompt(task_prompt: str, test_output: str, round_no: int) -> str:
    tail = test_output.strip()[-6000:] or "(no output)"
    return f"""\
You implemented this task; your changes are committed here:

<task>
{task_prompt}
</task>

The project's tests fail after your change (attempt {round_no} to fix them).
Find the cause and fix it in the code. Do not disable, skip or weaken tests to
make them pass; if a test is wrong because the task changed the behaviour on
purpose, update it and say so.

<test-output>
{tail}
</test-output>
"""
