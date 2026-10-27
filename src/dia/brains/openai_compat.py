"""A brain behind any OpenAI-compatible chat API: local models or cloud services.

Local, private and free to run: Ollama, LM Studio, llama.cpp's server, vLLM,
LocalAI... all expose ``/v1/chat/completions``::

    [brains.local]
    type = "ollama"              # = "openai" with base_url http://localhost:11434/v1
    model = "qwen2.5:3b"

    [brains.lmstudio]
    type = "openai"
    base_url = "http://localhost:1234/v1"
    model = "whatever-is-loaded"

    [brains.cloud]
    type = "openai"
    base_url = "https://api.example.com/v1"
    model = "..."
    api_key_env = "EXAMPLE_API_KEY"

Uses only the standard library.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from dia.brains import LLMBrain


class OpenAICompatBrain(LLMBrain):
    kind = "openai"
    default_base_url: str | None = None
    json_by_default = False

    @property
    def base_url(self) -> str:
        url = self.options.get("base_url") or self.default_base_url
        if not url:
            raise ValueError(f"brain '{self.name}' needs 'base_url'")
        return url.rstrip("/")

    def describe(self) -> str:
        url = self.options.get("base_url") or self.default_base_url
        return f"{self.kind} {self.options.get('model', '?')} @ {url}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if env := self.options.get("api_key_env"):
            if key := os.environ.get(env):
                headers["Authorization"] = f"Bearer {key}"
        return headers

    def _request(self, path: str, body: dict[str, Any] | None, timeout: float) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, headers=self._headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def check(self) -> str | None:
        if not self.options.get("model"):
            return f"brain '{self.name}' needs 'model'"
        try:
            self._request("/models", None, timeout=3)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return f"cannot reach {self.base_url}: {getattr(exc, 'reason', exc)}"
        return None

    async def complete(self, system: str, user: str) -> str:
        body = {
            "model": self.options["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": float(self.options.get("temperature", 0)),
            "stream": False,
        }
        if self.options.get("json", self.json_by_default):
            # Constrains the model to valid JSON: small local models need the help.
            body["response_format"] = {"type": "json_object"}
        timeout = float(self.options.get("timeout", 120))
        data = await asyncio.to_thread(self._request, "/chat/completions", body, timeout)
        return data["choices"][0]["message"]["content"]


class OllamaBrain(OpenAICompatBrain):
    kind = "ollama"
    default_base_url = "http://localhost:11434/v1"
    json_by_default = True
