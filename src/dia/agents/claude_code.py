"""Claude Code via ``claude -p`` (works with a Claude subscription or an API key)."""

from __future__ import annotations

import json
from pathlib import Path

from dia.agents.base import AgentRequest, AgentResult, CliAgent, Mode


class ClaudeCodeAgent(CliAgent):
    kind = "claude-code"
    models = ("sonnet", "opus", "haiku", "fable")
    default_command = "claude"

    def build_argv(self, request: AgentRequest, scratch: Path) -> list[str]:
        argv = [self.command, "-p", request.prompt, "--output-format", "json"]
        if model := request.model or self.options.get("model"):
            argv += ["--model", model]
        if request.session_id:
            argv += ["--resume", request.session_id]
        if request.system:
            argv += ["--system-prompt", request.system]
        if not request.tools:
            return argv + ["--tools", ""]
        # Plan mode cannot modify files; acceptEdits lets it edit the isolated worktree.
        default_permission = "plan" if request.mode is Mode.READ_ONLY else "acceptEdits"
        argv += ["--permission-mode", self.options.get("permission_mode", default_permission)]
        allowed = list(self.options.get("allowed_tools", []))
        if request.web:
            allowed += ["WebSearch", "WebFetch"]
        if allowed:
            argv += ["--allowedTools", *allowed]
        return argv + self.extra_args

    def parse(
        self, request: AgentRequest, scratch: Path, exit_code: int, stdout: str, stderr: str
    ) -> AgentResult:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return AgentResult(
                agent=self.name,
                success=False,
                summary=stdout.strip(),
                exit_code=exit_code,
                error=stderr.strip() or "unparseable output",
            )
        is_error = bool(data.get("is_error")) or exit_code != 0
        return AgentResult(
            agent=self.name,
            success=not is_error,
            summary=str(data.get("result", "")).strip(),
            exit_code=exit_code,
            session_id=data.get("session_id"),
            error=(stderr.strip() or data.get("subtype")) if is_error else None,
            details={k: data[k] for k in ("total_cost_usd", "usage", "num_turns") if k in data},
        )
