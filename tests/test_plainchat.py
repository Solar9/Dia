from pathlib import Path

import pytest

from dia import plainchat
from dia.config import parse_config
from dia.orchestrator import Orchestrator

# A "Claude Code" that echoes what it got: the system prompt, the model, the prompt.
ECHO = 'printf "model=%s | %s" "$DIA_MODEL" "$0"'


def make(tmp_path: Path, monkeypatch) -> Orchestrator:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "claude"},
        "agents": {
            "claude": {"type": "claude-code", "command": "true"},
            "gpt": {"type": "codex", "chat_models": ["gpt-x"]},
            "echo": {"type": "command", "argv": ["sh", "-c", ECHO, "{prompt}"]},
        },
        "chat": {"ollama_url": "http://127.0.0.1:9", "models": {"claude": ["sonnet", "opus"]}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


def test_providers_offer_the_subscriptions(tmp_path, monkeypatch) -> None:
    dia = make(tmp_path, monkeypatch)
    found = {p["id"]: p for p in plainchat.providers(dia)}
    assert list(found) == ["dia", "agent:claude", "agent:gpt"]  # no keys, no ollama
    assert found["agent:claude"]["label"] == "Claude (claude, subscription)"
    assert found["agent:claude"]["models"] == ["default", "sonnet", "opus"]
    assert found["agent:gpt"]["models"] == ["default", "gpt-x"]
    assert found["agent:gpt"]["label"].startswith("ChatGPT")


def test_history_goes_along() -> None:
    history = [
        {"from": "dia", "text": "hello"},  # an assistant message first is dropped for the API
        {"from": "me", "text": "2+2?"},
        {"from": "dia", "text": "4"},
    ]
    assert plainchat._messages(history, "and 3+3?") == [
        {"role": "user", "content": "2+2?"},
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "and 3+3?"},
    ]
    text = plainchat._transcript(history, "and 3+3?")
    assert "User: 2+2?" in text and text.endswith("User: and 3+3?\n\nAssistant:")
    assert plainchat._transcript([], "hi") == "hi"


async def test_a_subscription_agent_answers_without_tools(tmp_path, monkeypatch) -> None:
    dia = make(tmp_path, monkeypatch)
    dia.config.agents["echo"]["type"] = "command"
    answer = await plainchat.reply(dia, "agent:echo", "default", [{"from": "me", "text": "hi"},
                                   {"from": "dia", "text": "hello"}], "what's up?")  # fmt: skip
    assert "User: hi" in answer and "User: what's up?" in answer
    assert dia.store.usage(1)["agents"][0]["agent"] == "echo"  # counted like any call
    with pytest.raises(ValueError):
        await plainchat.reply(dia, "nope", None, [], "x")
