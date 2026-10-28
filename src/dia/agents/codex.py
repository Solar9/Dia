"""OpenAI Codex via ``codex exec`` (ChatGPT plan or API key)."""

from __future__ import annotations

import re
from pathlib import Path

from dia.agents.base import AgentRequest, AgentResult, CliAgent, Mode

_LAST_MESSAGE = "last-message.txt"
# `codex exec` prints its conversation's id in the header it writes first.
_SESSION = re.compile(r"^session id:\s*([0-9A-Za-z-]{8,})\s*$", re.MULTILINE | re.IGNORECASE)


class CodexAgent(CliAgent):
    kind = "codex"
    models = ("gpt-5-codex", "gpt-5", "o4-mini")
    default_command = "codex"

    def build_argv(self, request: AgentRequest, scratch: Path) -> list[str]:
        # Codex streams progress on stdout; the final answer goes to a file.
        sandbox = "read-only" if request.mode is Mode.READ_ONLY else "workspace-write"
        argv = [
            self.command,
            "exec",
            "--skip-git-repo-check",  # completions run in an empty, non-git directory
            "--sandbox",
            self.options.get("sandbox", sandbox),
            "--output-last-message",
            str(scratch / _LAST_MESSAGE),
        ]
        if model := request.model or self.options.get("model"):
            argv += ["--model", model]
        if request.web:
            argv += self.options.get("web_args", ["-c", "tools.web_search=true"])
        argv += self.extra_args
        if request.session_id:  # continue that conversation (`codex exec resume <id>`)
            argv += ["resume", request.session_id]
        return argv + [request.combined_prompt]

    def parse(
        self, request: AgentRequest, scratch: Path, exit_code: int, stdout: str, stderr: str
    ) -> AgentResult:
        message_file = scratch / _LAST_MESSAGE
        summary = message_file.read_text(errors="replace").strip() if message_file.exists() else ""
        ok = exit_code == 0
        found = _SESSION.search(f"{stderr}\n{stdout}")
        return AgentResult(
            agent=self.name,
            success=ok,
            summary=summary or stdout.strip()[-4000:],
            exit_code=exit_code,
            error=None if ok else (stderr.strip()[-2000:] or "codex exited with an error"),
            session_id=found.group(1) if found else request.session_id,
        )
