import subprocess
from pathlib import Path

import pytest

from dia.config import parse_config
from dia.experiments import plan_variants, recommend, run_experiment, variant_prompt
from dia.orchestrator import Orchestrator


def make(tmp_path: Path, repo: Path, **experiments) -> Orchestrator:
    (repo / "frame_ms").write_text("10\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "bench"],
        cwd=repo,
        check=True,
    )

    def agent(value: str) -> dict:
        return {"type": "command", "argv": ["sh", "-c", f"echo {value} > frame_ms; echo done"]}

    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "slow"},
        # "slow" makes it worse, "fast" better, "broken" fails its tests.
        "agents": {"slow": agent("13"), "fast": agent("7"), "broken": agent("x")},
        "projects": {
            "demo": {
                "path": str(repo),
                "benchmark": 'echo "frame_ms: $(cat frame_ms)"',
                "test_command": "grep -q '^[0-9]' frame_ms",
            }
        },
        "experiments": experiments,
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_variants_are_measured_and_the_best_recommended(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    main = subprocess.run(
        ["git", "rev-parse", "main"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    task = await run_experiment(dia, "demo", "make rendering faster", ["slow", "fast", "broken"])
    assert task.mode == "experiment" and task.status == "done"
    rows = {r["agent"]: r for r in task.details["results"]}
    assert rows["fast"]["metrics"] == {"frame_ms": 7.0}
    assert rows["slow"]["changes"][0]["worse"]
    assert rows["broken"]["tests_ok"] is False and "metrics" not in rows["broken"]
    assert task.details["best"] == rows["fast"]["index"]
    assert "Recommended: variant 2 (fast" in task.summary
    assert "| base |" in task.summary and "7 (-30%)" in task.summary
    # Nothing merged; every variant is an ordinary task, kept for review.
    assert (
        subprocess.run(
            ["git", "rev-parse", "main"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()
        == main
    )
    variants = [dia.store.get(r["task_id"]) for r in task.details["results"]]
    assert all(v.details["experiment"] == task.id for v in variants)
    await dia.merge_task(rows["fast"]["task_id"])  # the chosen one merges normally
    await dia.drain()  # its benchmark after the merge
    assert (repo / "frame_ms").read_text().strip() == "7"


async def test_without_a_benchmark_it_compares_tests_and_size(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    dia.config.projects["demo"].options.pop("benchmark")
    task = await run_experiment(dia, "demo", "x", ["broken", "slow"])
    assert task.details["best"] == 2 and "No benchmark configured" in task.summary


def test_planning(tmp_path, repo) -> None:
    dia = make(tmp_path, repo, max_variants=2)
    assert [v["agent"] for v in plan_variants(dia, None, None)] == ["slow", "fast"]
    by_approach = plan_variants(dia, None, ["ECS", "cache lookups"])
    assert [(v["agent"], v["approach"]) for v in by_approach] == [
        ("slow", "ECS"),
        ("slow", "cache lookups"),
    ]
    with pytest.raises(ValueError, match="two variants"):
        plan_variants(dia, ["fast"], None)
    assert "approach: ECS" in variant_prompt("speed it up", "ECS")
    assert recommend([{"status": "failed", "tests_ok": None}]) is None
