"""Test scenarios: "Dia, czy parry działa w nova?"

An agent writes an automated test for the behaviour you asked about (GUT or
gdUnit4 in a Godot project that has one, otherwise the project's own test
setup), without touching the game code. Dia runs the project's tests and
answers from the result: it works, it doesn't (with the failing output), or
the test could not be run. The test stays on the task's branch: merge it to
keep it as a regression test, discard it otherwise.

Retry policies never "fix" a failing scenario: a failing test is the answer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dia.agents import Mode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from dia.orchestrator import Orchestrator, TaskReport
    from dia.store import TaskRecord

PROMPT = """\
Check whether this works in the project, by writing an automated test for it:

<scenario>
{question}
</scenario>

- Write one focused test (or a few) that would pass if it works and fail if
  it doesn't. Use the project's own test framework (in a Godot project: GUT
  or gdUnit4 if present; otherwise a headless test the project's test command
  runs). Put it where the project keeps its tests.
- Do not change game or application code, even if you find the bug: this is
  a check, not a fix. Describe the bug instead.
- If the scenario cannot be tested automatically, say why and what would be
  needed.
End with a short explanation of what the test checks.
"""

ANSWERS = {
    "pl": {
        "works": "Tak, działa: test przechodzi.",
        "broken": "Nie działa: test nie przechodzi.",
        "unknown": "Nie udało się tego sprawdzić testem.",
        "keep": "Test jest na gałęzi {branch}: scal go, żeby został jako test regresji.",
    },
    "en": {
        "works": "Yes, it works: the test passes.",
        "broken": "It doesn't work: the test fails.",
        "unknown": "I couldn't check it with a test.",
        "keep": "The test is on branch {branch}: merge it to keep it as a regression test.",
    },
}


def verdict(task: TaskRecord) -> str:
    if task.tests_ok is True:
        return "works"
    if task.tests_ok is False:
        return "broken"
    return "unknown"


async def check_scenario(
    dia: Orchestrator,
    project: str | None,
    question: str,
    agent: str | None = None,
    on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
) -> TaskReport:
    from dia.orchestrator import TaskActionError

    if not project:
        raise TaskActionError("which project should I check?")
    report = await dia.run_task(
        project,
        PROMPT.format(question=question.strip()),
        agent,
        Mode.EDIT,
        on_start=on_start,
        review=False,
        details={"scenario": question.strip()},
    )
    task = report.task
    result = verdict(task)
    words = ANSWERS.get(dia.config.language, ANSWERS["en"])
    parts = [words[result]]
    if result == "broken" and report.test_output:
        parts.append(report.test_output.strip()[-1200:])
    if task.summary:
        parts.append(task.summary.strip())
    if task.branch and task.commit_sha:
        parts.append(words["keep"].format(branch=task.branch))
    task.details["scenario_result"] = result
    task.summary = "\n\n".join(parts)
    dia.store.save(task)
    return report
