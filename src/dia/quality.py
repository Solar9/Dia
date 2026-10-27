"""Quality guards that stand between a finished task and a merge.

**Architecture guardian.** A project's rules, in prose and optionally as
forbidden dependencies::

    [projects.nova]
    architecture = "ARCHITECTURE.md"      # default: ARCHITECTURE.md or docs/ARCHITECTURE.md
    architecture_forbid = [
      { from = "ui/**", to = "data/**", why = "UI never talks to the data layer directly" },
    ]

The forbidden dependencies are checked on every change, statically, from
the same graph ``dia impact`` uses (Godot references, imports by name): a
changed file in ``from`` that uses a file in ``to`` is a violation. The
prose rules go to the reviewer, who reports a broken one as a
``VIOLATION:`` line. Violations block merging until you override them
(``dia merge ID --override "why it is fine"``, the UI asks); the override is
a decision in the log.

**Verification gate.** After a large change (``[verification] min_lines``,
default 150 changed lines; ``always = true`` per project or globally), the
agent that wrote it is asked, read-only, which assumptions the change rests
on and a command that checks each. Dia runs the commands itself (in the
sandbox, in the task's worktree) and records which held. The agent's
confidence is not asked for; what is measured is how many of its
assumptions survived a check. A failed check blocks merging like a
violation.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.agents import AgentRequest, Mode

if TYPE_CHECKING:
    from dia.config import ProjectConfig
    from dia.orchestrator import Orchestrator
    from dia.store import TaskRecord
    from dia.workspace import Workspace

VIOLATION = re.compile(r"^\s*[-*]?\s*VIOLATION:\s*(.+)$", re.M | re.I)


# ----------------------------------------------------------- architecture ---


def rules_text(project: ProjectConfig, root: Path | None = None) -> str:
    """The project's architecture rules in prose ('' when there are none)."""
    root = root or project.path
    name = project.options.get("architecture")
    candidates = [name] if name else ["ARCHITECTURE.md", "docs/ARCHITECTURE.md"]
    for candidate in candidates:
        path = root / candidate
        if path.is_file():
            return path.read_text(errors="replace").strip()[:12000]
    return ""


def forbidden(project: ProjectConfig) -> list[dict[str, str]]:
    rules = project.options.get("architecture_forbid") or []
    return [r for r in rules if isinstance(r, dict) and r.get("from") and r.get("to")]


def _match(path: str, pattern: str) -> bool:
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern.rstrip("*/") + "/*")


def static_violations(
    root: Path, changed: list[str], rules: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Changed files that now use what a rule forbids them to use."""
    if not rules or not changed:
        return []
    from dia.impact import graph

    uses = graph(root)
    found = []
    for path in changed:
        for rule in rules:
            if not _match(path, rule["from"]):
                continue
            for used in sorted(uses.get(path, ())):
                if _match(used, rule["to"]):
                    why = rule.get("why") or f"{rule['from']} must not use {rule['to']}"
                    found.append({"rule": why, "where": f"{path} uses {used}", "by": "static"})
    return found


def review_rules(rules: str) -> str:
    """The part of a review prompt that asks the reviewer to check the rules."""
    if not rules:
        return ""
    return f"""
The project has architecture rules. Check the change against them too:

<architecture-rules>
{rules}
</architecture-rules>

For every rule the change breaks, add one line
VIOLATION: <the rule>: <file and what breaks it>
and request changes. Do not report rules the change does not touch.
"""


def parse_violations(text: str) -> list[dict[str, str]]:
    found = []
    for line in VIOLATION.findall(text or ""):
        rule, _, where = line.partition(":")
        found.append({"rule": rule.strip()[:300], "where": where.strip()[:300], "by": "review"})
    return found


# ----------------------------------------------------------- verification ---

ASSUMPTIONS_PROMPT = """\
You made this change (it is committed in the current directory):

<task>
{task}
</task>

<changed>
{diff_stat}
</changed>

List the assumptions your change depends on that could be wrong (about \
the rest of the code, data formats, the engine or library behaviour, \
performance, callers), at most {max}. For each, give a shell command run \
from this directory that exits 0 if the assumption holds and non-zero if \
not (grep, a test command for one test, a small script; it may not change \
files or use the network). Do not change any files.

Answer with JSON only: {{"assumptions": [{{"assumption": "...", "check": "..."}}]}}"""


def parse_assumptions(text: str, limit: int = 5) -> list[dict[str, str]]:
    for match in reversed(list(re.finditer(r"\{.*\}", text or "", re.DOTALL))):
        try:
            items = json.loads(match.group(0)).get("assumptions", [])
        except (ValueError, AttributeError):
            continue
        return [
            {"assumption": str(i["assumption"])[:300], "check": str(i["check"])[:500]}
            for i in items
            if isinstance(i, dict) and i.get("assumption") and i.get("check")
        ][:limit]
    return []


def _changed_lines(diff_stat: str) -> int:
    numbers = re.findall(r"(\d+) (?:insertion|deletion)", diff_stat)
    return sum(int(n) for n in numbers)


def needs_verification(dia: Orchestrator, project: ProjectConfig, diff_stat: str) -> bool:
    options = {**dia.config.section("verification"), **(project.options.get("verification") or {})}
    if options.get("enabled") is False:
        return False
    if options.get("always"):
        return True
    return _changed_lines(diff_stat) >= int(options.get("min_lines", 150))


async def verify(
    dia: Orchestrator,
    task: TaskRecord,
    project: ProjectConfig,
    workspace: Workspace,
    diff_stat: str,
) -> dict[str, Any]:
    from dia.sandbox import for_tests
    from dia.workspace import run

    options = dia.config.section("verification")
    author = dia.config.agent(task.details.get("author") or task.agent)
    _, result = await dia.call_agent(
        author,
        AgentRequest(
            prompt=ASSUMPTIONS_PROMPT.format(
                task=task.prompt.strip()[:3000],
                diff_stat=diff_stat.strip()[-2000:],
                max=int(options.get("max_checks", 5)),
            ),
            cwd=workspace.path,
            mode=Mode.READ_ONLY,
        ),
        task,
        purpose="verify",
    )
    checks = parse_assumptions(result.summary if result.success else "")
    box = for_tests(dia.config, project)
    timeout = float(options.get("timeout", 300))
    for check in checks:
        argv: list[str] | str = check["check"]
        if box is not None:
            argv = box.wrap(["sh", "-c", check["check"]], workspace.path)
        code, out = await run(argv, workspace.path, timeout, stoppable=True)
        check["held"] = code == 0
        check["output"] = out.strip()[-500:]
    held = sum(c["held"] for c in checks)
    return {
        "checks": checks,
        "held": held,
        "total": len(checks),
        "error": None if result.success else (result.error or "no answer")[:300],
    }


# --------------------------------------------------------------- the gate ---


def blockers(task: TaskRecord) -> list[str]:
    """What stops this task from merging (empty when nothing does, or overridden)."""
    if task.details.get("override"):
        return []
    found = [
        f"architecture: {v['rule']} ({v['where']})" for v in task.details.get("violations", [])
    ]
    verification = task.details.get("verification") or {}
    found += [
        f"assumption failed: {c['assumption']} ({c['check']})"
        for c in verification.get("checks", [])
        if c.get("held") is False
    ]
    return found


async def after_task(
    dia: Orchestrator,
    task: TaskRecord,
    project: ProjectConfig,
    workspace: Workspace,
    diff_stat: str,
) -> list[str]:
    """Run the guards on a finished change; returns warnings for the report."""
    warnings = []
    changed = await workspace.changed_files()
    violations = static_violations(workspace.path, changed, forbidden(project))
    if violations:
        task.details["violations"] = violations
        warnings += [f"architecture: {v['rule']}: {v['where']}" for v in violations]
    if needs_verification(dia, project, diff_stat):
        try:
            task.details["verification"] = await verify(dia, task, project, workspace, diff_stat)
        except Exception as exc:  # the change itself is done; this is an extra check
            warnings.append(f"verification: {type(exc).__name__}: {exc}")
        else:
            v = task.details["verification"]
            if v["total"]:
                warnings.append(f"verification: {v['held']}/{v['total']} assumptions held")
    dia.store.save(task)
    return warnings
