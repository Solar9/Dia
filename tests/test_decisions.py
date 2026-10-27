from pathlib import Path

from dia.config import parse_config
from dia.decisions import describe, terms, why
from dia.orchestrator import Orchestrator


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["sh", "-c", "echo x >> inv.txt; echo ok"]}},
        "projects": {"nova": {"path": str(repo)}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


def test_terms_drop_the_question_words() -> None:
    assert terms("Dlaczego trzy miesiące temu zrezygnowaliśmy z ECS w ekwipunku?") == [
        "ecs",
        "ekwipu",
    ]
    assert terms("why did we drop SQLite saves?") == ["sqli", "saves"]


async def test_decisions_are_recorded_and_found(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    ecs = (await dia.run_task("nova", "Rewrite the inventory as ECS")).task
    await dia.discard_task(ecs.id, "ECS made the save format incompatible")
    kept = (await dia.run_task("nova", "Cache inventory lookups")).task
    sha = await dia.merge_task(kept.id, "simpler, and fast enough")
    log = dia.store.decisions("nova")
    assert [(d["kind"], d["outcome"]) for d in log] == [
        ("merge", "merged"),
        ("discard", "discarded"),
    ]
    by_task = {d["task_id"]: d for d in log}
    assert by_task[ecs.id]["reason"] == "ECS made the save format incompatible"
    merged = by_task[kept.id]["detail"]
    assert merged["sha"] == sha and merged["files"] == ["inv.txt"]
    assert by_task[kept.id]["detail"]["agent"] == "a"

    rollback = await dia.rollback_task(kept.id, "the cache broke loading old saves")
    assert rollback.status == "done"
    found = await why(dia, "Dlaczego zrezygnowaliśmy z ECS w ekwipunku?")
    assert [d["task_id"] for d in found["decisions"]][0] == ecs.id
    text = describe(found)
    assert "discard: discarded" in text and "why: ECS made the save format" in text

    found = await why(dia, "why did we drop the inventory cache?", "nova")
    cache = [d for d in found["decisions"] if d["task_id"] == kept.id]
    assert {d["kind"] for d in cache} == {"merge", "rollback"}
    assert any("rolled back later" in c for d in cache for c in d["consequences"])
    assert any("Cache inventory lookups" in c["line"] for c in found["commits"])
    assert "Name the thing" in describe(await why(dia, "dlaczego?"))


async def test_a_rejected_plan_is_a_decision(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    dia.config.pipelines["two"] = {"steps": [{"agent": "a", "prompt": "a"}]}
    plan = await dia.create_plan("nova", "Move saves to SQLite", pipeline="two")
    await dia.discard_task(plan.id, "JSON is enough for now")
    assert dia.store.get(plan.id).status == "discarded"
    [decision] = dia.store.decisions(task_id=plan.id)
    assert (decision["kind"], decision["outcome"]) == ("plan", "rejected")
    assert (await why(dia, "czemu nie SQLite?"))["decisions"][0][
        "reason"
    ] == "JSON is enough for now"
