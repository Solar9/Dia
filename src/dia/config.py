"""Configuration: which agents exist, which projects Dia manages, where data lives.

Nothing in the core assumes a particular vendor, forge or engine; all of it
comes from a TOML file. Lookup order: ``--config``, ``$DIA_CONFIG``,
``./dia.toml``, ``$XDG_CONFIG_HOME/dia/config.toml``.

Settings changed in the UI are kept apart, in ``settings.json`` next to the
config file, and laid over it section by section, so the hand-written TOML
(and its comments) is never rewritten by a form.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia import plugins
from dia.agents import Agent
from dia.memory import Memory

if TYPE_CHECKING:
    from dia.brains import Brain
    from dia.channels import Channel
    from dia.orchestrator import Orchestrator


class ConfigError(Exception):
    pass


@dataclass
class ProjectConfig:
    name: str
    path: Path
    base_branch: str | None = None  # None: the repository's current branch
    test_command: str | None = None
    default_agent: str | None = None
    # Free-form extras for plugins (forge, toolchain, ...).
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    data_dir: Path
    agents: dict[str, dict[str, Any]]
    projects: dict[str, ProjectConfig]
    default_agent: str | None = None
    max_parallel_tasks: int = 2
    language: str = "en"  # of Dia's own messages (status, questions): "pl" or "en"
    # [channels.<name>] sections: interfaces such as Discord.
    channels: dict[str, dict[str, Any]] = field(default_factory=dict)
    # [brains.<name>] sections, and the order to try them in ([dia] brain).
    brains: dict[str, dict[str, Any]] = field(default_factory=dict)
    brain_order: list[str] | None = None
    # [review]: cross-review defaults (reviewer, auto, fix_rounds, max_diff_chars).
    review: dict[str, Any] = field(default_factory=dict)
    # [ci]: CI watching of published tasks (watch, interval, autofix, fix_rounds).
    ci: dict[str, Any] = field(default_factory=dict)
    # [ui]: the local web UI and API of `dia serve` (enabled, port).
    ui: dict[str, Any] = field(default_factory=dict)
    # [limits]: usage-limit handling (fallback, wait, max_wait_hours, cooldown_minutes).
    limits: dict[str, Any] = field(default_factory=dict)
    # [watch]: test new commits of projects in `dia serve` (enabled, interval, projects).
    watch: dict[str, Any] = field(default_factory=dict)
    # [pipelines.<name>]: fixed multi-step recipes; [plans]: planner settings.
    pipelines: dict[str, dict[str, Any]] = field(default_factory=dict)
    plans: dict[str, Any] = field(default_factory=dict)
    # Options of the optional [memory] section; None when memory is off.
    memory_options: dict[str, Any] | None = None
    # [assistant]: persona (name, user_name, personality) and everyday skills.
    assistant: dict[str, Any] = field(default_factory=dict)
    # The whole merged configuration, for sections plugins read themselves.
    raw: dict[str, Any] = field(default_factory=dict)
    source: Path | None = None
    # Other config files that exist but are not used because ``source`` wins.
    shadowed: list[Path] = field(default_factory=list)

    def section(self, name: str) -> dict[str, Any]:
        """A top-level table (``[schedule]``, ``[push]``...), empty when missing."""
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    @property
    def settings_path(self) -> Path | None:
        """Where the UI's settings go: ``settings.json`` beside the config file."""
        return self.source.parent / "settings.json" if self.source else None

    @staticmethod
    def split_agent(spec: str) -> tuple[str, str | None]:
        """``"claude:opus"`` -> (``"claude"``, ``"opus"``): an agent with a model for this use."""
        name, _, model = spec.partition(":")
        return name, model.strip() or None

    def agent(self, name: str | None = None, project: ProjectConfig | None = None) -> Agent:
        name = name or (project.default_agent if project else None) or self.default_agent
        if not name:
            raise ConfigError("no agent given and no default_agent configured")
        name, model = self.split_agent(name)
        if name not in self.agents:
            raise ConfigError(f"unknown agent '{name}' (configured: {', '.join(self.agents)})")
        options = dict(self.agents[name])
        if model:
            options["model"] = model
        kind = options.pop("type", name)
        cls = plugins.load("dia.agents", kind)
        return cls(name, options)

    def memory(self) -> Memory | None:
        if self.memory_options is None or self.memory_options.get("enabled", True) is False:
            return None
        options = dict(self.memory_options)
        options.pop("enabled", None)
        options.setdefault("index_dir", str(self.data_dir))
        kind = options.pop("type", "markdown")
        try:
            return plugins.load("dia.memory", kind)(options)
        except (LookupError, ValueError) as exc:
            raise ConfigError(f"[memory]: {exc}") from None

    def brain_chain(self, only: str | None = None) -> list[Brain]:
        """Brains in the order to try them.

        Without ``[dia] brain``: the rule brain, then the default agent as brain.
        A name is a ``[brains.<name>]`` section or, without options, a plugin kind.
        """
        if only:
            order = [only]
        elif self.brain_order is not None:
            order = self.brain_order
        else:
            order = ["rules"] + (["default-agent"] if self.default_agent else [])
        chain = []
        for name in order:
            if name in self.brains:
                options = dict(self.brains[name])
                kind = options.pop("type", name)
            elif name == "default-agent":
                options, kind = {}, "agent"
            else:
                options, kind = {}, name
            try:
                chain.append(plugins.load("dia.brains", kind)(name, options, self))
            except LookupError as exc:
                raise ConfigError(f"brain '{name}': {exc}") from None
        return chain

    def channel(self, name: str, dia: Orchestrator) -> Channel:
        options = dict(self.channels[name])
        kind = options.pop("type", name)
        try:
            cls = plugins.load("dia.channels", kind)
        except ModuleNotFoundError as exc:
            raise ConfigError(
                f"[channels.{name}] needs an optional dependency ({exc.name}); "
                f"install it with: pip install 'dia[{kind}]'"
            ) from None
        except LookupError as exc:
            raise ConfigError(f"[channels.{name}]: {exc}") from None
        try:
            return cls(name, options, dia)
        except ValueError as exc:
            raise ConfigError(f"[channels.{name}]: {exc}") from None

    def project(self, name: str) -> ProjectConfig:
        try:
            return self.projects[name]
        except KeyError:
            raise ConfigError(
                f"unknown project '{name}' (configured: {', '.join(self.projects) or 'none'})"
            ) from None


def _default_paths() -> list[Path]:
    paths = []
    if env := os.environ.get("DIA_CONFIG"):
        paths.append(Path(env))
    paths.append(Path.cwd() / "dia.toml")
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    paths.append(xdg / "dia" / "config.toml")
    return paths


def _expand(path: str | Path, relative_to: Path) -> Path:
    p = Path(os.path.expandvars(str(path))).expanduser()
    return p if p.is_absolute() else (relative_to / p).resolve()


def merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """``overlay`` laid over ``base``: tables merge key by key, anything else replaces."""
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        elif value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


def read_settings(source: Path) -> dict[str, Any]:
    path = source.parent / "settings.json"
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except ValueError as exc:
        raise ConfigError(f"{path}: {exc}") from None
    return data if isinstance(data, dict) else {}


def load_file(candidate: Path) -> Config:
    raw = tomllib.loads(candidate.read_text())
    return parse_config(merge(raw, read_settings(candidate)), candidate)


def save_settings(config: Config, changes: dict[str, Any]) -> Config:
    """Merge ``changes`` into settings.json (``None`` removes a key) and return the
    new configuration; nothing is written when the result is invalid."""
    if not config.source:
        raise ConfigError("Dia was started without a config file")
    settings = merge(read_settings(config.source), changes)
    raw = tomllib.loads(config.source.read_text())
    new = parse_config(merge(raw, settings), config.source)
    path = config.settings_path
    assert path is not None
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    path.chmod(0o600)
    new.shadowed = config.shadowed
    return new


def load_config(path: Path | None = None) -> Config:
    candidates = [path] if path else _default_paths()
    for i, candidate in enumerate(candidates):
        if candidate.is_file():
            config = load_file(candidate)
            config.shadowed = [
                c for c in candidates[i + 1 :] if c.is_file() and c.resolve() != candidate.resolve()
            ]
            return config
    if path:
        raise ConfigError(f"config file not found: {path}")
    raise ConfigError(
        "no config found: run `dia setup` (or copy dia.example.toml to ~/.config/dia/config.toml)"
    )


def parse_config(raw: dict[str, Any], source: Path | None = None) -> Config:
    base = source.parent if source else Path.cwd()
    core = raw.get("dia", {})
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    data_dir = _expand(core.get("data_dir", xdg_data / "dia"), base)

    agents = raw.get("agents", {})
    for name, opts in agents.items():
        if not isinstance(opts, dict):
            raise ConfigError(f"[agents.{name}] must be a table")

    projects = {}
    for name, opts in raw.get("projects", {}).items():
        opts = dict(opts)
        if "path" not in opts:
            raise ConfigError(f"[projects.{name}] needs a 'path'")
        projects[name] = ProjectConfig(
            name=name,
            path=_expand(opts.pop("path"), base),
            base_branch=opts.pop("base_branch", None),
            test_command=opts.pop("test_command", None),
            default_agent=opts.pop("default_agent", None),
            options=opts,
        )
    return Config(
        data_dir=data_dir,
        agents=agents,
        projects=projects,
        default_agent=core.get("default_agent"),
        max_parallel_tasks=int(core.get("max_parallel_tasks", 2)),
        language=core.get("language", "en"),
        channels=raw.get("channels", {}),
        brains=raw.get("brains", {}),
        review=raw.get("review", {}),
        ci=raw.get("ci", {}),
        limits=raw.get("limits", {}),
        watch=raw.get("watch", {}),
        pipelines=raw.get("pipelines", {}),
        ui=raw.get("ui", {}),
        plans=raw.get("plans", {}),
        brain_order=[core["brain"]] if isinstance(core.get("brain"), str) else core.get("brain"),
        memory_options=raw.get("memory"),
        assistant=raw.get("assistant", {}),
        raw=raw,
        source=source,
    )
