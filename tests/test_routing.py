from pathlib import Path

from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.store import TaskRecord


def make(tmp_path: Path, repo: Path, routing: dict) -> Orchestrator:
    agents = {n: {"type": "command", "argv": ["sh", "-c", f"echo {n}"]} for n in ("a", "b", "c")}
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": agents,
        "projects": {"nova": {"path": str(repo)}, "dia": {"path": str(repo)}},
        "routing": routing,
    }
    return Orchestrator(parse_config(raw), use_memory=False)


def history(dia: Orchestrator, agent: str, done: int, total: int) -> None:
    for i in range(total):
        dia.store.save(
            TaskRecord(
                id=f"{agent}{i}",
                project="nova",
                agent=agent,
                mode="edit",
                prompt="x",
                status="done" if i < done else "failed",
            )
        )


async def test_rules_then_the_record_then_the_default(tmp_path, repo) -> None:
    rules = [
        {"match": "testy|gut", "agent": "b"},
        {"match": "menu", "agent": "c", "project": "dia"},
    ]
    dia = make(tmp_path, repo, {"rules": rules, "auto": True, "min_tasks": 3})
    task = (await dia.run_task("nova", "dopisz testy GUT", mode="read-only")).task
    assert (task.agent, task.details["routed"]) == ("b", "rule 'testy|gut'")
    # a rule for another project does not apply; no record yet: the default
    task = (await dia.run_task("nova", "popraw menu", mode="read-only")).task
    assert task.agent == "a" and "routed" not in task.details

    history(dia, "a", 1, 4)
    history(dia, "c", 4, 4)
    task = (await dia.run_task("nova", "popraw menu", mode="read-only")).task
    assert task.agent == "c" and task.details["routed"].startswith("best record on nova: 100%")
    # naming an agent always wins
    assert (await dia.run_task("nova", "testy", "a", mode="read-only")).task.agent == "a"
