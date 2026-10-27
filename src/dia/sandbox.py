"""The agent sandbox: what an agent can see while it works.

An agent runs inside bubblewrap (``bwrap``): the system is visible read-only,
your home directory is replaced by an empty one, and only what the agent
needs comes back:

- its worktree (read and write) and the repository's git data it needs;
- its own configuration and login (``~/.claude``, ``~/.codex``, ``~/.cursor``);
- the tools it runs with (``~/.local/bin``, ``~/.npm-global``, ``~/.nvm``...);
- ``/tmp``.

So ``~/.ssh``, ``~/.gnupg``, ``~/.config/dia`` (your secrets), browser
profiles, other projects and the rest of home are simply not there. Dia's
own secrets are also removed from the agent's environment, except an API key
the agent itself needs.

    [sandbox]
    enabled = "auto"         # "auto": when bwrap works here; true: required; false: off
    allow_read = ["~/Projekty/Software/shared-assets"]   # extra, read-only
    allow_write = []                                        # extra, read and write
    hide = ["/mnt/backup"]   # extra places outside home to hide
    network = true           # agents need their APIs; false cuts the network
    decoys = true            # fake secrets where real ones were (see dia.guard)

    [agents.claude]
    sandbox = { allow_read = ["~/.config/some-tool"], pass_env = ["SOME_TOKEN"] }

``dia sandbox check`` shows what each agent would see and whether it starts.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dia.config import Config, ProjectConfig

# Tools agents run with (read-only).
COMMON_READ = [
    "~/.gitconfig",
    "~/.config/git",
    "~/.local/bin",
    "~/.local/lib",
    "~/.npm-global",
    "~/.nvm",
    "~/.bun",
    "~/.volta",
    "~/.cargo/bin",
    "~/.local/share/pnpm",
    "~/.local/share/mise",
    "~/.local/share/fnm",
]
COMMON_WRITE = ["~/.npm", "~/.cache/node", "~/.cache/pip"]

# Each agent's own configuration, login and installation (read and write).
AGENT_DIRS = {
    "claude-code": ["~/.claude", "~/.claude.json", "~/.local/share/claude", "~/.cache/claude"],
    "codex": ["~/.codex"],
    "cursor": ["~/.cursor", "~/.config/cursor", "~/.local/share/cursor-agent"],
}
# The API key an agent may need from Dia's secrets.
AGENT_KEYS = {
    "claude-code": ["ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"],
    "codex": ["OPENAI_API_KEY", "CODEX_API_KEY"],
    "cursor": ["CURSOR_API_KEY"],
}


def _expand(paths: list[str]) -> list[Path]:
    return [Path(os.path.expanduser(os.path.expandvars(p))) for p in paths]


@functools.cache
def bwrap_works() -> bool:
    """Whether bubblewrap is installed and may create namespaces here."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return False
    try:
        result = subprocess.run(
            [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "true"],
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


@dataclass
class Sandbox:
    """What one agent may see; :meth:`wrap` turns a command into a sandboxed one."""

    read: list[Path] = field(default_factory=list)
    write: list[Path] = field(default_factory=list)
    hide: list[Path] = field(default_factory=list)
    network: bool = True
    keep_env: set[str] = field(default_factory=set)
    secret_names: set[str] = field(default_factory=set)
    decoys: Path | None = None  # a fake home with decoy secrets (dia.guard)

    @property
    def home(self) -> Path:
        return Path.home()

    def wrap(self, argv: list[str], cwd: Path) -> list[str]:
        home = self.home
        args = ["bwrap", "--die-with-parent", "--unshare-ipc", "--unshare-uts"]
        if not self.network:
            args.append("--unshare-net")
        args += [
            "--ro-bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--bind",
            "/tmp",
            "/tmp",
        ]
        # An empty home (or the decoys), then only what is allowed back in.
        if self.decoys and self.decoys.is_dir():
            args += ["--bind", str(self.decoys), str(home)]  # throwaway; removed after
        else:
            args += ["--tmpfs", str(home)]
        for path in self.hide:
            if not path.exists() or _inside(home, path):
                continue
            if path.is_dir():
                args += ["--tmpfs", str(path)]
            else:
                args += ["--ro-bind", "/dev/null", str(path)]
        binds: list[tuple[str, Path]] = []
        binds += [("--ro-bind", p) for p in self.read]
        binds += [("--bind", p) for p in self.write]
        # The repository's git data read-only (no moving main, no hooks); the
        # worktree's own git state and its task branch writable.
        common, own = _git_dirs(cwd)
        binds += [("--ro-bind", p) for p in common] + [("--bind", p) for p in own]
        binds += [("--bind", cwd)]
        for flag, path in binds:
            if path.exists():
                args += [flag, str(path), str(path)]
        args += ["--chdir", str(cwd), "--"]
        return args + argv

    def environment(self, env: dict[str, str]) -> dict[str, str]:
        """``env`` without Dia's secrets (but with the agent's own key)."""
        drop = self.secret_names - self.keep_env
        return {k: v for k, v in env.items() if k not in drop}

    def describe(self) -> str:
        shown = [f"  rw {p}" for p in self.write if p.exists()]
        shown += [f"  ro {p}" for p in self.read if p.exists()]
        return "\n".join(shown) or "  (only the working directory)"


def _secrets_dir() -> Path:
    """Where Dia's secrets file lives (hidden even when it is outside home)."""
    from dia.service import env_path

    return env_path().parent


def _inside(parent: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _git_dirs(cwd: Path) -> tuple[list[Path], list[Path]]:
    """The repository's git data and a worktree's own git directory, which the
    worktree's ``.git`` file points into: ([common], [own])."""
    marker = cwd / ".git"
    if not marker.is_file():
        return [], []
    text = marker.read_text(errors="replace").strip()
    if not text.startswith("gitdir:"):
        return [], []
    own = (cwd / text.split(":", 1)[1].strip()).resolve()
    common = own.parent.parent  # <repo>/.git/worktrees/<name> -> <repo>/.git
    # An agent may commit on its own task branch (objects, refs/heads/dia/*), but
    # main, other branches, hooks and the config stay read-only.
    writable = [own, common / "objects", common / "refs/heads/dia", common / "logs/refs/heads/dia"]
    return [common], writable


def enabled(config: Config) -> bool:
    """Whether agents run sandboxed: ``[sandbox] enabled`` ("auto" by default)."""
    setting = config.section("sandbox").get("enabled", "auto")
    if setting is False or str(setting).lower() in ("false", "off", "no"):
        return False
    if setting is True or str(setting).lower() in ("true", "on", "yes", "required"):
        if not bwrap_works():
            raise RuntimeError(
                "[sandbox] is required but bubblewrap does not work here "
                "(install bubblewrap; it needs unprivileged user namespaces)"
            )
        return True
    return bwrap_works()


# What a project's tests may write besides the worktree (engines keep caches).
TEST_WRITE = [
    "~/.config/godot",
    "~/.cache/godot",
    "~/.local/share/godot",
    "~/.cache/pip",
    "~/.npm",
    "~/.cache/node",
]


def for_tests(config: Config, project: ProjectConfig | None = None) -> Sandbox | None:
    """The sandbox a project's tests run in: code an agent wrote runs there too.
    ``[sandbox] tests = false`` runs them unconfined."""
    options = config.section("sandbox")
    if not enabled(config) or options.get("tests", True) is False:
        return None
    from dia import secrets

    project_options = (project.options.get("sandbox") or {}) if project else {}
    read = COMMON_READ + list(options.get("allow_read", []))
    read += list(project_options.get("allow_read", []))
    write = TEST_WRITE + list(options.get("allow_write", []))
    write += list(project_options.get("allow_write", []))
    return Sandbox(
        read=_expand(read),
        write=_expand(write),
        hide=_expand(list(options.get("hide", []))) + [config.data_dir, _secrets_dir()],
        network=bool(options.get("test_network", True)),
        secret_names=set(secrets.names()),
    )


def for_agent(
    config: Config,
    agent_kind: str,
    agent_options: dict[str, Any],
    project: ProjectConfig | None = None,
    decoys: Path | None = None,
) -> Sandbox | None:
    """The sandbox an agent runs in, or None when sandboxing is off."""
    if not enabled(config):
        return None
    from dia import secrets

    options = config.section("sandbox")
    own = agent_options.get("sandbox") or {}
    project_options = (project.options.get("sandbox") or {}) if project else {}
    read = COMMON_READ + list(options.get("allow_read", []))
    read += list(own.get("allow_read", [])) + list(project_options.get("allow_read", []))
    write = AGENT_DIRS.get(agent_kind, []) + COMMON_WRITE + list(options.get("allow_write", []))
    write += list(own.get("allow_write", [])) + list(project_options.get("allow_write", []))
    return Sandbox(
        read=_expand(read),
        write=_expand(write),
        hide=_expand(list(options.get("hide", []))) + [config.data_dir, _secrets_dir()],
        network=bool(own.get("network", options.get("network", True))),
        keep_env=set(AGENT_KEYS.get(agent_kind, [])) | set(own.get("pass_env", [])),
        secret_names=set(secrets.names()),
        decoys=decoys,
    )
