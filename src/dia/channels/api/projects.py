"""API routes: projects."""

from __future__ import annotations

import asyncio

from aiohttp import web

from dia.channels.api._util import ApiBase, task_json


class ProjectRoutes(ApiBase):
    async def project_changelog(self, request: web.Request) -> web.Response:
        from dia.release.release import Releases

        text = await Releases(self.dia).changelog(
            request.match_info["name"],
            since=request.query.get("since") or None,
            write=request.query.get("write") == "1",
        )
        return web.json_response({"changelog": text})

    async def project_benchmarks(self, request: web.Request) -> web.Response:
        project = self.dia.config.project(request.match_info["name"])
        return web.json_response(
            {
                "command": project.options.get("benchmark"),
                "results": self.dia.store.benchmarks(project.name, limit=50),
            }
        )

    async def project_impact(self, request: web.Request) -> web.Response:
        from dia.quality.impact import impact

        result, text = await impact(
            self.dia, request.match_info["name"], request.query.get("q", ""), False
        )
        return web.json_response({**result.to_dict(), "text": text})

    async def project_debt(self, request: web.Request) -> web.Response:
        from dia.quality import debt

        project = self.dia.config.project(request.match_info["name"]).name
        if request.query.get("refresh") or not debt.saved(self.dia, project):
            items = await debt.register(self.dia, project, bool(request.query.get("deps")))
        else:
            items = debt.saved(self.dia, project)
        return web.json_response({"items": items, "text": debt.describe(items)})

    async def fix_debt(self, request: web.Request) -> web.Response:
        from dia.quality import debt

        project = self.dia.config.project(request.match_info["name"]).name
        number = int(request.match_info["n"])
        if not any(i.get("n") == number for i in debt.saved(self.dia, project)):
            raise ValueError(f"no debt item {number}")
        task = await self._start(lambda on_start: debt.fix(self.dia, project, number, on_start))
        return web.json_response(task_json(task), status=202)

    async def check_contradictions(self, request: web.Request) -> web.Response:
        """An agent compares the project's notes and docs with its code (minutes)."""
        from dia.quality.contradictions import check

        project = self.dia.config.project(request.match_info["name"]).name
        task = await self._start(lambda on_start: check(self.dia, project, on_start=on_start))
        return web.json_response(task_json(task), status=202)

    async def project_balance(self, request: web.Request) -> web.Response:
        from dia.release.balance import analyze, data_folder, describe, read_events

        project = self.dia.config.project(request.match_info["name"])
        folder = data_folder(project.options)
        events, files = (
            await asyncio.to_thread(read_events, folder) if folder and folder.is_dir() else ([], 0)
        )
        result = analyze(events, project.options.get("balance") or {})
        result.sessions = files
        text = describe(result, self.dia.config.language)
        return web.json_response({**result.to_dict(), "text": text})

    async def project_analysis(self, request: web.Request) -> web.Response:
        from dia.release.godot_analysis import analyze, describe

        project = self.dia.config.project(request.match_info["name"])
        result = await asyncio.to_thread(
            analyze, project.path, self.dia.config.section("godot_analysis")
        )
        text = describe(result, self.dia.config.language)
        return web.json_response({**result.to_dict(), "text": text})


def routes(ch: ProjectRoutes) -> list[web.RouteDef]:
    return [
        web.get("/api/projects/{name}/changelog", ch.project_changelog),
        web.get("/api/projects/{name}/analysis", ch.project_analysis),
        web.get("/api/projects/{name}/balance", ch.project_balance),
        web.get("/api/projects/{name}/benchmarks", ch.project_benchmarks),
        web.post("/api/projects/{name}/contradictions", ch.check_contradictions),
        web.get("/api/projects/{name}/impact", ch.project_impact),
        web.get("/api/projects/{name}/debt", ch.project_debt),
        web.post("/api/projects/{name}/debt/{n}/fix", ch.fix_debt),
    ]
