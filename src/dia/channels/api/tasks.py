"""API routes: tasks."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from dia.agents import Mode
from dia.channels.api._util import ApiBase, read_body, task_json
from dia.core.store import TaskRecord


class TaskRoutes(ApiBase):
    async def create_council(self, request: web.Request) -> web.Response:
        from dia.knowledge.council import convene

        body = await request.json()
        self._spawn(
            self._report_errors(
                "council",
                convene(
                    self.dia,
                    body["question"],
                    body.get("project") or None,
                    body.get("members") or None,
                ),
            )
        )
        return web.json_response({"message": "the council is meeting"}, status=202)

    async def create_research(self, request: web.Request) -> web.Response:
        """A web research report on a topic (minutes): the task appears at once."""
        from dia.knowledge.research import research

        body = await request.json()
        task = await self._start(
            lambda on_start: research(
                self.dia, body["topic"], body.get("project") or None, body.get("agent"), on_start
            )
        )
        return web.json_response(task_json(task), status=202)

    async def create_experiment(self, request: web.Request) -> web.Response:
        """The same change several ways (agents or approaches), each measured."""
        from dia.quality.experiments import plan_variants, run_experiment

        body = await request.json()
        agents = body.get("agents") or None
        approaches = body.get("approaches") or None
        plan_variants(self.dia, agents, approaches)  # a bad request fails here, not later
        task = await self._start(
            lambda on_start: run_experiment(
                self.dia, body["project"], body["question"], agents, approaches, on_start
            )
        )
        return web.json_response(task_json(task), status=202)

    async def create_debug(self, request: web.Request) -> web.Response:
        """A bug for the debugging swarm: hypotheses, each checked by a test."""
        from dia.work.swarm import debug

        body = await request.json()
        project = self.dia.config.project(body["project"]).name
        task = await self._start(
            lambda on_start: debug(
                self.dia, project, body["bug"], body.get("agents") or None, on_start
            )
        )
        return web.json_response(task_json(task), status=202)

    async def create_scenario(self, request: web.Request) -> web.Response:
        """ "Does parry work?": an agent writes a test for it, Dia runs it."""
        from dia.quality.scenario import check_scenario

        body = await request.json()
        task = await self._start(
            lambda on_start: check_scenario(
                self.dia, body["project"], body["scenario"], body.get("agent"), on_start
            )
        )
        return web.json_response(task_json(task), status=202)

    async def create_build(self, request: web.Request) -> web.Response:
        from dia.release.release import Releases

        body = await request.json()
        presets = body.get("presets") or None
        self._spawn(
            self._report_errors(
                "build",
                Releases(self.dia).build(
                    body["project"],
                    presets,
                    body.get("ref"),
                    body.get("version"),
                    write_changelog=bool(body.get("write_changelog")),
                ),
            )
        )
        return web.json_response({"message": "build started"}, status=202)

    async def tasks(self, request: web.Request) -> web.Response:
        limit = int(request.query.get("limit", 50))
        tasks = self.dia.store.recent(limit, request.query.get("project") or None)
        stats = await asyncio.gather(*(self._diff_stat(t) for t in tasks))
        return web.json_response(
            [{**task_json(t), "diffstat": d} for t, d in zip(tasks, stats, strict=True)]
        )

    async def _diff_stat(self, task: TaskRecord) -> dict[str, int] | None:
        """+/- lines of a task waiting for a decision; kept per commit, a branch never changes."""
        if task.status not in ("done", "failed", "published") or not task.commit_sha:
            return None
        key = (task.id, task.commit_sha)
        if key not in self._diff_stats:
            self._diff_stats[key] = await self.dia.diff_stat(task)
        return self._diff_stats[key]

    def _get(self, request: web.Request) -> TaskRecord:
        task = self.dia.store.get(request.match_info["id"])
        if not task:
            raise web.HTTPNotFound(text="no such task")
        return task

    async def task(self, request: web.Request) -> web.Response:
        task = self._get(request)
        data = task_json(task)
        data["has_test_log"] = self.dia.test_log_path(task.id).exists()
        data["diffstat"] = await self._diff_stat(task)
        return web.json_response(data)

    async def diff(self, request: web.Request) -> web.Response:
        return web.Response(text=await self.dia.task_diff(self._get(request).id))

    async def tests(self, request: web.Request) -> web.Response:
        path = self.dia.test_log_path(self._get(request).id)
        if not path.exists():
            raise web.HTTPNotFound(text="no test log for this task")
        return web.Response(text=path.read_text())

    async def create_task(self, request: web.Request) -> web.Response:
        body = await request.json()
        mode = Mode.READ_ONLY if body.get("mode") == "read-only" else Mode.EDIT
        task = await self._start(
            lambda on_start: self.dia.run_task(
                body["project"],
                body["prompt"],
                body.get("agent") or None,
                mode,
                on_start=on_start,
                review=body.get("review"),
                model=body.get("model") or None,
            )
        )
        return web.json_response(task_json(task), status=201)

    async def create_plan(self, request: web.Request) -> web.Response:
        body = await request.json()
        plan = await self.dia.create_plan(
            body["project"],
            body["goal"],
            pipeline=body.get("pipeline") or None,
            planner=body.get("planner") or None,
        )
        return web.json_response(task_json(plan), status=201)

    async def task_action(self, request: web.Request) -> web.Response:
        task = self._get(request)
        action = request.match_info["action"]
        body = await read_body(request)
        reason = (body.get("reason") or None) if isinstance(body, dict) else None
        handler = ACTIONS.get(action)
        if handler is None:
            raise web.HTTPNotFound(text=f"unknown action {action}")
        return await handler(self, task, body, reason)

    async def _report_errors(self, task_id: str, coro: Any) -> None:
        try:
            await coro
        except Exception as exc:
            await self._broadcast({"type": "error", "task_id": task_id, "message": str(exc)})


# --- POST /api/tasks/{id}/{action}: each handler gets (channel, task, body, reason) ---


async def _merge(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    override = (body.get("override") or None) if isinstance(body, dict) else None
    sha = await ch.dia.merge_task(task.id, reason, override)
    return web.json_response({"message": f"merged as {sha[:10]}"})


async def _discard(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    await ch.dia.discard_task(task.id, reason)
    return web.json_response({"message": "discarded"})


async def _publish(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    publication = await ch.dia.publish_task(task.id)
    return web.json_response({"message": publication.message, "url": publication.url})


async def _publish_itch(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    from dia.release.release import Releases

    pushed = await Releases(ch.dia).publish_itch(task.id)
    return web.json_response({"message": "published: " + ", ".join(pushed)})


async def _publish_steam(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    from dia.release.release import Releases

    target = await Releases(ch.dia).publish_steam(task.id)
    return web.json_response({"message": f"published: {target}"})


def _announce(ch: Any, task: TaskRecord) -> None:
    ch._spawn(ch._broadcast({"type": "task", "task": task_json(ch.dia.store.get(task.id))}))


async def _learn(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    stored = ch.dia.decide_facts(task.id, body.get("accept"), body.get("reject"))
    _announce(ch, task)
    return web.json_response({"message": f"remembered {len(stored)}", "stored": stored})


async def _rollback(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    # prepared as a new task; merging it stays a click
    revert = await ch.dia.rollback_task(task.id, reason)
    return web.json_response(task_json(revert), status=201)


async def _howto(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    # propose how this task was done, as a how-to
    howto = await ch.dia.propose_howto(task.id)
    _announce(ch, task)
    return web.json_response({"howto": howto})


async def _howto_accept(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    path = ch.dia.accept_howto(task.id, body)
    _announce(ch, task)
    return web.json_response({"message": f"saved {path}", "path": path})


async def _fix_build(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    started = await ch._start(lambda on_start: ch.dia.fix_build(task.id, on_start))
    return web.json_response(task_json(started), status=202)


async def _fix_bug(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    # the confirmed cause of a debugging task
    from dia.work.swarm import fix

    started = await ch._start(lambda on_start: fix(ch.dia, task.id, on_start))
    return web.json_response(task_json(started), status=202)


async def _run_plan(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
    started = await ch._start(lambda on_start: ch.dia.run_plan(task.id, on_start))
    return web.json_response(task_json(started), status=202)


def _background(name: str, method: str) -> Any:
    """An action that runs for minutes: answer 202, report failures over the WebSocket."""

    async def handler(ch: Any, task: TaskRecord, body: Any, reason: str | None) -> web.Response:
        ch._spawn(ch._report_errors(task.id, getattr(ch.dia, method)(task.id)))
        return web.json_response({"message": f"{name} started"}, status=202)

    return handler


ACTIONS: dict[str, Any] = {
    "merge": _merge,
    "discard": _discard,
    "publish": _publish,
    "publish-itch": _publish_itch,
    "publish-steam": _publish_steam,
    "learn": _learn,
    "rollback": _rollback,
    "howto": _howto,
    "howto-accept": _howto_accept,
    "fix-build": _fix_build,
    "fix-bug": _fix_bug,
    "run-plan": _run_plan,
    "review": _background("review", "review_task"),
    "fix-ci": _background("fix-ci", "fix_ci"),
    "address-comments": _background("address-comments", "address_comments"),
}


def routes(ch: TaskRoutes) -> list[web.RouteDef]:
    return [
        web.get("/api/tasks", ch.tasks),
        web.post("/api/tasks", ch.create_task),
        web.get("/api/tasks/{id}", ch.task),
        web.get("/api/tasks/{id}/diff", ch.diff),
        web.get("/api/tasks/{id}/tests", ch.tests),
        web.post("/api/tasks/{id}/{action}", ch.task_action),
        web.post("/api/plans", ch.create_plan),
        web.post("/api/builds", ch.create_build),
        web.post("/api/council", ch.create_council),
        web.post("/api/scenarios", ch.create_scenario),
        web.post("/api/research", ch.create_research),
        web.post("/api/experiments", ch.create_experiment),
        web.post("/api/debug", ch.create_debug),
    ]
