"""The agent contract every coding-agent adapter implements.

Dia never talks to a specific vendor directly from the core. It talks to an
:class:`Agent`, and the concrete agent (Claude Code, Codex, Cursor, a local
model behind some CLI, ...) is picked by configuration.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from shutil import which
from typing import Any, ClassVar

from dia import processes

log = logging.getLogger("dia.agents")

# Where agent installers commonly put binaries. Dia may be started from a
# service, a desktop launcher or a non-login shell whose PATH misses these,
# and shell aliases are never visible to subprocesses.
FALLBACK_BIN_DIRS = (
    "~/.local/bin",
    "~/bin",
    "~/.claude/local",
    "~/.npm-global/bin",
    "~/.bun/bin",
)


def find_executable(command: str) -> str | None:
    """Resolve ``command`` to an absolute path via PATH, then the fallback dirs."""
    command = os.path.expanduser(command)
    if os.sep in command:
        return command if os.access(command, os.X_OK) else None
    fallback = os.pathsep.join(os.path.expanduser(d) for d in FALLBACK_BIN_DIRS)
    return which(command) or which(command, path=fallback)


class Mode(StrEnum):
    """What the agent is allowed to do in its working directory."""

    READ_ONLY = "read-only"  # analyse, review, plan; must not modify files
    EDIT = "edit"  # may modify files inside the (isolated) working directory


@dataclass(frozen=True)
class AgentRequest:
    prompt: str
    cwd: Path
    mode: Mode = Mode.EDIT
    timeout: float | None = None
    # Agent-specific conversation/session id to continue, when supported.
    session_id: str | None = None
    # Used for plain text completions (see Agent.complete): instructions,
    # a model override, and whether the agent may use tools at all.
    system: str | None = None
    model: str | None = None
    tools: bool = True
    # Allow searching and reading the web (research reports); agents without a
    # switch for it use their ``web_args`` option, if any.
    web: bool = False
    # CPU priority for the agent's process (``nice``), 0 = normal.
    nice: int = 0
    # Where the agent runs (dia.sandbox.Sandbox); None: unconfined.
    sandbox: Any = None

    @property
    def combined_prompt(self) -> str:
        """The prompt with ``system`` folded in, for CLIs without a system-prompt flag."""
        return f"{self.system}\n\n---\n\n{self.prompt}" if self.system else self.prompt


@dataclass
class AgentResult:
    agent: str
    success: bool
    summary: str
    exit_code: int | None = None
    duration_s: float = 0.0
    session_id: str | None = None
    error: str | None = None
    # The agent stopped because its plan's usage limit is used up; until when, if known.
    limited: bool = False
    retry_at: datetime | None = None
    # Anything adapter-specific (raw JSON, token usage, cost) for logs and memory.
    details: dict[str, Any] = field(default_factory=dict)


def mark_limit(result: AgentResult, *extra: str) -> AgentResult:
    """Flag a failed result whose messages say the usage limit is used up."""
    from dia.limits import is_limit, retry_at

    summary = result.summary if len(result.summary) < 600 else ""  # not a long answer
    text = "\n".join(t[-2000:] for t in (result.error or "", summary, *extra) if t)
    if is_limit(text):
        result.limited = True
        result.retry_at = retry_at(text)
    return result


class Agent(ABC):
    """Base class for agent plugins.

    ``kind`` is the plugin name used in configuration (``type = "codex"``);
    ``name`` is the user's instance name (``[agents.reviewer]``), so the same
    kind can be configured several times with different models or options.
    """

    kind: ClassVar[str]
    # Model names worth offering in the UI; any other name can still be typed.
    # No model configured means "auto": the CLI picks its own default.
    models: ClassVar[tuple[str, ...]] = ()

    def __init__(self, name: str, options: dict[str, Any] | None = None) -> None:
        self.name = name
        self.options: dict[str, Any] = dict(options or {})

    @abstractmethod
    async def run(self, request: AgentRequest) -> AgentResult: ...

    async def check(self) -> str | None:
        """Return a problem description if the agent cannot run, else ``None``."""
        return None

    async def complete(self, system: str, prompt: str, model: str | None = None) -> str:
        """Answer with text only (used when the agent serves as Dia's brain).

        Runs read-only in an empty directory, without tools where the CLI allows it.
        """
        with tempfile.TemporaryDirectory(prefix="dia-complete-") as cwd:
            result = await self.run(
                AgentRequest(
                    prompt=prompt,
                    cwd=Path(cwd),
                    mode=Mode.READ_ONLY,
                    system=system,
                    model=model,
                    tools=False,
                )
            )
        if not result.success:
            raise RuntimeError(f"agent '{self.name}': {result.error or 'failed'}")
        return result.summary


class CliAgent(Agent):
    """An agent driven by a non-interactive command-line invocation.

    Subclasses only describe how to build the command and how to read its
    output; process handling, timeouts and timing live here.
    """

    default_command: ClassVar[str]
    # Binary names to look for, in order of preference, when ``command`` is not
    # configured. Defaults to ``(default_command,)``.
    command_candidates: ClassVar[tuple[str, ...]] = ()

    @property
    def command(self) -> str:
        """The executable to run: an absolute path when it can be found."""
        configured = self.options.get("command")
        for name in (
            [configured] if configured else (self.command_candidates or (self.default_command,))
        ):
            if path := find_executable(name):
                return path
        return configured or self.default_command

    @property
    def extra_args(self) -> list[str]:
        return list(self.options.get("args", []))

    @abstractmethod
    def build_argv(self, request: AgentRequest, scratch: Path) -> list[str]:
        """Build the command line. ``scratch`` is a private temp dir for this run."""

    @abstractmethod
    def parse(
        self, request: AgentRequest, scratch: Path, exit_code: int, stdout: str, stderr: str
    ) -> AgentResult: ...

    async def check(self) -> str | None:
        if find_executable(self.command) is None:
            dirs = ", ".join(FALLBACK_BIN_DIRS)
            return (
                f"command '{self.command}' not found on PATH or in {dirs}; "
                "set 'command' to its full path (shell aliases are not visible)"
            )
        return None

    async def run(self, request: AgentRequest) -> AgentResult:
        with tempfile.TemporaryDirectory(prefix=f"dia-{self.kind}-") as scratch:
            return await self._run(request, Path(scratch))

    async def _run(self, request: AgentRequest, scratch: Path) -> AgentResult:
        argv = self.build_argv(request, scratch)
        if request.nice and shutil.which("nice"):
            argv = ["nice", "-n", str(request.nice), *argv]
        # System error texts stay English: the guard recognises refused reads by them.
        env = {
            **os.environ,
            "LC_MESSAGES": "C",
            **{k: str(v) for k, v in self.options.get("env", {}).items()},
        }
        if request.sandbox is not None:
            argv = request.sandbox.wrap(argv, Path(request.cwd))
            env = request.sandbox.environment(env)
        else:
            # DIA-29: never quietly run agents on the host without a sandbox.
            log.warning(
                "SECURITY: agent %r runs WITHOUT a sandbox in %s "
                "(install bubblewrap, or set [sandbox] enabled = true / auto)",
                self.name,
                request.cwd,
            )
        timeout = request.timeout or self.options.get("timeout")
        started = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=request.cwd,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,  # its own process group: the emergency stop ends it all
            )
        except FileNotFoundError:
            return AgentResult(
                agent=self.name,
                success=False,
                summary="",
                error=f"command '{argv[0]}' not found",
            )
        processes.track(proc.pid, f"agent {self.name} in {request.cwd}")
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return AgentResult(
                agent=self.name,
                success=False,
                summary="",
                exit_code=proc.returncode,
                duration_s=time.monotonic() - started,
                error=f"timed out after {timeout}s",
            )
        finally:
            processes.untrack(proc.pid)
        if processes.was_stopped(proc.pid):
            return AgentResult(
                agent=self.name,
                success=False,
                summary="",
                exit_code=proc.returncode,
                duration_s=time.monotonic() - started,
                error="stopped (emergency stop)",
            )
        result = self.parse(
            request,
            scratch,
            proc.returncode or 0,
            out.decode(errors="replace"),
            err.decode(errors="replace"),
        )
        result.duration_s = time.monotonic() - started
        if not result.success:
            mark_limit(result, err.decode(errors="replace"))
        return result
