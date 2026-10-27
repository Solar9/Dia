"""The disposable lab: run something in a throwaway container, never on your
computer itself.

For experiments that install software, try a configuration or run code
nobody has reviewed yet: Dia copies the project (a commit of it, without its
git history) into a fresh directory, starts a container with it mounted at
``/work``, runs the command and throws both away. By default the container
has no network, no added privileges, limited memory and CPU, and sees nothing
of your home.

    [lab]
    engine = "podman"                         # or "docker" (default: whichever is installed)
    image = "docker.io/library/python:3.13-slim"
    network = false
    memory = "4g"
    cpus = 2
    timeout = 1800

``dia lab nova "godot --headless --version" --image my-godot-image`` or, in
code, ``Lab(dia).run(...)``; experiments (milestone 2) build on it.
"""

from __future__ import annotations

import asyncio
import io
import secrets
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.workspace import git, run

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator


@dataclass
class LabResult:
    code: int
    output: str
    image: str
    seconds: float
    kept: str | None = None  # the work directory, when asked to keep it

    @property
    def ok(self) -> bool:
        return self.code == 0


def engine_command(options: dict[str, Any]) -> list[str] | None:
    if command := options.get("command"):  # a full command line (tests, wrappers)
        return list(command)
    wanted = options.get("engine")
    for name in [wanted] if wanted else ["podman", "docker"]:
        if name and (path := shutil.which(name)):
            return [path]
    return None


class Lab:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia
        self.options = dia.config.section("lab")

    def check(self) -> str | None:
        if not engine_command(self.options):
            return "no container engine: install podman (or docker)"
        return None

    async def _copy_project(self, project_name: str, ref: str | None, target: Path) -> str:
        """The project at ``ref`` (default: its base branch) as plain files."""
        project = self.dia.config.project(project_name)
        ref = ref or project.base_branch or "HEAD"
        sha = await git(project.path, "rev-parse", "--verify", f"{ref}^{{commit}}")
        proc = await asyncio.create_subprocess_exec(
            "git",
            "archive",
            "--format=tar",
            sha,
            cwd=project.path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        data, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git archive failed: {err.decode(errors='replace')[:300]}")
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            archive.extractall(target, filter="data")
        return sha

    async def run(
        self,
        command: str,
        project: str | None = None,
        ref: str | None = None,
        image: str | None = None,
        network: bool | None = None,
        keep: bool = False,
        timeout: float | None = None,
    ) -> LabResult:
        engine = engine_command(self.options)
        if not engine:
            raise RuntimeError("no container engine: install podman (or docker)")
        lab_id = secrets.token_hex(4)
        work = self.dia.config.data_dir / "lab" / lab_id
        work.mkdir(parents=True)
        image = image or self.options.get("image", "docker.io/library/python:3.13-slim")
        network = self.options.get("network", False) if network is None else network
        detail = command[:200]
        try:
            if project:
                sha = await self._copy_project(project, ref, work)
                detail = f"{project}@{sha[:10]}: {detail}"
            self.dia.audit("lab.run", lab_id, f"{image} {detail}")
            name = f"dia-lab-{lab_id}"
            argv = [
                *engine,
                "run",
                "--rm",
                "--name",
                name,
                "--network",
                "bridge" if network else "none",
                "--memory",
                str(self.options.get("memory", "4g")),
                "--cpus",
                str(self.options.get("cpus", 2)),
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--volume",
                f"{work}:/work:Z",
                "--workdir",
                "/work",
                image,
                "sh",
                "-c",
                command,
            ]
            limit = float(timeout or self.options.get("timeout", 1800))
            started = asyncio.get_running_loop().time()
            code, out = await run(argv, work, limit, stoppable=True)
            if code == -1 and out.startswith("timed out"):
                await run([*engine, "kill", name], work, 30)
            seconds = asyncio.get_running_loop().time() - started
        finally:
            if not keep:
                shutil.rmtree(work, ignore_errors=True)
        return LabResult(code, out, image, round(seconds, 1), str(work) if keep else None)
