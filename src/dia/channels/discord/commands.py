"""Slash commands."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

from dia.agents import Mode
from dia.channels.discord.embeds import _cut, task_embed, tasks_embed
from dia.channels.discord.views import plan_message, task_view
from dia.core.orchestrator import TaskActionError

if TYPE_CHECKING:
    from dia.channels.discord.bot import DiaBot

    pass

log = logging.getLogger("dia.discord")


def register_commands(bot: DiaBot) -> None:
    tree, dia = bot.tree, bot.dia

    async def project_choices(_: discord.Interaction, current: str) -> list[app_commands.Choice]:
        names = [n for n in dia.config.projects if current.lower() in n.lower()]
        return [app_commands.Choice(name=n, value=n) for n in names[:25]]

    async def agent_choices(_: discord.Interaction, current: str) -> list[app_commands.Choice]:
        names = [n for n in dia.config.agents if current.lower() in n.lower()]
        return [app_commands.Choice(name=n, value=n) for n in names[:25]]

    @tree.command(name="run", description="Give a task to a coding agent (works on its own branch)")
    @app_commands.describe(
        project="Project to work on",
        prompt="What to do",
        agent="Agent (default: the project's or global default)",
        read_only="Only analyse, change nothing",
        review="Have another agent review the changes (default: per config)",
    )
    @app_commands.autocomplete(project=project_choices, agent=agent_choices)
    async def run_cmd(
        interaction: discord.Interaction,
        project: str,
        prompt: str,
        agent: str | None = None,
        read_only: bool = False,
        review: bool | None = None,
    ) -> None:
        await interaction.response.send_message(f"⏳ **{project}**\n> {_cut(prompt, 300)}")
        mode = Mode.READ_ONLY if read_only else Mode.EDIT
        bot.spawn(bot.run_and_report(interaction, project, prompt, agent, mode, review))

    @tree.command(name="ask", description="Ask a question about a project (read-only)")
    @app_commands.describe(project="Project", question="Your question", agent="Agent")
    @app_commands.autocomplete(project=project_choices, agent=agent_choices)
    async def ask_cmd(
        interaction: discord.Interaction, project: str, question: str, agent: str | None = None
    ) -> None:
        await interaction.response.send_message(f"⏳ **{project}**\n> {_cut(question, 300)}")
        bot.spawn(bot.run_and_report(interaction, project, question, agent, Mode.READ_ONLY))

    async def pipeline_choices(_: discord.Interaction, current: str) -> list[app_commands.Choice]:
        names = [n for n in dia.config.pipelines if current.lower() in n.lower()]
        return [app_commands.Choice(name=n, value=n) for n in names[:25]]

    @tree.command(name="plan", description="Plan work across several agents, then run it")
    @app_commands.describe(
        project="Project", goal="What to achieve", pipeline="A configured pipeline (optional)"
    )
    @app_commands.autocomplete(project=project_choices, pipeline=pipeline_choices)
    async def plan_cmd(
        interaction: discord.Interaction, project: str, goal: str, pipeline: str | None = None
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            plan = await dia.create_plan(project, goal, pipeline=pipeline)
        except (TaskActionError, LookupError) as exc:
            await interaction.followup.send(f"❌ {exc}")
            return
        await interaction.followup.send(**plan_message(plan))

    @tree.command(name="mission", description="Give Dia a goal: it plans, delegates, tests")
    @app_commands.describe(project="Project", goal="What to achieve")
    @app_commands.autocomplete(project=project_choices)
    async def mission_cmd(interaction: discord.Interaction, project: str, goal: str) -> None:
        from dia.work.missions import Missions

        await interaction.response.defer(thinking=True)
        try:
            mission = await Missions(dia).create(project, goal)
        except (TaskActionError, LookupError) as exc:
            await interaction.followup.send(f"❌ {exc}")
            return
        await interaction.followup.send(**plan_message(mission))

    @tree.command(name="launch", description="Start a project, e.g. run the game")
    @app_commands.autocomplete(project=project_choices)
    async def launch_cmd(interaction: discord.Interaction, project: str) -> None:
        try:
            message = await dia.launch(project)
        except (TaskActionError, LookupError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        await interaction.response.send_message(f"🎮 {message}", ephemeral=True)

    @tree.command(name="tasks", description="Recent tasks")
    @app_commands.autocomplete(project=project_choices)
    async def tasks_cmd(interaction: discord.Interaction, project: str | None = None) -> None:
        await interaction.response.send_message(embed=tasks_embed(dia.store.recent(15, project)))

    @tree.command(name="task", description="Show a task, with review buttons")
    async def task_cmd(interaction: discord.Interaction, task_id: str) -> None:
        task = dia.store.get(task_id.strip())
        if not task:
            await interaction.response.send_message(f"No task `{task_id}`.", ephemeral=True)
            return
        kwargs: dict[str, Any] = {"embed": task_embed(task)}
        if view := task_view(task):
            kwargs["view"] = view
        await interaction.response.send_message(**kwargs)

    @tree.command(name="search", description="Search memory notes (what agents would see)")
    async def search_cmd(interaction: discord.Interaction, query: str) -> None:
        if not dia.memory:
            await interaction.response.send_message("Memory is off.", ephemeral=True)
            return
        hits = dia.memory.search(query, limit=5)
        lines = [f"**{h.link}**\n{_cut(h.snippet, 300)}" for h in hits]
        embed = discord.Embed(
            title=_cut(f"🔎 {query}", 256), description="\n\n".join(lines) or "No matching notes."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(name="stop", description="Emergency stop: end every running agent now")
    async def stop_cmd(interaction: discord.Interaction) -> None:
        stopped = await dia.stop_all()
        await interaction.response.send_message(
            f"🛑 Stopped {len(stopped)} process(es). Nothing new starts until `/resume`."
        )

    @tree.command(name="resume", description="Resume after an emergency stop")
    async def resume_cmd(interaction: discord.Interaction) -> None:
        await dia.resume()
        await interaction.response.send_message("▶️ Resumed.")

    @tree.command(name="status", description="Agents, projects and running tasks")
    async def status_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        lines = []
        limited = dia.limit_status()
        for name in dia.config.agents:
            try:
                issue = await dia.config.agent(name).check()
            except Exception as exc:
                issue = str(exc)
            if until := limited.get(name):
                issue = f"usage limit until <t:{int(datetime.fromisoformat(until).timestamp())}:t>"
            lines.append(
                f"{'✅' if not issue else '⚠️'} agent **{name}**{': ' + issue if issue else ''}"
            )
        for project in dia.config.projects.values():
            ok = (project.path / ".git").exists()
            lines.append(f"{'✅' if ok else '⚠️'} project **{project.name}**")
        lines.append(f"🧠 memory: {dia.memory.describe() if dia.memory else 'off'}")
        active = [t for t in dia.store.recent(50) if t.status in ("queued", "running", "waiting")]
        lines.append(f"🔄 active tasks: {len(active)}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
