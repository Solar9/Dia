"""Benchmarks per project: numbers over time, and a regression noticed the
moment a merge makes them worse.

    [projects.nova]
    benchmark = "godot --headless --path . res://bench/bench.tscn"
    # benchmark_runs = 3                       # median of several runs
    # benchmark_better = { fps = "higher" }    # default: lower is better
    # benchmark_tolerance = 0.05               # changes under 5 % are noise

The command prints its metrics, either as one JSON object
(``{"frame_ms": 12.4, "load_s": 1.8}``) or as lines like ``frame_ms: 12.4``
or ``fps=144``. It runs on a clean copy of a commit, in the sandbox, like the
tests. After every merge Dia runs it on the base branch and compares with the
previous result; a metric that got worse beyond the tolerance is reported
with the commits that came in. ``dia bench nova`` runs it by hand;
experiments use it to compare variants.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.workspace import GitError, Workspace, git, worktree

if TYPE_CHECKING:
    from dia.config import ProjectConfig
    from dia.orchestrator import Orchestrator

_LINE = re.compile(r"^\s*([A-Za-z][\w.\-/ ]{0,60}?)\s*[:=]\s*(-?\d+(?:\.\d+)?)\b")


def parse_metrics(output: str) -> dict[str, float]:
    """Metrics from a benchmark's output: a JSON object (the last one wins) or
    ``name: value`` / ``name=value`` lines."""
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
            except ValueError:
                continue
            numbers = {
                str(k): float(v)
                for k, v in data.items()
                if isinstance(v, int | float) and not isinstance(v, bool)
            }
            if numbers:
                return numbers
    found: dict[str, float] = {}
    for line in output.splitlines():
        if match := _LINE.match(line):
            found[match.group(1).strip()] = float(match.group(2))
    return found


def compare(
    before: dict[str, float],
    after: dict[str, float],
    better: dict[str, str] | None = None,
    tolerance: float = 0.05,
) -> list[dict[str, Any]]:
    """Per metric: the change, and whether it is worse beyond ``tolerance``."""
    better = better or {}
    changes = []
    for name in sorted(set(before) & set(after)):
        old, new = before[name], after[name]
        change = (new - old) / abs(old) if old else (0.0 if new == old else float("inf"))
        higher = better.get(name, "lower") == "higher"
        worse = (change < -tolerance) if higher else (change > tolerance)
        changes.append(
            {
                "metric": name,
                "before": old,
                "after": new,
                "change": round(change, 4),
                "worse": worse,
                "better": (change > tolerance) if higher else (change < -tolerance),
            }
        )
    return changes


def options(project: ProjectConfig) -> dict[str, Any]:
    return {
        "command": project.options.get("benchmark"),
        "runs": max(1, int(project.options.get("benchmark_runs", 1))),
        "better": dict(project.options.get("benchmark_better", {})),
        "tolerance": float(project.options.get("benchmark_tolerance", 0.05)),
        "timeout": float(project.options.get("benchmark_timeout", 1800)),
    }


async def base_branch(project: ProjectConfig) -> str:
    """The project's base branch by name (results are kept per branch)."""
    if project.base_branch:
        return project.base_branch
    try:
        return await git(project.path, "rev-parse", "--abbrev-ref", "HEAD")
    except GitError:
        return "HEAD"


async def measure(dia: Orchestrator, project: ProjectConfig, workdir: Path) -> dict[str, float]:
    """Run the project's benchmark in ``workdir`` (median of ``benchmark_runs``)."""
    from dia.sandbox import for_tests
    from dia.workspace import run

    opts = options(project)
    if not opts["command"]:
        raise ValueError(f"{project.name} has no benchmark ([projects.{project.name}] benchmark)")
    box = for_tests(dia.config, project)
    runs: list[dict[str, float]] = []
    for _ in range(opts["runs"]):
        argv: list[str] | str = opts["command"]
        if box is not None:
            argv = box.wrap(["sh", "-c", opts["command"]], workdir)
        code, out = await run(argv, workdir, opts["timeout"], stoppable=True)
        metrics = parse_metrics(out)
        if code != 0 or not metrics:
            raise RuntimeError(
                f"the benchmark failed (exit {code})"
                + ("" if metrics else ", no metrics")
                + f":\n{out.strip()[-800:]}"
            )
        runs.append(metrics)
    names = set.intersection(*(set(r) for r in runs))
    return {n: round(statistics.median(r[n] for r in runs), 6) for n in sorted(names)}


async def bench(
    dia: Orchestrator,
    project_name: str,
    ref: str | None = None,
    task_id: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Benchmark a commit on a clean, detached copy; the result is stored under
    ``label`` (default: the ref), so results of one branch can be compared."""
    project = dia.config.project(project_name)
    ref = ref or await base_branch(project)
    try:
        sha = await git(project.path, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except GitError as exc:
        raise ValueError(str(exc)) from None
    path = dia.config.data_dir / "worktrees" / project.name / f"bench-{sha[:10]}"
    workspace = Workspace(repo=project.path, path=path, branch="", base=sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        await workspace.remove()
    await worktree(project.path, "add", "--detach", str(path), sha)
    try:
        metrics = await measure(dia, project, path)
    finally:
        await workspace.remove()
    dia.store.log_benchmark(project.name, sha, metrics, label or ref, task_id)
    return {"sha": sha, "ref": ref, "metrics": metrics}


async def after_merge(
    dia: Orchestrator, project_name: str, sha: str, task_id: str | None = None
) -> list[dict[str, Any]]:
    """Benchmark the base branch after a merge; report a regression (and mark the
    merged task with it: it counts against its agent's quality)."""
    project = dia.config.project(project_name)
    opts = options(project)
    base = await base_branch(project)
    previous = dia.store.benchmarks(project.name, ref=base, limit=1)
    try:
        result = await bench(dia, project.name, sha, label=base)
    except Exception as exc:
        await dia.emit("benchmark", None, f"{project.name}: benchmark failed after merge: {exc}")
        return []
    if not previous:
        return []
    changes = compare(previous[0]["metrics"], result["metrics"], opts["better"], opts["tolerance"])
    worse = [c for c in changes if c["worse"]]
    if worse:
        try:
            log = await git(
                project.path, "log", "--oneline", "--no-merges", f"{previous[0]['sha']}..{sha}"
            )
        except GitError:
            log = ""
        listing = ", ".join(f"{c['metric']} {c['change']:+.0%}" for c in worse)
        dia.audit("benchmark.regression", project.name, listing)
        if task_id and (task := dia.store.get(task_id)):
            task.details["regression"] = worse
            dia.store.save(task)
        await dia.emit(
            "benchmark",
            None,
            f"{project.name}: worse after merge: {listing}\n{log[:800]}",
            {"project": project.name, "changes": worse, "sha": sha},
        )
    return worse


def describe(changes: list[dict[str, Any]], metrics: dict[str, float]) -> str:
    if not changes:
        return "\n".join(f"{k}: {v:g}" for k, v in metrics.items())
    lines = []
    for c in changes:
        mark = " WORSE" if c["worse"] else " better" if c["better"] else ""
        lines.append(f"{c['metric']}: {c['before']:g} → {c['after']:g} ({c['change']:+.1%}){mark}")
    return "\n".join(lines)
