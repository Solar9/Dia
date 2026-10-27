"""Builds and changelogs: "Dia, przygotuj nową wersję testową Nova".

A build is made from a commit of your project (default: the base branch) in
a detached worktree: tests first, then every export preset (or the ones you
name), into ``<data_dir>/builds/<project>/<version>/<preset>/`` with a
CHANGELOG.md. Publishing the build stays your decision; Dia never uploads it.

The changelog lists the commits since the previous tag; with ``write`` an
agent turns them into notes for players (or testers) in your language.

    [builds]
    test_first = true
    presets = ["Linux", "Windows Desktop"]   # default: all export presets
    changelog_agent = "claude"               # who writes changelogs (default agent)
    changelog_model = "haiku"
    itch = "yourname/nova"                   # itch.io target for `butler push`
    itch_channels = { "Linux" = "linux", "Windows Desktop" = "windows" }

Publishing to itch.io is a separate, explicit step (the Publish button on a
build, or ``dia publish-build <task>``) with ``butler`` logged in (``butler
login`` or the secret BUTLER_API_KEY).

Steam is the same, with ``steamcmd`` (``dia publish-build <task> --steam``)::

    [builds.steam]
    app_id = 1234560
    depots = { "Linux" = 1234561, "Windows Desktop" = 1234562 }
    username = "your_steam_build_account"   # log in once yourself: steamcmd +login <name>
    branch = "beta"                         # set the build live there (optional)

Dia never sets a build live on the default branch (the one players get):
that stays your click in Steamworks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dia.agents import AgentRequest, Mode
from dia.store import TaskRecord, now
from dia.workspace import GitError, Workspace, git

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

CHANGELOG_PROMPT = """\
Write release notes for version {version} of "{project}" from these commit
messages (newest first). Write for {audience}, in {language}: group related
changes, use short bullet points under "New", "Changed" and "Fixed" (omit
empty groups), leave out purely internal changes (refactors, CI, typos),
and don't invent anything that the commits don't say. Answer with the notes
only, in Markdown.

Commits:
{commits}
"""


def app_build_vdf(
    app_id: int, description: str, depots: dict[str, Path], output: Path, branch: str = ""
) -> str:
    """A steamcmd app build script with the depots inline (one folder per depot)."""

    def q(value: object) -> str:
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = [
        '"AppBuild"',
        "{",
        f'\t"AppID" {q(app_id)}',
        f'\t"Desc" {q(description)}',
        f'\t"BuildOutput" {q(output)}',
    ]
    if branch:
        lines.append(f'\t"SetLive" {q(branch)}')
    lines += ['\t"Depots"', "\t{"]
    for depot, folder in depots.items():
        lines += [
            f"\t\t{q(depot)}",
            "\t\t{",
            f'\t\t\t"ContentRoot" {q(folder)}',
            '\t\t\t"FileMapping"',
            "\t\t\t{",
            '\t\t\t\t"LocalPath" "*"',
            '\t\t\t\t"DepotPath" "."',
            '\t\t\t\t"recursive" "1"',
            "\t\t\t}",
            "\t\t}",
        ]
    lines += ["\t}", "}"]
    return "\n".join(lines) + "\n"


def _slug(text: str) -> str:
    return re.sub(r"[^\w.-]+", "-", text).strip("-") or "build"


class Releases:
    def __init__(self, dia: Orchestrator) -> None:
        self.dia = dia

    @property
    def options(self) -> dict[str, Any]:
        return self.dia.config.section("builds")

    async def _previous_tag(self, repo: Path, ref: str) -> str | None:
        for target in (ref, f"{ref}^"):
            try:
                tag = await git(repo, "describe", "--tags", "--abbrev=0", target)
            except GitError:
                return None
            if await git(repo, "rev-parse", f"{tag}^{{commit}}") != await git(
                repo, "rev-parse", ref
            ):
                return tag
        return None

    async def changelog(
        self,
        project_name: str,
        since: str | None = None,
        ref: str = "HEAD",
        write: bool = False,
        version: str | None = None,
        audience: str = "players and testers",
    ) -> str:
        """The changes since ``since`` (default: the previous tag), as Markdown."""
        project = self.dia.config.project(project_name)
        since = since or await self._previous_tag(project.path, ref)
        span = f"{since}..{ref}" if since else ref
        args = ["log", "--no-merges", "--format=%s", span]
        if not since:
            args.insert(1, "-50")
        subjects = [s for s in (await git(project.path, *args)).splitlines() if s.strip()]
        subjects = [s for s in subjects if not s.startswith("dia: step")]  # Dia's own step commits
        if not subjects:
            return "(no changes)"
        plain = "\n".join(f"- {s}" for s in subjects)
        if not write:
            return (f"Since {since}:\n\n" if since else "") + plain
        agent = self.dia.config.agent(self.options.get("changelog_agent"), project)
        language = {"pl": "Polish", "en": "English"}.get(self.dia.config.language, "English")
        _, result = await self.dia.call_agent(
            agent,
            AgentRequest(
                prompt=CHANGELOG_PROMPT.format(
                    version=version or ref,
                    project=project.name,
                    audience=audience,
                    language=language,
                    commits=plain,
                ),
                cwd=project.path,
                mode=Mode.READ_ONLY,
                model=self.options.get("changelog_model"),
                tools=False,
            ),
            purpose="changelog",
        )
        return result.summary.strip() if result.success and result.summary.strip() else plain

    async def publish_itch(self, task_id: str) -> list[str]:
        """Upload a finished build to itch.io with butler. Only ever on your request."""
        from dia.agents.base import find_executable
        from dia.orchestrator import TaskActionError
        from dia.workspace import run

        task = self.dia.store.get(task_id)
        if not task or task.mode != "build" or task.status != "done":
            raise TaskActionError(f"task {task_id} is not a finished build")
        target = self.options.get("itch") or self.dia.config.project(task.project).options.get(
            "itch"
        )
        if not target:
            raise TaskActionError('set [builds] itch = "yourname/game" to publish on itch.io')
        butler = find_executable("butler")
        if not butler:
            raise TaskActionError("butler is not installed (https://itch.io/docs/butler/)")
        channels = self.options.get("itch_channels", {})
        version = task.details.get("version", "")
        pushed = []
        for build in task.details.get("builds", []):
            folder = Path(build["files"][0]).parent if build["files"] else None
            if not folder:
                continue
            channel = channels.get(build["preset"]) or _slug(build["preset"]).lower()
            argv = [butler, "push", str(folder), f"{target}:{channel}"]
            if version:
                argv += ["--userversion", version]
            code, out = await run(argv, folder, 1800)
            if code != 0:
                raise TaskActionError(f"butler push {channel} failed: {out.strip()[-800:]}")
            pushed.append(f"{target}:{channel}")
            self.dia.audit("build.publish", task.id, f"{target}:{channel} {version}")
        task.details.setdefault("published", {})["itch"] = pushed
        self.dia.store.save(task)
        return pushed

    async def publish_steam(self, task_id: str) -> str:
        """Upload a finished build to Steam with steamcmd. Only ever on your request."""
        from dia.agents.base import find_executable
        from dia.orchestrator import TaskActionError
        from dia.workspace import run

        task = self.dia.store.get(task_id)
        if not task or task.mode != "build" or task.status != "done":
            raise TaskActionError(f"task {task_id} is not a finished build")
        steam = self.options.get("steam") or {}
        app_id, depots = steam.get("app_id"), steam.get("depots") or {}
        if not app_id or not depots or not steam.get("username"):
            raise TaskActionError("set [builds.steam] app_id, depots and username to publish")
        branch = str(steam.get("branch") or "")
        if branch.lower() in ("default", "public"):
            raise TaskActionError("Dia doesn't set builds live on the default branch")
        steamcmd = find_executable("steamcmd")
        if not steamcmd:
            raise TaskActionError("steamcmd is not installed")
        folders = {
            b["preset"]: Path(b["files"][0]).parent
            for b in task.details.get("builds", [])
            if b["files"]
        }
        chosen = {str(d): folders[p] for p, d in depots.items() if p in folders}
        if not chosen:
            raise TaskActionError("none of the built presets has a depot in [builds.steam] depots")
        work = self.dia.config.data_dir / "steam" / task.id
        work.mkdir(parents=True, exist_ok=True)
        script = work / f"app_build_{app_id}.vdf"
        script.write_text(
            app_build_vdf(
                int(app_id),
                f"Dia: {task.project} {task.details.get('version', '')}".strip(),
                chosen,
                work / "output",
                branch,
            )
        )
        argv = [steamcmd, "+login", str(steam["username"]), "+run_app_build", str(script), "+quit"]
        code, out = await run(argv, work, 3600)
        if code != 0 or "ERROR" in out:
            raise TaskActionError(f"steamcmd failed: {out.strip()[-800:]}")
        build_id = re.search(r"BuildID (\d+)", out)
        target = f"steam:{app_id}" + (f" ({branch})" if branch else "")
        self.dia.audit("build.publish", task.id, f"{target} {task.details.get('version', '')}")
        task.details.setdefault("published", {})["steam"] = {
            "app_id": app_id,
            "branch": branch,
            "build_id": build_id.group(1) if build_id else "",
        }
        self.dia.store.save(task)
        return target + (f", build {build_id.group(1)}" if build_id else "")

    async def build(
        self,
        project_name: str,
        presets: list[str] | None = None,
        ref: str | None = None,
        version: str | None = None,
        write_changelog: bool = False,
    ) -> TaskRecord:
        """Test and build a commit; recorded as a task with mode "build"."""
        from dia.orchestrator import TaskActionError, new_task_id

        self.dia._ensure_running()
        project = self.dia.config.project(project_name)
        toolchain = self.dia.toolchain_for(project)
        if not toolchain:
            raise TaskActionError(f"Dia doesn't know how to build {project.name}")
        ref = ref or project.base_branch or "HEAD"
        try:
            sha = await git(project.path, "rev-parse", "--verify", f"{ref}^{{commit}}")
            version = version or await git(project.path, "describe", "--tags", "--always", sha)
        except GitError as exc:
            raise TaskActionError(str(exc)) from None
        presets = presets or self.options.get("presets") or toolchain.presets(project.path)
        if not presets:
            raise TaskActionError(f"{project.name} has no build presets (Godot: Project → Export)")
        task = TaskRecord(
            id=new_task_id(),
            project=project.name,
            agent="-",
            mode="build",
            prompt=f"build {version} ({', '.join(presets)})",
            status="running",
            commit_sha=sha,
            details={"version": version, "presets": presets},
        )
        self.dia.store.save(task)
        self.dia.audit("build.start", task.id, task.prompt)
        out_root = self.dia.config.data_dir / "builds" / project.name / _slug(version)
        path = self.dia.config.data_dir / "worktrees" / project.name / task.id
        workspace = Workspace(repo=project.path, path=path, branch="", base=sha)
        try:
            async with self.dia._slots:
                path.parent.mkdir(parents=True, exist_ok=True)
                await git(project.path, "worktree", "add", "--detach", str(path), sha)
                if self.options.get("test_first", True):
                    task.tests_ok, _ = await self.dia._test(project, workspace)
                    if task.tests_ok is False:
                        raise TaskActionError("the tests fail; nothing was built")
                built = []
                for preset in presets:
                    files = await toolchain.build(path, preset, out_root / _slug(preset))
                    built.append(
                        {
                            "preset": preset,
                            "files": [str(f) for f in files],
                            "mb": round(
                                sum(f.stat().st_size for f in files if f.is_file()) / 2**20, 1
                            ),
                        }
                    )
                task.details["builds"] = built
            changelog = await self.changelog(
                project.name, ref=sha, write=write_changelog, version=version
            )
            (out_root / "CHANGELOG.md").write_text(f"# {project.name} {version}\n\n{changelog}\n")
            task.details.update(output=str(out_root), changelog=changelog)
            task.summary = (
                f"{version}: "
                + ", ".join(f"{b['preset']} ({b['mb']} MB)" for b in built)
                + f"\n\n{changelog}"
            )
            task.status = "done"
        except Exception as exc:
            task.status, task.error = "failed", str(exc)[:2000]
        finally:
            task.finished_at = now()
            self.dia.store.save(task)
            await workspace.remove()
        self.dia.audit("build.finish", task.id, task.status)
        await self.dia.emit("build", task, task.summary or task.error or task.status)
        return task
