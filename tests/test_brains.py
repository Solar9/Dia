import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from dia.agents import AgentRequest, Mode
from dia.agents.claude_code import ClaudeCodeAgent
from dia.agents.codex import CodexAgent
from dia.assistant import Assistant
from dia.brains import BrainContext, parse_intent
from dia.config import ConfigError, parse_config
from dia.orchestrator import Orchestrator

CTX = BrainContext(projects={"nova": "/p/nova", "starfall": "/p/uv"}, agents=["claude", "codex"])


def test_parse_intent_validates_against_config() -> None:
    raw = 'Sure!\n```json\n{"action": "run", "project": "Nova", "agent": "CODEX",\n'
    raw += '"prompt": "Dodaj strzelbę", "reply": "Zlecam."}\n```'
    intent = parse_intent(raw, "dodaj strzelbę", CTX)
    assert (intent.action, intent.project, intent.agent) == ("run", "nova", "codex")
    assert intent.prompt == "Dodaj strzelbę" and intent.reply == "Zlecam."

    invented = parse_intent('{"action": "ask", "project": "zelda"}', "x", CTX)
    assert invented.action == "chat" and "nova" in invented.reply  # asks which project

    with pytest.raises(ValueError):
        parse_intent("no json here", "x", CTX)
    with pytest.raises(ValueError):
        parse_intent('{"action": "merge"}', "x", CTX)  # brains cannot merge


def test_claude_completion_runs_without_tools(tmp_path: Path) -> None:
    agent = ClaudeCodeAgent("c", {"model": "sonnet"})
    req = AgentRequest(
        prompt="hi", cwd=tmp_path, mode=Mode.READ_ONLY, system="sys", model="haiku", tools=False
    )
    argv = agent.build_argv(req, tmp_path)
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == "haiku"
    assert argv[argv.index("--system-prompt") + 1] == "sys"
    assert "--permission-mode" not in argv


def test_codex_folds_system_prompt_in(tmp_path: Path) -> None:
    req = AgentRequest(prompt="hi", cwd=tmp_path, system="sys")
    argv = CodexAgent("x").build_argv(req, tmp_path)
    assert argv[-1].startswith("sys") and argv[-1].endswith("hi")
    assert "--skip-git-repo-check" in argv


def orchestrator(tmp_path: Path, repo: Path, raw: dict) -> Orchestrator:
    raw = {
        "dia": {
            "data_dir": str(tmp_path / "data"),
            "default_agent": "worker",
            **raw.pop("dia", {}),
        },
        "agents": {
            "worker": {"type": "command", "argv": ["sh", "-c", 'echo "did: $0"', "{prompt}"]}
        },
        "projects": {"nova": {"path": str(repo)}},
        **raw,
    }
    return Orchestrator(parse_config(raw))


async def test_agent_brain_routes_and_assistant_executes(tmp_path: Path, repo: Path) -> None:
    answer = json.dumps(
        {"action": "ask", "project": "nova", "prompt": "Jak działa zapis?", "reply": "Sprawdzam."}
    )
    orch = orchestrator(
        tmp_path,
        repo,
        {
            "dia": {"brain": ["rules", "router"]},
            "agents": {
                "worker": {"type": "command", "argv": ["sh", "-c", 'echo "did: $0"', "{prompt}"]},
                "fake-llm": {"type": "command", "argv": ["echo", answer]},
            },
            "brains": {"router": {"type": "agent", "agent": "fake-llm"}},
        },
    )
    assistant = Assistant(orch)
    assert [b.name for b in assistant.brains] == ["rules", "router"]

    status = await assistant.interpret("Dia, status")
    assert status.action == "status" and status.brain == "rules"  # no model needed

    intent = await assistant.interpret("jak działa zapis gry w nova?")
    assert (intent.action, intent.project, intent.brain) == ("ask", "nova", "router")
    response = await assistant.execute(intent)
    assert response.report.task.mode == "read-only"
    assert response.text.startswith("did: ") and "Jak działa zapis?" in response.text


async def test_failing_brain_falls_back_to_next(tmp_path: Path, repo: Path) -> None:
    orch = orchestrator(
        tmp_path,
        repo,
        {
            "dia": {"brain": ["local", "backup"]},
            "agents": {
                "worker": {"type": "command", "argv": ["true"]},
                "broken": {"type": "command", "argv": ["sh", "-c", "exit 1"]},
                "ok": {"type": "command", "argv": ["echo", '{"action": "chat", "reply": "hej"}']},
            },
            "brains": {
                "local": {"type": "agent", "agent": "broken"},
                "backup": {"type": "agent", "agent": "ok"},
            },
        },
    )
    intent = await Assistant(orch).interpret("cześć")
    assert intent.brain == "backup" and intent.reply == "hej"


def test_default_chain_and_errors(tmp_path: Path) -> None:
    config = parse_config({"dia": {"default_agent": "claude"}, "agents": {"claude": {}}})
    assert [b.kind for b in config.brain_chain()] == ["rules", "agent"]
    assert parse_config({}).brain_chain()[0].kind == "rules"
    with pytest.raises(ConfigError):
        parse_config({"dia": {"brain": "nope"}}).brain_chain()


async def test_ollama_compatible_api(tmp_path: Path, repo: Path) -> None:
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # /models, used by check()
            self._send({"data": []})

        def do_POST(self):
            seen.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            seen["auth"] = self.headers.get("Authorization")
            content = '{"action": "tasks"}'
            self._send({"choices": [{"message": {"content": content}}]})

        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/v1"
        orch = orchestrator(
            tmp_path,
            repo,
            {
                "dia": {"brain": "local"},
                "brains": {
                    "local": {
                        "type": "ollama",
                        "base_url": url,
                        "model": "qwen2.5:3b",
                        "api_key_env": "DIA_TEST_KEY",
                    },
                },
            },
        )
        brain = orch.config.brain_chain()[0]
        assert brain.check() is None
        import os

        os.environ["DIA_TEST_KEY"] = "k"
        try:
            intent = await Assistant(orch).interpret("pokaż zadania z wczoraj")
        finally:
            del os.environ["DIA_TEST_KEY"]
        assert intent.action == "tasks" and intent.brain == "local"
        assert seen["model"] == "qwen2.5:3b" and seen["temperature"] == 0
        assert seen["messages"][0]["role"] == "system"
        assert "nova" in seen["messages"][1]["content"]
        assert seen["auth"] == "Bearer k"
    finally:
        server.shutdown()


def test_unreachable_local_model_is_reported(tmp_path: Path) -> None:
    config = parse_config(
        {"brains": {"local": {"type": "ollama", "base_url": "http://127.0.0.1:9/v1", "model": "m"}}}
    )
    assert "cannot reach" in config.brain_chain(only="local")[0].check()


@pytest.mark.parametrize(
    "heard",
    ["Dia, status", "Dias status.", "Dziastatus", "DIA STATUS", "Hej, Jarvis. Status.", "status"],
)
async def test_rules_tolerate_how_speech_recognition_writes_the_address(heard: str) -> None:
    from dia.brains.rules import RulesBrain

    intent = await RulesBrain("rules", {}, parse_config({})).interpret(heard, CTX)
    assert intent and intent.action == "status"


async def test_rules_do_not_eat_words_starting_with_dia() -> None:
    from dia.brains.rules import strip_address

    assert strip_address("diagram status") == "diagram status"


async def test_status_is_in_the_configured_language(tmp_path: Path, repo: Path) -> None:
    orch = orchestrator(tmp_path, repo, {"dia": {"language": "pl", "brain": ["rules"]}})
    response = await Assistant(orch).handle("Dziastatus")
    assert response.text == "Gotowi agenci: worker.\nŻadne zadanie teraz nie trwa."


@pytest.mark.parametrize(
    "text",
    [
        "scal to do main",
        "merge this branch",
        "wypchnij na github",
        "push the branch to origin",
        "odrzuć to zadanie",
        "discard the task",
    ],
)
def test_merge_push_never_becomes_run(text: str) -> None:
    from dia.brains import Intent, guard_irreversible

    blocked = guard_irreversible(Intent("run", project="nova", prompt=text), text, "pl")
    assert blocked.action == "chat" and "Merge" in blocked.reply
    assert guard_irreversible(Intent("ask", prompt=text), text).action == "chat"


def test_merge_guard_leaves_ordinary_coding_alone() -> None:
    from dia.brains import Intent, guard_irreversible

    for text in ("napraw zapis", "add push notifications", "implement merge sort"):
        assert guard_irreversible(Intent("run", prompt=text), text).action == "run"
