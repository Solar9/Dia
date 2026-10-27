"""Plain chat with a model, without Dia's assistant around it.

A chat session can talk to Dia (the assistant: it runs tasks, skills,
plans) or straight to a model, like the ChatGPT or Claude apps: no
intent parsing, no tools, just the conversation. That is cheaper and
faster for everyday questions. The models on offer:

- **your subscriptions, through the CLIs you already use**: every
  configured Claude Code agent ("Claude") and Codex agent ("ChatGPT"), and
  Cursor. Answers count against the subscription, not an API bill; the
  agent runs read-only, without tools, in an empty folder.
- **the APIs, with a key**: Anthropic (``ANTHROPIC_API_KEY``; the official
  SDK, ``pip install 'dia[chat]'``) and OpenAI (``OPENAI_API_KEY``), paid
  per token. Their model lists come from the APIs themselves.
- **Ollama**, local and free, when it runs.

    [chat]
    default = "dia"                    # or e.g. "agent:claude"
    models = { claude = ["sonnet", "opus", "haiku"], codex = ["gpt-5"] }   # per agent

The list of models for a subscription agent is yours to set (the CLIs take
whatever name their service knows); "default" uses the CLI's own default.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.agents import AgentRequest, Mode

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

DIA = "dia"
SYSTEM = (
    "You are a helpful assistant in a chat. Answer directly and concisely, in the "
    "language of the user's last message. Use Markdown where it helps."
)
AGENT_MODELS = {
    "claude-code": ["sonnet", "opus", "haiku"],  # Claude Code's own aliases
    "codex": ["gpt-5", "o4-mini"],
    "cursor": [],
}
AGENT_LABELS = {"claude-code": "Claude", "codex": "ChatGPT", "cursor": "Cursor"}
ANTHROPIC_MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
MAX_HISTORY = 30  # messages sent back as context
_model_cache: dict[str, tuple[float, list[str]]] = {}


def _cached(key: str, load: Any, ttl: float = 3600) -> list[str]:
    hit = _model_cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    try:
        models = load()
    except Exception:
        models = []
    _model_cache[key] = (time.monotonic(), models)
    return models


def _http_json(url: str, headers: dict[str, str] | None = None, body: Any = None,
               timeout: float = 5) -> Any:  # fmt: skip
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                          **(headers or {})})  # fmt: skip
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _anthropic_available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _anthropic_models() -> list[str]:
    import anthropic

    client = anthropic.Anthropic(max_retries=0, timeout=5)
    return [m.id for m in client.models.list(limit=50)]


def _openai_models() -> list[str]:
    key = os.environ["OPENAI_API_KEY"]
    data = _http_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
    ids = [m["id"] for m in data.get("data", [])]
    chat = [i for i in ids if i.startswith(("gpt-", "o")) and "audio" not in i
            and "realtime" not in i and "transcribe" not in i and "tts" not in i]  # fmt: skip
    return sorted(chat, reverse=True)


def _ollama_url(dia: Orchestrator) -> str:
    return str(dia.config.section("chat").get("ollama_url", "http://localhost:11434")).rstrip("/")


def _ollama_models(url: str) -> list[str]:
    return [m["name"] for m in _http_json(f"{url}/api/tags", timeout=2).get("models", [])]


def providers(dia: Orchestrator) -> list[dict[str, Any]]:
    """Who the chat can talk to, with their models (the first is the default)."""
    options = dia.config.section("chat")
    configured = options.get("models", {})
    sub = "subskrypcja" if dia.config.language == "pl" else "subscription"
    found: list[dict[str, Any]] = [{"id": DIA, "label": "Dia", "kind": "assistant", "models": []}]
    for name, agent in dia.config.agents.items():
        kind = agent.get("type", "")
        if kind not in AGENT_MODELS:
            continue
        models = list(configured.get(name) or agent.get("chat_models") or AGENT_MODELS[kind])
        found.append({
            "id": f"agent:{name}",
            "label": f"{AGENT_LABELS[kind]} ({name}, {sub})",
            "kind": "subscription",
            "models": ["default", *[m for m in models if m != "default"]],
        })  # fmt: skip
    if _anthropic_available():
        models = _cached("anthropic", _anthropic_models) or ANTHROPIC_MODELS
        preferred = [m for m in ANTHROPIC_MODELS if m in models]
        found.append({"id": "anthropic", "label": "Claude API", "kind": "api",
                      "models": preferred + [m for m in models if m not in preferred]})  # fmt: skip
    if os.environ.get("OPENAI_API_KEY"):
        models = _cached("openai", _openai_models) or list(configured.get("openai", []))
        found.append({"id": "openai", "label": "OpenAI API", "kind": "api", "models": models})
    url = _ollama_url(dia)
    if models := _cached(f"ollama:{url}", lambda: _ollama_models(url), ttl=60):
        local = "lokalnie" if dia.config.language == "pl" else "local"
        label = f"Ollama ({local})"
        found.append({"id": "ollama", "label": label, "kind": "local", "models": models})
    return found


def _transcript(history: list[dict[str, Any]], text: str) -> str:
    lines = []
    for m in history[-MAX_HISTORY:]:
        who = "User" if m["from"] == "me" else "Assistant"
        lines.append(f"{who}: {m['text']}")
    if not lines:
        return text
    return "The conversation so far:\n\n" + "\n\n".join(lines) + f"\n\nUser: {text}\n\nAssistant:"


def _messages(history: list[dict[str, Any]], text: str) -> list[dict[str, str]]:
    turns = [
        {"role": "user" if m["from"] == "me" else "assistant", "content": m["text"]}
        for m in history[-MAX_HISTORY:]
        if m.get("text")
    ]
    while turns and turns[0]["role"] != "user":  # a conversation starts with the user
        turns.pop(0)
    return [*turns, {"role": "user", "content": text}]


async def _agent(dia: Orchestrator, name: str, model: str | None, history: list, text: str) -> str:
    agent = dia.config.agent(name)
    with tempfile.TemporaryDirectory(prefix="dia-chat-") as empty:
        used, result = await dia.call_agent(
            agent,
            AgentRequest(
                prompt=_transcript(history, text),
                cwd=Path(empty),
                mode=Mode.READ_ONLY,
                system=SYSTEM,
                model=model,
                tools=False,
                timeout=float(dia.config.section("chat").get("timeout", 300)),
            ),
            purpose="chat",
        )
    if not result.success:
        raise RuntimeError(f"{used.name}: {result.error or 'no answer'}")
    return result.summary.strip()


async def _anthropic(model: str, history: list, text: str) -> str:
    import anthropic

    client = anthropic.AsyncAnthropic()
    try:
        response = await client.beta.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM,
            messages=_messages(history, text),
            # A policy decline on the requested model is retried on its server-side
            # default fallback; on models without one this changes nothing.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("the Anthropic API key was rejected") from None
    except anthropic.RateLimitError:
        raise RuntimeError("the Anthropic API rate limit was hit; try again shortly") from None
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"Anthropic API error {exc.status_code}: {exc.message}") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("cannot reach the Anthropic API") from None
    finally:
        await client.close()
    if response.stop_reason == "refusal":
        return "(The model declined to answer this.)"
    return "".join(block.text for block in response.content if block.type == "text").strip()


async def _openai_compatible(url: str, key: str | None, model: str, history: list,
                             text: str) -> str:  # fmt: skip
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM},
                                         *_messages(history, text)]}  # fmt: skip
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        data = await asyncio.to_thread(_http_json, f"{url}/chat/completions", headers, body, 300)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode(errors="replace")
        raise RuntimeError(f"{url}: HTTP {exc.code} {detail}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"cannot reach {url}: {exc}") from None
    return str(data["choices"][0]["message"]["content"]).strip()


async def reply(
    dia: Orchestrator, provider: str, model: str | None, history: list[dict[str, Any]], text: str
) -> str:
    """The model's answer to ``text`` after ``history`` (the session's transcript)."""
    model = None if model in (None, "", "default") else model
    if provider.startswith("agent:"):
        return await _agent(dia, provider.split(":", 1)[1], model, history, text)
    if provider == "anthropic":
        return await _anthropic(model or ANTHROPIC_MODELS[0], history, text)
    if provider == "openai":
        if not model:
            raise ValueError("choose an OpenAI model")
        key = os.environ.get("OPENAI_API_KEY")
        return await _openai_compatible("https://api.openai.com/v1", key, model, history, text)
    if provider == "ollama":
        if not model:
            raise ValueError("choose an Ollama model")
        return await _openai_compatible(f"{_ollama_url(dia)}/v1", None, model, history, text)
    raise ValueError(f"unknown chat provider {provider!r}")
