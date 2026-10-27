from pathlib import Path

from dia.agents import AgentRequest, Mode
from dia.agents.claude_code import ClaudeCodeAgent
from dia.agents.codex import CodexAgent
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.research import research

REPORT = "# Co-op w roguelike\\n## Summary\\nNajczęściej host-authoritative.\\n## Sources\\n1. https://example.com"


def make(tmp_path: Path, repo: Path, answer: str = REPORT) -> Orchestrator:
    agent = ["sh", "-c", f'printf "{answer}"']
    config = parse_config(
        {
            "dia": {"data_dir": str(tmp_path / "d"), "language": "pl", "default_agent": "r"},
            "agents": {"r": {"type": "command", "argv": agent}},
            "projects": {"nova": {"path": str(repo)}},
            "memory": {"type": "markdown", "vault": str(tmp_path / "vault")},
        }
    )
    (tmp_path / "vault").mkdir()
    return Orchestrator(config)


async def test_a_report_becomes_a_task_and_a_note(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    started = []

    async def on_start(task):
        started.append(task.id)

    task = await research(dia, "jak inne gry robią co-op?", "nova", on_start=on_start)
    assert task.status == "done" and task.mode == "research"
    assert started == [task.id]
    assert task.summary.startswith("# Co-op w roguelike")
    note = tmp_path / "vault" / "Dia" / task.details["note"]
    assert task.details["note"].startswith("Research/") and "host-authoritative" in note.read_text()
    assert not list((tmp_path / "d" / "worktrees" / "nova").glob("research-*"))  # cleaned up


async def test_an_empty_answer_fails(tmp_path, repo) -> None:
    task = await research(make(tmp_path, repo, answer=""), "anything")
    assert task.status == "failed" and task.project == "-"


def test_agents_get_the_web_only_for_research(tmp_path) -> None:
    request = AgentRequest(prompt="x", cwd=tmp_path, mode=Mode.READ_ONLY, web=True)
    claude = ClaudeCodeAgent("claude", {})
    argv = claude.build_argv(request, tmp_path)
    assert argv[argv.index("--allowedTools") + 1 :][:2] == ["WebSearch", "WebFetch"]
    plain = AgentRequest(prompt="x", cwd=tmp_path, mode=Mode.READ_ONLY)
    assert "--allowedTools" not in claude.build_argv(plain, tmp_path)
    codex = CodexAgent("codex", {})
    assert "tools.web_search=true" in codex.build_argv(request, tmp_path)
    assert "tools.web_search=true" not in codex.build_argv(plain, tmp_path)


async def test_the_same_topic_twice_keeps_both_notes(tmp_path, repo) -> None:
    dia = make(tmp_path, repo)
    first = await research(dia, "co-op w roguelike")
    second = await research(dia, "co-op w roguelike")
    assert first.details["note"] != second.details["note"]
    assert second.details["note"].endswith(" (2).md")
    assert (tmp_path / "vault" / "Dia" / first.details["note"]).exists()
