"""Toolchains: what Dia knows about a kind of project (engine, language, build).

A toolchain can test a worktree when the project has no ``test_command``,
describe the project to agents, and launch it. ``toolchain = "auto"`` (the
default) picks the first installed toolchain that recognises the project.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar


class Toolchain(ABC):
    kind: ClassVar[str]

    def __init__(self, project_path: Path, options: dict[str, Any] | None = None) -> None:
        self.project_path = project_path
        self.options: dict[str, Any] = dict(options or {})
        self.sandbox: Any = None  # dia.sandbox.Sandbox for test runs, set by the orchestrator

    @classmethod
    @abstractmethod
    def detect(cls, path: Path) -> bool:
        """Does the project at ``path`` use this toolchain?"""

    def check(self) -> str | None:
        return None

    def describe(self) -> str:
        return self.kind

    def context(self, workdir: Path) -> str:
        """Facts and conventions for agents working on the project ('' if none)."""
        return ""

    async def test(
        self, workdir: Path, changed: list[str] | None = None
    ) -> tuple[bool, str] | None:
        """Build/test ``workdir``; None when the toolchain knows no way to test it.

        ``changed``: paths (relative to ``workdir``) the task changed, so the
        toolchain can check them specifically.
        """
        return None

    async def launch(self, workdir: Path) -> str:
        raise NotImplementedError(f"{self.kind} projects cannot be launched by Dia")

    def presets(self, workdir: Path) -> list[str]:
        """Names of the builds the project defines (e.g. Godot export presets)."""
        return []

    async def build(self, workdir: Path, preset: str, output_dir: Path) -> list[Path]:
        """Build ``preset`` of ``workdir`` into ``output_dir``; the files it made."""
        raise NotImplementedError(f"Dia doesn't know how to build {self.kind} projects")
