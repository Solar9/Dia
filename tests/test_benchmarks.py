import subprocess
from pathlib import Path

from dia.benchmarks import after_merge, bench, compare, parse_metrics
from dia.config import parse_config
from dia.orchestrator import Orchestrator


def test_parse_metrics() -> None:
    assert parse_metrics('noise\n{"frame_ms": 12.5, "ok": true, "name": "x"}\n') == {
        "frame_ms": 12.5
    }
    assert parse_metrics("frame_ms: 12.5 ms\nfps=144\nnot a metric\n") == {
        "frame_ms": 12.5,
        "fps": 144.0,
    }
    assert parse_metrics("nothing here") == {}


def test_compare_knows_which_way_is_better() -> None:
    changes = compare(
        {"frame_ms": 10.0, "fps": 100.0, "load_s": 2.0},
        {"frame_ms": 12.0, "fps": 90.0, "load_s": 2.05},
        better={"fps": "higher"},
    )
    by = {c["metric"]: c for c in changes}
    assert by["frame_ms"]["worse"] and by["frame_ms"]["change"] == 0.2
    assert by["fps"]["worse"]  # higher is better, and it went down
    assert not by["load_s"]["worse"]  # +2.5 %: within the 5 % tolerance


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    # The "benchmark" reads its frame time from a file the code changes.
    (repo / "frame_ms").write_text("10\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "bench"],
        cwd=repo,
        check=True,
    )
    agent = ["sh", "-c", "echo 13 > frame_ms; echo made it slower"]
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": agent}},
        "projects": {"demo": {"path": str(repo), "benchmark": 'echo "frame_ms: $(cat frame_ms)"'}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_a_merge_that_makes_it_slower_is_reported(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    first = await bench(dia, "demo")
    assert first["metrics"] == {"frame_ms": 10.0} and first["ref"] == "main"
    events = []

    async def listen(event):
        events.append(event)

    dia.listeners.append(listen)
    task = (await dia.run_task("demo", "refactor the renderer")).task
    sha = await dia.merge_task(task.id)
    await dia.drain()  # the benchmark runs in the background after the merge
    regression = [e for e in events if e.kind == "benchmark"]
    assert regression and "frame_ms +30%" in regression[0].message
    assert regression[0].data["sha"] == sha
    history = dia.store.benchmarks("demo", ref="main")
    assert [r["metrics"]["frame_ms"] for r in history] == [13.0, 10.0]
    assert dia.store.audit(action="benchmark.regression")
    assert dia.store.get(task.id).details["regression"][0]["metric"] == "frame_ms"
    assert not list((tmp_path / "d" / "worktrees" / "demo").glob("bench-*"))


async def test_no_regression_no_alert(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    await bench(dia, "demo")
    assert await after_merge(dia, "demo", "main") == []
