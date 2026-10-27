"""A generic agent for any CLI, configured entirely from the config file.

This is the escape hatch that lets Dia drive tools it has no dedicated
adapter for (aider, a local-model wrapper, a custom script, ...)::

    [agents.aider]
    type = "command"
    argv = ["aider", "--yes", "--message", "{prompt}"]
    read_only_argv = ["aider", "--dry-run", "--message", "{prompt}"]

Placeholders: ``{prompt}``, ``{cwd}``, ``{mode}``. Stdout becomes the summary.
"""

from __future__ import annotations

import re
from pathlib import Path

from dia.agents.base import AgentRequest, AgentResult, CliAgent, Mode, find_executable


class CommandAgent(CliAgent):
    kind = "command"

    @property
    def command(self) -> str:
        return self._template(Mode.EDIT)[0]

    def _template(self, mode: Mode) -> list[str]:
        if mode is Mode.READ_ONLY and "read_only_argv" in self.options:
            return list(self.options["read_only_argv"])
        try:
            return list(self.options["argv"])
        except KeyError:
            raise ValueError(f"agent '{self.name}': type 'command' requires 'argv'") from None

    def build_argv(self, request: AgentRequest, scratch: Path) -> list[str]:
        values = {
            "prompt": request.combined_prompt,
            "cwd": str(request.cwd),
            "mode": request.mode.value,
        }
        # Only the known placeholders are substituted; other braces stay literal.
        placeholder = re.compile(r"\{(prompt|cwd|mode)\}")
        argv = [
            placeholder.sub(lambda m: values[m[1]], part) for part in self._template(request.mode)
        ]
        return [find_executable(argv[0]) or argv[0], *argv[1:]]

    def parse(
        self, request: AgentRequest, scratch: Path, exit_code: int, stdout: str, stderr: str
    ) -> AgentResult:
        ok = exit_code == 0
        return AgentResult(
            agent=self.name,
            success=ok,
            summary=stdout.strip(),
            exit_code=exit_code,
            error=None if ok else (stderr.strip()[-2000:] or f"exit code {exit_code}"),
        )
