"""Godot Engine 4 projects (GDScript, optionally C#).

Testing runs headless in the task's worktree: an import pass, then GUT or
gdUnit4 if the project has them, otherwise a short smoke run of the main
scene. Script errors fail the run even when Godot exits with 0.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from dia.agents.base import find_executable
from dia.toolchains import Toolchain
from dia.workspace import run

ERROR_PATTERNS = [
    "SCRIPT ERROR",
    "Parse Error",
    "Compile Error",
    "Failed to load script",
    "Invalid call",
    "Assertion failed",
]


def read_project(path: Path) -> dict[str, str]:
    """name, version (e.g. "4.3"), main_scene and csharp from project.godot."""
    text = (path / "project.godot").read_text(errors="replace")
    info = {
        "name": _value(text, r'^config/name="([^"]*)"'),
        "main_scene": _value(text, r'^run/main_scene="([^"]*)"'),
        "version": _value(text, r'^config/features=PackedStringArray\("(\d+\.\d+)"'),
    }
    info["csharp"] = "yes" if any(path.glob("*.csproj")) else ""
    return {k: v for k, v in info.items() if v}


def read_presets(path: Path) -> list[dict[str, str]]:
    """Export presets from export_presets.cfg: name, platform, export_path."""
    file = path / "export_presets.cfg"
    if not file.is_file():
        return []
    presets, current = [], None
    for line in file.read_text(errors="replace").splitlines():
        line = line.strip()
        if re.fullmatch(r"\[preset\.\d+\]", line):
            current = {}
            presets.append(current)
        elif line.startswith("["):
            current = None
        elif current is not None and "=" in line:
            key, value = line.split("=", 1)
            if key in ("name", "platform", "export_path"):
                current[key] = value.strip().strip('"')
    return [p for p in presets if p.get("name")]


def test_counts(output: str) -> dict[str, object] | None:
    """Passed/failed counts and failing tests from GUT or gdUnit4 output."""
    if match := re.search(
        r"Overall Summary:\s*(\d+) test cases \|\s*(\d+) errors? \|\s*(\d+) failures?", output
    ):
        total, errors, failures = (int(g) for g in match.groups())
        failed = errors + failures
        names = [
            name
            for line in output.splitlines()
            if re.search(r"\b(FAILED|ERROR)\b", line)
            for name in re.findall(r"test_\w+", line)
        ]
        return {
            "total": total,
            "passed": total - failed,
            "failed": failed,
            "failing": list(dict.fromkeys(names))[:20],
        }
    passing = re.search(r"Passing(?: Tests)?\s+(\d+)", output, re.IGNORECASE)
    failing = re.search(r"Failing(?: Tests)?\s+(\d+)", output, re.IGNORECASE)
    if passing or failing:
        passed = int(passing.group(1)) if passing else 0
        failed = int(failing.group(1)) if failing else 0
        names = re.findall(r"^\s*[-*]?\s*(test_\w+)\s*$", output, re.MULTILINE)
        names += re.findall(r"\[Failed\][^\n]*?(test_\w+)", output)
        return {
            "total": passed + failed,
            "passed": passed,
            "failed": failed,
            "failing": list(dict.fromkeys(names))[:20] if failed else [],
        }
    return None


def _value(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else ""


class GodotToolchain(Toolchain):
    kind = "godot"

    @classmethod
    def detect(cls, path: Path) -> bool:
        return (path / "project.godot").is_file()

    # -------------------------------------------------------------- binary ---

    def command(self) -> list[str] | None:
        configured = self.options.get("command")
        if isinstance(configured, list):
            return configured
        for name in [configured] if configured else ["godot4", "godot", "Godot"]:
            if path := find_executable(name):
                return [path]
        if not configured and find_executable("flatpak"):
            found = (
                subprocess.run(
                    ["flatpak", "info", "org.godotengine.Godot"], capture_output=True
                ).returncode
                == 0
            )
            if found:
                return ["flatpak", "run", "org.godotengine.Godot"]
        return None

    def check(self) -> str | None:
        if not self.command():
            return "Godot not found: install it (godot4/godot on PATH or Flatpak) or set command"
        return None

    def describe(self) -> str:
        info = read_project(self.project_path)
        tests = self._tests(self.project_path)
        return f"godot {info.get('version', '?')}, " + (tests[0] if tests else "smoke run")

    # ------------------------------------------------------------- context ---

    def context(self, workdir: Path) -> str:
        info = read_project(workdir)
        version = info.get("version", "4")
        lines = [
            f"This is a Godot {version} project"
            + (f" ('{info['name']}')" if "name" in info else "")
            + (f", main scene {info['main_scene']}" if "main_scene" in info else "")
            + ".",
            f"Use Godot {version} APIs and GDScript 2.0 syntax (typed GDScript, @export, "
            "signals as first-class), not Godot 3 APIs."
            + (" The project also uses C#." if info.get("csharp") else ""),
            "Never edit the .godot/ folder or *.import files. Keep .tscn/.tres files valid "
            "(unique ext_resource/sub_resource ids, correct load_steps).",
        ]
        if tests := self._tests(workdir):
            lines.append(f"Tests use {tests[0]}; add or update tests next to the existing ones.")
        return "\n".join(lines)

    # ---------------------------------------------------------------- test ---

    def _tests(self, workdir: Path) -> tuple[str, list[str]] | None:
        """(framework name, Godot arguments) for the project's test framework, if any."""
        if (workdir / "addons/gut/gut_cmdln.gd").is_file():
            return "GUT", ["-s", "addons/gut/gut_cmdln.gd", "-gexit"]
        if (workdir / "addons/gdUnit4/bin/GdUnitCmdTool.gd").is_file():
            return "gdUnit4", [
                "-s",
                "res://addons/gdUnit4/bin/GdUnitCmdTool.gd",
                "--ignoreHeadlessMode",
                "-a",
                self.options.get("test_dir", "res://test"),
            ]
        return None

    def _copy_import_cache(self, workdir: Path) -> None:
        """Re-use the checkout's .godot/ import cache: importing from scratch is slow."""
        source, target = self.project_path / ".godot", workdir / ".godot"
        if source.is_dir() and not target.exists() and self.options.get("reuse_import_cache", True):
            shutil.copytree(source, target, symlinks=True)

    async def _godot(self, workdir: Path, args: list[str], timeout: float) -> tuple[int, str]:
        argv = [*self.command(), "--headless", "--path", str(workdir), *args]
        if self.sandbox is not None:
            argv = self.sandbox.wrap(argv, workdir)
        return await run(argv, workdir, timeout)

    def _failed(self, output: str) -> list[str]:
        patterns = self.options.get("error_patterns", ERROR_PATTERNS)
        return [line for line in output.splitlines() if any(p in line for p in patterns)]

    async def test(
        self, workdir: Path, changed: list[str] | None = None
    ) -> tuple[bool, str] | None:
        """Import, parse every changed script, then run tests (or a smoke run).

        Godot only parses scripts that something loads, so a new or unused
        script with a syntax error would slip through the import and the smoke
        run; ``--check-only`` on each changed ``.gd`` file catches it.
        """
        if problem := self.check():
            return False, problem
        timeout = float(self.options.get("timeout", 600))
        await asyncio.to_thread(self._copy_import_cache, workdir)
        log, scope, failed = [], [], []

        import_args = list(self.options.get("import_args", ["--editor", "--quit"]))
        code, out = await self._godot(workdir, import_args, timeout)
        log.append(f"$ godot --headless {' '.join(import_args)}  (import, exit {code})\n{out}")
        errors = self._failed(out)
        scope.append(f"import {'OK' if code == 0 else f'FAILED (exit {code})'}")
        if code != 0:
            failed.append("import")

        scripts = [f for f in changed or [] if f.endswith(".gd") and (workdir / f).is_file()]
        bad_scripts = []
        for script in scripts[: int(self.options.get("max_checked_scripts", 50))]:
            code, out = await self._godot(
                workdir, ["--check-only", "--script", f"res://{script}"], timeout
            )
            if code != 0 or self._failed(out):
                bad_scripts.append(script)
                log.append(
                    f"$ godot --headless --check-only --script res://{script}  (exit {code})\n{out}"
                )
                errors += self._failed(out) or [f"{script}: check failed (exit {code})"]
        if scripts:
            scope.append(
                f"{len(scripts)} changed script(s) parsed"
                + (f", {len(bad_scripts)} with errors" if bad_scripts else "")
            )
        if bad_scripts:
            failed.append("scripts")

        if tests := self._tests(workdir):
            name, args = tests
        else:
            name, args = "smoke run", ["--quit-after", str(self.options.get("smoke_frames", 120))]
        code, out = await self._godot(workdir, args, timeout)
        log.append(f"$ godot --headless {' '.join(args)}  ({name}, exit {code})\n{out}")
        run_errors = self._failed(out)
        errors += run_errors
        result = f"{name} {'OK' if code == 0 and not run_errors else 'FAILED'}"
        if counts := test_counts(out):
            result += f" ({counts['passed']}/{counts['total']} passed"
            if counts["failing"]:
                result += "; failing: " + ", ".join(counts["failing"][:8])
            result += ")"
        scope.append(result)
        if code != 0 or run_errors:
            failed.append(name)

        ok = not failed and not errors
        summary = "Godot: " + "; ".join(scope)
        if not self._tests(workdir):
            summary += " (no GUT/gdUnit4 found: set test_command to run the project's own tests)"
        if errors:
            log.append("Errors found:\n" + "\n".join(dict.fromkeys(errors[:20])))
        return ok, summary + "\n\n" + "\n".join(log)

    # --------------------------------------------------------------- build ---

    def presets(self, workdir: Path) -> list[str]:
        return [p["name"] for p in read_presets(workdir)]

    async def build(self, workdir: Path, preset: str, output_dir: Path) -> list[Path]:
        """``godot --export-release``; needs the export templates installed."""
        if problem := self.check():
            raise RuntimeError(problem)
        found = {p["name"]: p for p in read_presets(workdir)}
        if preset not in found:
            known = ", ".join(found) or "none (add one in Project → Export)"
            raise RuntimeError(f"no export preset '{preset}' (presets: {known})")
        await asyncio.to_thread(self._copy_import_cache, workdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        name = Path(
            found[preset].get("export_path") or f"{read_project(workdir).get('name', 'game')}"
        )
        target = output_dir / name.name
        started = time.time() - 1
        timeout = float(self.options.get("build_timeout", 1800))
        await self._godot(workdir, ["--editor", "--quit"], timeout)  # import first
        code, out = await self._godot(workdir, ["--export-release", preset, str(target)], timeout)
        # what this export wrote, including files it overwrote from an earlier build
        made = sorted(p for p in output_dir.iterdir() if p.stat().st_mtime >= started)
        if code != 0 or not made:
            hint = " (are the export templates installed? Editor → Manage Export Templates)"
            raise RuntimeError(f"export '{preset}' failed{hint}:\n{out.strip()[-1500:]}")
        return made

    # -------------------------------------------------------------- launch ---

    async def launch(self, workdir: Path) -> str:
        if problem := self.check():
            raise RuntimeError(problem)
        args = ["-e"] if self.options.get("launch_editor") else []
        subprocess.Popen(  # detached: the game keeps running after Dia moves on
            [*self.command(), "--path", str(workdir), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
        info = read_project(workdir)
        return f"started {info.get('name', workdir.name)}"
