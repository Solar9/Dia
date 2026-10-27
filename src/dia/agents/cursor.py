"""Cursor Agent via its headless CLI (``agent -p`` / ``cursor-agent -p``)."""

from __future__ import annotations

import json
from pathlib import Path

from dia.agents.base import AgentRequest, AgentResult, CliAgent, Mode


class CursorAgent(CliAgent):
    kind = "cursor"
    models = ("auto", "gpt-5", "sonnet-4", "opus-4.1")
    default_command = "cursor-agent"
    # Installers ship both names (``agent`` is the current one); the
    # unambiguous name wins when both exist. ``command`` overrides both.
    command_candidates = ("cursor-agent", "agent")

    def build_argv(self, request: AgentRequest, scratch: Path) -> list[str]:
        argv = [self.command, "-p", "--output-format", "json"]
        if model := request.model or self.options.get("model"):
            argv += ["--model", model]
        if request.session_id:
            argv += ["--resume", request.session_id]
        if self.options.get("trust", True):
            # Headless Cursor refuses untrusted directories. Dia runs it in a
            # worktree it created itself, so trusting that directory is safe.
            argv.append("--trust")
        if request.mode is Mode.EDIT:
            # Without --force the headless agent only proposes file changes.
            argv.append("--force")
        return argv + self.extra_args + [request.combined_prompt]

    def parse(
        self, request: AgentRequest, scratch: Path, exit_code: int, stdout: str, stderr: str
    ) -> AgentResult:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            data = {"result": stdout.strip()}
        is_error = bool(data.get("is_error")) or exit_code != 0
        return AgentResult(
            agent=self.name,
            success=not is_error,
            summary=str(data.get("result", "")).strip(),
            exit_code=exit_code,
            session_id=data.get("session_id"),
            error=(stderr.strip()[-2000:] or "cursor agent failed") if is_error else None,
        )
