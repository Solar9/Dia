from pathlib import Path

from dia.benchmark import agent_stats, suggestions
from dia.brains import SURFACE_STYLE, BrainContext, LLMBrain
from dia.config import load_config, parse_config, save_settings
from dia.store import TaskRecord, TaskStore


def fill(store: TaskStore) -> None:
    n = 0
    for agent, done in (("claude", 3), ("codex", 6)):
        for i in range(6):
            n += 1
            store.save(
                TaskRecord(
                    id=f"t{n}",
                    project="nova",
                    agent=agent,
                    mode="edit",
                    prompt="x",
                    status="done" if i < done else "failed",
                    tests_ok=i < done,
                    details={
                        "duration_s": 120,
                        "author": agent,
                        "reviews": [{"verdict": "approved" if i < done else "changes_requested"}],
                    },
                )
            )
    store.save(
        TaskRecord(
            id="m1",
            project="nova",
            agent="claude",
            mode="edit",
            prompt="step",
            status="failed",
            details={"mission": "m"},
        )
    )  # judged with its mission


def test_stats_and_proposal(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "t.db")
    fill(store)
    stats = {r["agent"]: r for r in agent_stats(store)}
    assert stats["claude"]["tasks"] == 6 and stats["claude"]["success"] == 0.5
    assert stats["codex"]["success"] == 1.0 and stats["codex"]["approved"] == 1.0
    assert stats["codex"]["minutes"] == 2.0

    config_file = tmp_path / "dia.toml"
    config_file.write_text(
        f'[dia]\ndata_dir = "{tmp_path}"\ndefault_agent = "claude"\n'
        '[agents.claude]\ntype = "claude-code"\n[agents.codex]\ntype = "codex"\n'
        f'[projects.nova]\npath = "{tmp_path}"\n'
    )
    config = load_config(config_file)
    [proposal] = suggestions(config, list(stats.values()))
    assert (proposal["project"], proposal["agent"], proposal["current"]) == (
        "nova",
        "codex",
        "claude",
    )
    new = save_settings(config, {"projects": {"nova": {"default_agent": "codex"}}})
    assert new.projects["nova"].default_agent == "codex"
    assert suggestions(new, list(stats.values())) == []  # nothing left to propose


def test_few_tasks_propose_nothing(tmp_path: Path) -> None:
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path), "default_agent": "a"},
            "agents": {"a": {}, "b": {}},
            "projects": {"p": {"path": "."}},
        }
    )
    rows = [
        {"project": "p", "agent": "a", "tasks": 2, "success": 0.0, "tests": None},
        {"project": "p", "agent": "b", "tasks": 2, "success": 1.0, "tests": None},
    ]
    assert suggestions(config, rows) == []


async def test_reply_style_follows_the_device() -> None:
    seen = []

    class Echo(LLMBrain):
        kind = "echo"

        async def complete(self, system: str, user: str) -> str:
            seen.append(system)
            return '{"action": "chat", "reply": "ok"}'

    brain = Echo("e", {}, None)
    await brain.interpret("hej", BrainContext({}, [], surface="phone"))
    await brain.interpret("hej", BrainContext({}, [], surface="voice"))
    await brain.interpret("hej", BrainContext({}, []))
    assert SURFACE_STYLE["phone"] in seen[0] and SURFACE_STYLE["voice"] in seen[1]
    assert not any(style in seen[2] for style in SURFACE_STYLE.values())


def test_rollbacks_and_regressions_count_against_an_agent(tmp_path: Path) -> None:
    """Fast-and-done is not good when the merges come back out."""
    store = TaskStore(tmp_path / "t.db")
    for i in range(6):
        # "hasty" finishes everything, but half its merges were rolled back or slower
        flaw = {0: {"reverted_by": "r"}, 1: {"regression": [{"metric": "fps"}]}}.get(i, {})
        rounds = [{"verdict": "changes_requested"}] * 2 + [{"verdict": "approved"}]
        store.save(
            TaskRecord(
                id=f"h{i}", project="nova", agent="hasty", mode="edit", prompt="x",
                status="merged", details={"author": "hasty", "reviews": rounds, **flaw},
            )
        )  # fmt: skip
        store.save(
            TaskRecord(
                id=f"c{i}", project="nova", agent="careful", mode="edit", prompt="x",
                status="merged" if i < 5 else "discarded",
                details={"author": "careful", "reviews": [{"verdict": "approved"}]},
            )
        )  # fmt: skip
    stats = {r["agent"]: r for r in agent_stats(store)}
    hasty, careful = stats["hasty"], stats["careful"]
    assert hasty["success"] == 1.0 and careful["success"] == 0.83
    assert (hasty["reverted"], hasty["regressions"], hasty["review_rounds"]) == (1, 1, 3.0)
    assert hasty["quality"] == 0.47 and careful["quality"] == 0.83
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path), "default_agent": "hasty"},
            "agents": {"hasty": {}, "careful": {}},
            "projects": {"nova": {"path": "."}},
        }
    )
    [proposal] = suggestions(config, list(stats.values()))
    assert proposal["agent"] == "careful" and "1 rolled back" in proposal["reason"]
