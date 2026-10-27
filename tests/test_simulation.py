import subprocess
from pathlib import Path

from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.simulation import describe


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    (repo / "player").mkdir()
    (repo / "player" / "dash.gd").write_text("func dash():\n\tpass\n")
    (repo / "ui").mkdir()
    (repo / "ui" / "hud.gd").write_text("func show():\n\tpass\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "game"],
        cwd=repo,
        check=True,
    )
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", "echo x >> player/dash.gd"]}},
        "projects": {
            "nova": {
                "path": str(repo),
                "architecture_forbid": [
                    {"from": "ui/**", "to": "player/**", "why": "UI reads state only"}
                ],
            }
        },
        "pipelines": {
            "two": {"steps": [{"agent": "a", "prompt": "a: {goal}"}, {"agent": "a", "prompt": "b"}]}
        },
        "retry": {"test_fixes": 1},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_a_plan_shows_files_cost_risks_and_approvals(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    # history: a dash change that was rolled back, and how long the agent takes
    task = (await dia.run_task("nova", "make the dash longer")).task
    await dia.merge_task(task.id)
    await dia.rollback_task(task.id)
    plan = await dia.create_plan("nova", "rework the dash and show it in the hud", pipeline="two")
    sim = plan.details["simulation"]
    files = [f["file"] for f in sim["files"]]
    assert "player/dash.gd" in files and "ui/hud.gd" in files
    assert sim["cost"]["calls"] == 2 and sim["cost"]["calls_worst"] == 4
    assert sim["cost"]["from_tasks"] >= 1 and sim["cost"]["minutes"] is not None
    risks = " ".join(sim["risks"])
    assert "player/dash.gd: 1 earlier change(s) rolled back" in risks
    assert "architecture rule in play: UI reads state only" in risks
    assert "no tests among the likely files" in risks
    text = describe(sim)
    assert text.startswith("Likely files:") and "Waits for you: you accept the plan" in text
    assert dia.store.get(plan.id).status == "planned"  # nothing ran
