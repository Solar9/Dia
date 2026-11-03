"""API routes: work."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from aiohttp import web

from dia.channels.api._util import TOOLS, ApiBase, read_body, task_json
from dia.skills import enabled_skills
from dia.work.missions import Missions
from dia.work.schedule import Scheduler, Schedules


class WorkRoutes(ApiBase):
    def _schedules(self) -> Schedules:
        return Schedules(self.dia)

    async def list_schedules(self, request: web.Request) -> web.Response:
        schedules = self._schedules()
        upcoming = schedules.next_runs()
        return web.json_response(
            [{**asdict(job), "next": upcoming.get(job.id)} for job in schedules.list()]
        )

    async def add_schedule(self, request: web.Request) -> web.Response:
        job = self._schedules().add(await request.json())
        return web.json_response(asdict(job), status=201)

    async def update_schedule(self, request: web.Request) -> web.Response:
        job = self._schedules().update(request.match_info["id"], await request.json())
        return web.json_response(asdict(job))

    async def remove_schedule(self, request: web.Request) -> web.Response:
        if not self._schedules().remove(request.match_info["id"]):
            raise web.HTTPNotFound(text="no such schedule (config jobs: edit the file)")
        return web.json_response({"message": "removed"})

    async def run_schedule(self, request: web.Request) -> web.Response:
        job = next((j for j in self._schedules().list() if j.id == request.match_info["id"]), None)
        if not job:
            raise web.HTTPNotFound(text="no such schedule")
        self._spawn(Scheduler(self.dia, self.assistant).execute(job))
        return web.json_response({"message": "started"}, status=202)

    async def list_skills(self, request: web.Request) -> web.Response:
        skills = enabled_skills(self.dia)
        return web.json_response(
            [{"name": n, "description": s.description, "args": s.args} for n, s in skills.items()]
        )

    async def run_skill(self, request: web.Request) -> web.Response:
        """A skill's answer; one that needs a yes first answers with its question."""
        from dia.skills import NeedsConfirmation

        skill = enabled_skills(self.dia).get(request.match_info["name"])
        if not skill:
            raise web.HTTPNotFound(text="no such skill")
        body = await read_body(request)
        args = {k: v for k, v in (body.get("args") or {}).items() if k in skill.args and v != ""}
        try:
            return web.json_response({"text": await skill.run(args)})
        except NeedsConfirmation as ask:
            if not body.get("confirm"):
                return web.json_response({"question": ask.question})
            self.dia.audit("skill.confirmed", skill.kind, ask.question)
            return web.json_response({"text": await ask.action()})

    async def run_tool(self, request: web.Request) -> web.Response:
        """One of Dia's CLI commands, ``{"command": "doctor", "args": ["--fix"]}``, with
        what it printed: the app reaches what has no button of its own."""
        import contextlib
        import io

        from dia.cli import build_parser

        body = await request.json()
        command = str(body.get("command", ""))
        if command not in TOOLS:
            raise web.HTTPNotFound(text=f"not available from the app: {command}")
        argv = [command, *(str(a) for a in body.get("args") or [])]
        out = io.StringIO()
        async with self._tool_lock:  # output is captured process-wide: one at a time
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    args = build_parser().parse_args(argv)
                except SystemExit:
                    return web.json_response({"code": 2, "output": out.getvalue()}, status=400)
                self.dia.audit("tool", command, " ".join(argv[1:]))
                try:
                    code = await args.fn(self.dia.config, args)
                except EOFError:  # it wanted to ask on the terminal
                    code = 1
                except Exception as exc:
                    print(f"error: {exc}")
                    code = 1
        return web.json_response({"code": code, "output": out.getvalue()})

    async def list_suggestions(self, request: web.Request) -> web.Response:
        from dia.knowledge.suggestions import Suggestions

        return web.json_response(Suggestions(self.dia).open())

    async def suggestion_action(self, request: web.Request) -> web.Response:
        from dia.knowledge.suggestions import Suggestions

        key, action = request.match_info["key"], request.match_info["action"]
        suggestions = Suggestions(self.dia)
        if action == "dismiss":
            suggestions.dismiss(key)
            return web.json_response({"message": "dismissed"})
        if action != "accept":
            raise web.HTTPNotFound(text=f"unknown action {action}")
        if not any(s["key"] == key for s in suggestions.open()):
            raise ValueError(f"no open suggestion {key}")

        async def run(on_start: Any) -> Any:
            report = await suggestions.accept(key, on_start)
            if report is None:  # nothing to run: it was a reminder
                raise RuntimeError("nothing to run")
            return report

        action_of = next(s for s in suggestions.open() if s["key"] == key).get("action")
        if not action_of:
            suggestions._take(key, "accepted")
            return web.json_response({"message": "noted"})
        task = await self._start(run)
        return web.json_response(task_json(task), status=202)

    async def work_profiles(self, request: web.Request) -> web.Response:
        from dia.work import work

        state = work._state(self.dia)
        return web.json_response(
            {"profiles": work.profiles(self.dia), "current": state.get("current")}
        )

    async def work_action(self, request: web.Request) -> web.Response:
        from dia.work import work

        body = await read_body(request)
        action = request.match_info["action"]
        if action == "start":
            text = await work.start(self.dia, body.get("name", ""), not body.get("no_apps"))
        elif action == "stop":
            text = await work.stop(self.dia, body.get("name") or None, body.get("note", ""))
        else:
            raise web.HTTPNotFound(text=f"unknown action {action}")
        return web.json_response({"text": text})

    async def list_goals(self, request: web.Request) -> web.Response:
        from dia.work import goals

        found = goals.goals(self.dia, active=False)
        return web.json_response(
            [{**task_json(g), "blockers": goals.blockers(self.dia, g)} for g in found]
        )

    async def create_goal(self, request: web.Request) -> web.Response:
        from dia.work import goals

        body = await request.json()
        weeks = int(body["weeks"]) if body.get("weeks") else None
        goal = await goals.create(self.dia, body["project"], body["goal"], weeks)
        return web.json_response(task_json(goal), status=201)

    async def goal_action(self, request: web.Request) -> web.Response:
        from dia.work import goals

        goal_id, action = request.match_info["id"], request.match_info["action"]
        if action == "review":
            return web.json_response(await goals.review(self.dia, goal_id))
        if action == "approve":
            mission = await goals.approve(self.dia, goal_id)
            return web.json_response({"mission": task_json(mission) if mission else None})
        if action == "close":
            goals.close(self.dia, goal_id)
            return web.json_response({"message": "closed"})
        raise web.HTTPNotFound(text=f"unknown action {action}")

    async def list_missions(self, request: web.Request) -> web.Response:
        missions = Missions(self.dia)
        return web.json_response(
            [
                {**task_json(t), "budget": missions.budget(t)}
                for t in self.dia.store.recent(200)
                if t.mode == "mission"
            ]
        )

    async def create_mission(self, request: web.Request) -> web.Response:
        body = await request.json()
        budget = {k: float(body[k]) for k in ("calls", "minutes") if body.get(k)}
        mission = await Missions(self.dia).create(
            body["project"], body["goal"], budget=budget, priority=body.get("priority", "normal")
        )
        return web.json_response(task_json(mission), status=201)

    async def cancel_mission(self, request: web.Request) -> web.Response:
        Missions(self.dia).cancel(request.match_info["id"])
        return web.json_response({"message": "no further steps will start"})


def routes(ch: WorkRoutes) -> list[web.RouteDef]:
    return [
        web.get("/api/suggestions", ch.list_suggestions),
        web.post("/api/suggestions/{key}/{action}", ch.suggestion_action),
        web.get("/api/work", ch.work_profiles),
        web.post("/api/work/{action}", ch.work_action),
        web.get("/api/goals", ch.list_goals),
        web.post("/api/goals", ch.create_goal),
        web.post("/api/goals/{id}/{action}", ch.goal_action),
        web.get("/api/missions", ch.list_missions),
        web.post("/api/missions", ch.create_mission),
        web.post("/api/missions/{id}/cancel", ch.cancel_mission),
        web.get("/api/schedules", ch.list_schedules),
        web.post("/api/schedules", ch.add_schedule),
        web.patch("/api/schedules/{id}", ch.update_schedule),
        web.delete("/api/schedules/{id}", ch.remove_schedule),
        web.post("/api/schedules/{id}/run", ch.run_schedule),
        web.get("/api/skills", ch.list_skills),
        web.post("/api/skills/{name}", ch.run_skill),
        web.post("/api/tools", ch.run_tool),
    ]
