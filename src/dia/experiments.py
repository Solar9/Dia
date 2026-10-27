"""Experiments: "co by było, gdyby…" answered with measurements.

"Dia, sprawdź, czy przepisanie ekwipunku na ECS przyspieszy nova" becomes
several variants of the same change: by different agents, or the same agent
with different approaches ("ECS" vs "keep the nodes, cache lookups"). Each is
an ordinary task on its own branch: written in the sandbox, tested, and then
measured with the project's benchmark against the base branch. Dia shows a
table (tests, size of the change, every metric and its change) and
recommends the variant that improves most while passing its tests.

Nothing is merged: pick a variant and merge it like any task, discard the
rest. It costs one agent call per variant (plus their retries), so the number
of variants is capped.

    [experiments]
    max_variants = 3
    agents = ["claude", "codex"]     # default variants: one per agent
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

from dia.agents import Mode
from dia.store import TaskRecord, now
from dia.workspace import GitError, git

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from dia.orchestrator import Orchestrator


def plan_variants(
    dia: Orchestrator, agents: list[str] | None, approaches: list[str] | None
) -> list[dict[str, Any]]:
    options = dia.config.section("experiments")
    limit = int(options.get("max_variants", 3))
    approaches = [a for a in approaches or [] if a.strip()]
    agents = agents or []
    if approaches:
        pool = agents or [dia.config.default_agent or next(iter(dia.config.agents))]
        variants = [{"agent": pool[i % len(pool)], "approach": a} for i, a in enumerate(approaches)]
    else:
        names = agents or options.get("agents") or list(dia.config.agents)
        variants = [{"agent": name, "approach": None} for name in names]
    if len(variants) < 2:
        raise ValueError("an experiment needs at least two variants (agents or approaches)")
    return variants[:limit]


def variant_prompt(question: str, approach: str | None) -> str:
    text = question.strip()
    if approach:
        text += f"\n\nTake this approach: {approach}. Implement it fully, so it can be measured."
    return text


async def _diff_size(dia: Orchestrator, task: TaskRecord) -> dict[str, int]:
    project = dia.config.project(task.project)
    try:
        stat = await git(
            project.path, "diff", "--shortstat", f"{task.details.get('base')}...{task.branch}"
        )
    except GitError:
        return {}
    numbers = {k: int(v) for v, k in re.findall(r"(\d+) (file|insertion|deletion)", stat)}
    return {
        "files": numbers.get("file", 0),
        "added": numbers.get("insertion", 0),
        "removed": numbers.get("deletion", 0),
    }


def score(row: dict[str, Any]) -> tuple[int, int]:
    """Higher is better: metrics improved minus metrics made worse, then smaller."""
    changes = row.get("changes", [])
    net = sum(c["better"] for c in changes) - sum(c["worse"] for c in changes)
    size = row.get("size", {})
    return net, -(size.get("added", 0) + size.get("removed", 0))


def recommend(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [r for r in rows if r["status"] == "done" and r.get("tests_ok") is not False]
    return max(usable, key=score) if usable else None


def table(rows: list[dict[str, Any]], baseline: dict[str, float]) -> str:
    metrics = sorted({m for r in rows for m in r.get("metrics", {})} | set(baseline))
    head = ["variant", "agent", "status", "tests", "change", *metrics]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    if baseline:
        cells = [
            "base",
            "-",
            "-",
            "-",
            "-",
            *(f"{baseline.get(m, '-'):g}" if m in baseline else "-" for m in metrics),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    for r in rows:
        size = r.get("size", {})
        change = f"+{size.get('added', 0)}/-{size.get('removed', 0)}" if size else "-"
        tests = {True: "ok", False: "FAIL", None: "-"}[r.get("tests_ok")]
        by_metric = {c["metric"]: c for c in r.get("changes", [])}
        cells = [
            f"{r['index']}" + (f" ({r['approach']})" if r.get("approach") else ""),
            r["agent"],
            r["status"],
            tests,
            change,
        ]
        for m in metrics:
            value = r.get("metrics", {}).get(m)
            c = by_metric.get(m)
            cells.append(
                "-" if value is None else f"{value:g}" + (f" ({c['change']:+.0%})" if c else "")
            )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


async def run_experiment(
    dia: Orchestrator,
    project_name: str,
    question: str,
    agents: list[str] | None = None,
    approaches: list[str] | None = None,
    on_start: Callable[[TaskRecord], Awaitable[None]] | None = None,
) -> TaskRecord:
    from dia.benchmarks import bench, compare, options
    from dia.orchestrator import new_task_id

    dia._ensure_running()
    project = dia.config.project(project_name)
    variants = plan_variants(dia, agents, approaches)
    parent = TaskRecord(
        id=new_task_id(),
        project=project.name,
        agent="+".join(dict.fromkeys(v["agent"] for v in variants)),
        mode="experiment",
        prompt=question,
        status="running",
        details={"variants": variants},
    )
    dia.store.save(parent)
    if on_start:
        await on_start(parent)
    dia.audit("experiment.start", parent.id, f"{project.name}: {question[:200]}")
    bench_opts = options(project)
    baseline: dict[str, float] = {}
    try:
        if bench_opts["command"]:
            base = await bench(dia, project.name, task_id=parent.id)
            baseline = base["metrics"]

        # One benchmark at a time: concurrent `git worktree add` calls on a repo can
        # collide on its lock files, and parallel runs would skew each other's timings.
        measuring = asyncio.Lock()

        async def one(index: int, variant: dict[str, Any]) -> dict[str, Any]:
            report = await dia.run_task(
                project.name,
                variant_prompt(question, variant.get("approach")),
                variant["agent"],
                Mode.EDIT,
                review=False,
                details={"experiment": parent.id, "variant": index},
            )
            task = report.task
            row: dict[str, Any] = {
                "index": index,
                "task_id": task.id,
                "branch": task.branch,
                "agent": task.agent,
                "approach": variant.get("approach"),
                "status": task.status,
                "tests_ok": task.tests_ok,
            }
            if task.commit_sha:
                row["size"] = await _diff_size(dia, task)
                if bench_opts["command"] and task.tests_ok is not False:
                    try:
                        async with measuring:
                            measured = await bench(
                                dia,
                                project.name,
                                task.branch,
                                task.id,
                                label=f"experiment:{parent.id}",
                            )
                        row["metrics"] = measured["metrics"]
                        row["changes"] = compare(
                            baseline,
                            measured["metrics"],
                            bench_opts["better"],
                            bench_opts["tolerance"],
                        )
                    except Exception as exc:
                        row["bench_error"] = str(exc)[:300]
            return row

        rows = list(await asyncio.gather(*(one(i + 1, v) for i, v in enumerate(variants))))
        best = recommend(rows)
        parent.details.update(results=rows, baseline=baseline, best=best and best["index"])
        text = table(rows, baseline)
        if best:
            text += (
                f"\n\nRecommended: variant {best['index']} ({best['agent']}"
                + (f", {best['approach']}" if best.get("approach") else "")
                + f"), task {best['task_id']}: merge it, discard the others."
            )
        else:
            text += "\n\nNo variant finished with passing tests."
        if not bench_opts["command"]:
            text += "\n(No benchmark configured: compared by tests and size only.)"
        parent.summary = text
        parent.status = "done" if best else "failed"
    except Exception as exc:
        parent.status, parent.error = "failed", str(exc)[:1000]
    finally:
        parent.finished_at = now()
        dia.store.save(parent)
    dia.audit("experiment.finish", parent.id, parent.status)
    await dia.emit("experiment", parent, (parent.summary or parent.error or "")[:300])
    return parent
