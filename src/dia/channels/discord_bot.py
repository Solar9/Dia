"""Discord channel: slash commands, task notifications and approval buttons.

Setup (once): create an application at https://discord.com/developers,
add a bot, copy its token into the ``DIA_DISCORD_TOKEN`` environment
variable, and invite it with the ``bot`` and ``applications.commands``
scopes. No privileged intents are needed: Dia only uses slash commands.

Besides slash commands, a direct message or an @mention is read by Dia's
brain (``[dia] brain``), e.g. "@Dia what does the save system in nova do?".

Only the user ids listed in ``allowed_users`` can use the bot; everyone
else is refused, including on buttons.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

from dia.agents import Mode
from dia.assistant import Assistant
from dia.audit import ACTOR
from dia.channels import Channel
from dia.learn import MAX_FACTS
from dia.orchestrator import Event, TaskActionError, TaskReport
from dia.store import TaskRecord

if TYPE_CHECKING:
    from dia.orchestrator import Orchestrator

log = logging.getLogger("dia.discord")

STATUS_ICON = {
    "planned": "📋",
    "queued": "⏳",
    "running": "🔄",
    "done": "✅",
    "failed": "❌",
    "merged": "🔀",
    "discarded": "🗑️",
    "published": "🚀",
}
COLOR = {"done": 0x2E9E5B, "failed": 0xC93C37, "merged": 0x6E56CF}
TESTS = {None: "not run", True: "passed", False: "FAILED"}
REVIEW_ICON = {"approved": "✅", "changes_requested": "✏️", "unclear": "❔"}


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 2].rstrip() + " …"


def _location(comment: dict[str, Any]) -> str:
    """ " (file:line)" for an inline review comment, "" otherwise."""
    if not comment.get("path"):
        return ""
    line = f":{comment['line']}" if comment.get("line") else ""
    return f" ({comment['path']}{line})"


def _title(task: TaskRecord) -> str:
    return _cut(task.prompt.splitlines()[0], 80)


# ---------------------------------------------------------------- render ---


def task_embed(task: TaskRecord, report: TaskReport | None = None) -> discord.Embed:
    icon = STATUS_ICON.get(task.status, "•")
    embed = discord.Embed(
        title=_cut(f"{icon} {task.project} · {_title(task)}", 256),
        description=_cut(task.summary or "", 3500) or None,
        color=COLOR.get(task.status, 0x808080),
    )
    embed.add_field(name="Status", value=task.status)
    embed.add_field(name="Agent", value=task.agent)
    embed.add_field(name="Mode", value=str(task.mode))
    if task.mode == Mode.EDIT:
        embed.add_field(name="Tests", value=TESTS[task.tests_ok])
    if task.branch and task.commit_sha:
        embed.add_field(
            name="Branch", value=f"`{task.branch}` @ `{task.commit_sha[:10]}`", inline=False
        )
    if report and report.diff_stat:
        embed.add_field(name="Changes", value=f"```{_cut(report.diff_stat, 1000)}```", inline=False)
    if report and task.tests_ok is False and report.test_output:
        embed.add_field(
            name="Test output",
            value=f"```{_cut(report.test_output[-1000:], 1000)}```",
            inline=False,
        )
    if reviews := task.details.get("reviews"):
        last = reviews[-1]
        icon = REVIEW_ICON.get(last["verdict"], "🔍")
        text = f"{icon} {last['verdict'].replace('_', ' ')} by {last['reviewer']}"
        if len(reviews) > 1:
            text += f" (after {len(reviews) - 1} fix round(s))"
        if last["verdict"] != "approved":
            text += "\n" + _cut(last["findings"], 700)
        embed.add_field(name="Review", value=_cut(text, 1000), inline=False)
    if task.error:
        embed.add_field(name="Error", value=_cut(task.error, 1000), inline=False)
    if report and report.warnings:
        embed.add_field(
            name="Warnings",
            value=_cut("\n".join(f"• {w}" for w in report.warnings), 1000),
            inline=False,
        )
    embed.set_footer(text=f"task {task.id}")
    return embed


def task_view(task: TaskRecord) -> discord.ui.View | None:
    """Review buttons for a task whose branch is still waiting for a decision."""
    if not task.commit_sha or task.status not in ("done", "failed"):
        return None
    view = discord.ui.View(timeout=None)
    view.add_item(TaskButton("diff", task.id))
    view.add_item(TaskButton("review", task.id))
    view.add_item(TaskButton("merge", task.id, disabled=task.status != "done"))
    view.add_item(TaskButton("publish", task.id, disabled=task.status != "done"))
    view.add_item(TaskButton("discard", task.id))
    return view


def plan_embed(task: TaskRecord) -> discord.Embed:
    lines = [
        f"**{i}. {step.get('title') or step['agent']}** · {step['agent']}\n"
        f"> {_cut(step['prompt'], 250)}"
        for i, step in enumerate(task.details.get("plan", []), 1)
    ]
    embed = discord.Embed(
        title=_cut(f"📋 {task.project} · {_title(task)}", 256),
        description=_cut("\n".join(lines), 4000),
    )
    if task.mode == "mission":
        embed.set_footer(text=f"mission {task.id} · independent steps run in parallel")
    else:
        embed.set_footer(text=f"plan {task.id} · runs on one branch, step by step")
    return embed


def plan_message(task: TaskRecord) -> dict[str, Any]:
    """Embed, Run button and, when steps don't fit the embed, the full plan as a file."""
    kwargs: dict[str, Any] = {"embed": plan_embed(task), "view": plan_view(task)}
    steps = task.details.get("plan", [])
    if any(len(step["prompt"]) > 250 for step in steps):
        text = f"# {task.prompt}\n\n" + "\n\n".join(
            f"## {i}. {s.get('title') or s['agent']} ({s['agent']})\n\n{s['prompt']}"
            for i, s in enumerate(steps, 1)
        )
        kwargs["file"] = discord.File(io.BytesIO(text.encode()), f"plan-{task.id}.md")
    return kwargs


def plan_view(task: TaskRecord) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(TaskButton("runplan", task.id))
    return view


def tasks_embed(tasks: list[TaskRecord]) -> discord.Embed:
    lines = [
        f"{STATUS_ICON.get(t.status, '•')} `{t.id}` **{t.project}** · {t.agent} · "
        f"{_cut(_title(t), 50)}"
        for t in tasks
    ]
    return discord.Embed(title="Recent tasks", description="\n".join(lines) or "No tasks yet.")


# --------------------------------------------------------------- buttons ---

BUTTONS = {
    "diff": ("Diff", discord.ButtonStyle.secondary, "📄"),
    "review": ("Review", discord.ButtonStyle.secondary, "🔍"),
    "merge": ("Merge", discord.ButtonStyle.success, "🔀"),
    "publish": ("PR / MR", discord.ButtonStyle.primary, "🚀"),
    "discard": ("Discard", discord.ButtonStyle.danger, "🗑️"),
    "fixci": ("Fix CI", discord.ButtonStyle.primary, "🛠️"),
    "fixreview": ("Address comments", discord.ButtonStyle.primary, "💬"),
    "runplan": ("Run plan", discord.ButtonStyle.success, "▶️"),
    "learnyes": ("Remember", discord.ButtonStyle.success, "🧠"),
    "learnno": ("Skip", discord.ButtonStyle.secondary, "✖️"),
    "fixbuild": ("Fix", discord.ButtonStyle.primary, "🛠️"),
}


class TaskButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"dia:(?P<action>diff|review|merge|publish|discard|fixci|fixreview|runplan"
        r"|learnyes|learnno|fixbuild):(?P<task>[0-9a-f-]+)"
    ),
):
    """A review button. Its state lives in the custom id, so it survives bot restarts."""

    def __init__(self, action: str, task_id: str, disabled: bool = False) -> None:
        label, style, emoji = BUTTONS[action]
        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=f"dia:{action}:{task_id}",
                disabled=disabled,
            )
        )
        self.action = action
        self.task_id = task_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Button, match: Any
    ) -> TaskButton:
        return cls(match["action"], match["task"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _authorize(interaction)

    async def callback(self, interaction: discord.Interaction) -> None:
        dia: Orchestrator = interaction.client.dia  # type: ignore[attr-defined]
        if self.action == "diff":
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                diff = await dia.task_diff(self.task_id)
            except TaskActionError as exc:
                await interaction.followup.send(f"❌ {exc}", ephemeral=True)
                return
            if len(diff) < 1900:
                await interaction.followup.send(f"```diff\n{diff}\n```", ephemeral=True)
            else:
                file = discord.File(io.BytesIO(diff.encode()), filename=f"{self.task_id}.diff")
                await interaction.followup.send(file=file, ephemeral=True)
            return

        if self.action == "runplan":
            bot: DiaBot = interaction.client  # type: ignore[assignment]
            task = dia.store.get(self.task_id)
            if not task or task.status != "planned":
                await interaction.response.send_message("This plan was already started.")
                return
            await interaction.response.edit_message(view=None)
            status = await interaction.followup.send(f"▶️ Starting plan `{task.id}`", wait=True)
            bot.spawn(
                bot.report_task(
                    status,
                    interaction.user.mention,
                    task.project,
                    task.prompt,
                    None,
                    Mode.EDIT,
                    fallback=interaction.followup.send,
                    plan_id=task.id,
                )
            )
            return

        if self.action in ("learnyes", "learnno"):
            try:
                if self.action == "learnyes":
                    stored = dia.decide_facts(self.task_id)
                    outcome = f"🧠 Remembered {len(stored)} fact(s)."
                else:
                    dia.decide_facts(self.task_id, accept=[], reject=list(range(MAX_FACTS)))
                    outcome = "✖️ Skipped."
            except TaskActionError as exc:
                outcome = f"❌ {exc}"
            await interaction.response.edit_message(view=None)
            await interaction.followup.send(outcome)
            return

        if self.action == "fixbuild":
            await interaction.response.defer(thinking=True)
            try:
                report = await dia.fix_build(self.task_id)
            except TaskActionError as exc:
                await interaction.followup.send(f"❌ {exc}")
                return
            fixed: dict[str, Any] = {"embed": task_embed(report.task, report)}
            if view := task_view(report.task):
                fixed["view"] = view
            await interaction.followup.send(**fixed)
            return

        if self.action == "fixreview":
            await interaction.response.defer(thinking=True)
            try:
                await dia.address_comments(self.task_id)
            except TaskActionError as exc:
                await interaction.followup.send(f"❌ {exc}")
                return
            await interaction.followup.send(
                f"💬 Changes for the comments on `{self.task_id}` pushed; the PR/MR is updated."
            )
            return

        if self.action == "fixci":
            await interaction.response.defer(thinking=True)
            try:
                await dia.fix_ci(self.task_id)
            except TaskActionError as exc:
                await interaction.followup.send(f"❌ {exc}")
                return
            await interaction.followup.send(f"🛠️ Fix for `{self.task_id}` pushed; CI runs again.")
            return

        if self.action == "review":
            await interaction.response.defer(thinking=True)
            try:
                report = await dia.review_task(self.task_id)
            except TaskActionError as exc:
                await interaction.followup.send(f"❌ {exc}")
                return
            kwargs: dict[str, Any] = {"embed": task_embed(report.task, report)}
            if view := task_view(report.task):
                kwargs["view"] = view
            await interaction.followup.send(**kwargs)
            return

        # merge / publish / discard: the click is the user's approval.
        await interaction.response.defer()
        try:
            if self.action == "merge":
                sha = await dia.merge_task(self.task_id)
                outcome = f"🔀 Merged task `{self.task_id}` (`{sha[:10]}`)."
            elif self.action == "publish":
                publication = await dia.publish_task(self.task_id)
                outcome = f"🚀 Task `{self.task_id}`: {publication.message}"
            else:
                await dia.discard_task(self.task_id)
                outcome = f"🗑️ Discarded task `{self.task_id}` and its branch."
        except TaskActionError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return
        if task := dia.store.get(self.task_id):
            await interaction.edit_original_response(embed=task_embed(task), view=None)
        await interaction.followup.send(outcome)


# ------------------------------------------------------------------- bot ---


async def _authorize(interaction: discord.Interaction) -> bool:
    allowed: set[int] = interaction.client.allowed_users  # type: ignore[attr-defined]
    if interaction.user.id in allowed:
        ACTOR.set(f"discord:{getattr(interaction.user, 'name', interaction.user.id)}")
        return True
    log.warning("refused %s (%s)", interaction.user, interaction.user.id)
    if not interaction.response.is_done():
        await interaction.response.send_message("You are not allowed to use Dia.", ephemeral=True)
    return False


class DiaTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _authorize(interaction)

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            return
        log.exception("command failed", exc_info=error)
        message = f"❌ {getattr(error, 'original', error)}"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class DiaBot(discord.Client):
    def __init__(self, channel: DiscordChannel) -> None:
        # Default intents suffice: DMs and @mentions carry their text without
        # the privileged message-content intent.
        super().__init__(intents=discord.Intents.default())
        self.dia = channel.dia
        self.allowed_users = channel.allowed_users
        self.guild_id = channel.guild_id
        self.notify_channel_id = channel.notify_channel_id
        self.tree = DiaTree(self)
        self.assistant = Assistant(channel.dia)
        self.assistant.surface = "discord"
        self._background: set[asyncio.Task] = set()
        register_commands(self)

    async def setup_hook(self) -> None:
        self.add_dynamic_items(TaskButton)
        self.dia.listeners.append(self.on_dia_event)
        if self.guild_id:
            # Guild commands appear instantly; global ones (usable in DMs) can lag.
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_dia_event(self, event: Event) -> None:
        """Background news (CI results, review comments): to the notify channel, or a DM
        to each user."""
        if event.kind == "learn" and event.task:
            facts = "\n".join(f"• {fact}" for fact in event.message.splitlines())
            view = discord.ui.View(timeout=None)
            view.add_item(TaskButton("learnyes", event.task.id))
            view.add_item(TaskButton("learnno", event.task.id))
            await self._notify(
                {
                    "content": _cut(
                        f"🧠 Worth remembering about **{event.task.project}**?\n{facts}", 1900
                    ),
                    "view": view,
                }
            )
            return
        if event.kind == "watch" and event.task:
            check = event.task
            watch = check.details.get("watch", {})
            icon = "✅" if event.message == "fixed" else "❌"
            lines = [
                f"{icon} Build · **{check.project}** · `{watch.get('sha', '')[:10]}` "
                f"{watch.get('subject', '')} ({watch.get('author', '?')}): {event.message}"
            ]
            if tail := check.details.get("test_tail"):
                lines.append(f"```\n{_cut(tail[-800:], 800)}\n```")
            kwargs: dict[str, Any] = {"content": _cut("\n".join(lines), 1900)}
            if event.message != "fixed":
                view = discord.ui.View(timeout=None)
                view.add_item(TaskButton("fixbuild", check.id))
                kwargs["view"] = view
            await self._notify(kwargs)
            return
        if event.kind == "issue" and event.task:
            issue = event.task.details.get("issue", {})
            view = discord.ui.View(timeout=None)
            view.add_item(TaskButton("runplan", event.task.id))
            text = f"📥 Issue · **{event.task.project}**: {event.message}"
            if issue.get("url"):
                text += f"\n{issue['url']}"
            await self._notify({"content": _cut(text, 1900), "view": view})
            return
        if event.kind == "build" and event.task:
            icon = "📦" if event.task.status == "done" else "❌"
            text = f"{icon} Build · **{event.task.project}**: {event.message}"
            await self._notify({"content": _cut(text, 1900)})
            return
        if event.kind == "system":
            await self._notify({"content": f"🖥️ {event.message}"})
            return
        if event.kind == "schedule":
            job = event.data.get("job", {})
            title = job.get("name") or job.get("text") or job.get("skill") or "schedule"
            await self._notify({"content": _cut(f"⏰ **{title}**\n{event.message}", 1900)})
            return
        if event.kind == "limit":
            where = f" · **{event.task.project}** · `{event.task.id}`" if event.task else ""
            await self._notify({"content": f"⏳ Limit{where}: {event.message}"})
            return
        if event.kind not in ("ci", "review") or event.task is None:
            return
        task = event.task
        ci = task.details.get("ci", {})
        pr_url = task.details.get("published", {}).get("url")
        view = discord.ui.View(timeout=None)
        if event.kind == "review":
            lines = [f"💬 Review · **{task.project}** · `{task.id}`: {event.message}"]
            if pr_url:
                lines.append(pr_url)
            pending = task.details.get("comments_pending", [])
            for c in pending[:5]:
                body = _cut(" ".join(c["body"].split()), 200)
                lines.append(f"> **{c['author']}**{_location(c)}: {body}")
            if pending:
                view.add_item(TaskButton("fixreview", task.id))
        else:
            icon = {"success": "✅", "failed": "❌"}.get(event.message, "🔔")
            lines = [f"{icon} CI · **{task.project}** · `{task.id}`: {event.message}"]
            if url := ci.get("url") or pr_url:
                lines.append(url)
            lines += [f"• {job.get('name')}" for job in ci.get("failed", [])[:5]]
            if event.message == "failed":
                view.add_item(TaskButton("fixci", task.id))
        kwargs: dict[str, Any] = {"content": _cut("\n".join(lines), 1900)}
        if view.children:
            kwargs["view"] = view
        await self._notify(kwargs)

    async def _notify(self, kwargs: dict[str, Any]) -> None:
        """Send to the notify channel, or a DM to each allowed user."""
        targets: list[Any] = []
        if self.notify_channel_id:
            targets.append(self.get_channel(self.notify_channel_id))
        else:
            for user_id in self.allowed_users:
                try:
                    targets.append(await self.fetch_user(user_id))
                except discord.HTTPException:
                    log.warning("cannot reach user %s", user_id)
        for target in filter(None, targets):
            await target.send(**kwargs)

    async def on_ready(self) -> None:
        log.info("Discord: logged in as %s", self.user)

    def spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def run_and_report(
        self,
        interaction: discord.Interaction,
        project: str,
        prompt: str,
        agent: str | None,
        mode: Mode,
        review: bool | None = None,
    ) -> None:
        """Slash-command flavour of :meth:`report_task`."""
        await self.report_task(
            await interaction.original_response(),
            interaction.user.mention,
            project,
            prompt,
            agent,
            mode,
            fallback=interaction.followup.send,
            review=review,
        )

    async def report_task(
        self,
        status: discord.Message,
        mention: str,
        project: str,
        prompt: str,
        agent: str | None,
        mode: Mode,
        fallback: Callable[..., Awaitable[Any]] | None = None,
        review: bool | None = None,
        plan_id: str | None = None,
    ) -> None:
        """Run a task (or the stored plan ``plan_id``), keep ``status`` updated, and reply
        with the result, pinging the user."""

        async def on_start(task: TaskRecord) -> None:
            note = " (queued: waiting for a running task)" if self.dia.busy else ""
            await status.edit(
                content=f"{STATUS_ICON['running']} `{task.id}` · **{project}** · "
                f"{task.agent}{note}\n> {_cut(prompt, 300)}"
            )

        send = fallback or status.channel.send
        try:
            if plan_id:
                report = await self.dia.run_plan(plan_id, on_start=on_start, review=review)
            else:
                report = await self.dia.run_task(
                    project, prompt, agent, mode, on_start=on_start, review=review
                )
        except Exception as exc:  # e.g. unknown project/agent
            await send(f"❌ {exc}")
            return
        task = report.task
        kwargs: dict[str, Any] = {"embed": task_embed(task, report)}
        if view := task_view(task):
            kwargs["view"] = view
        if task.summary and len(task.summary) > 3500:
            kwargs["file"] = discord.File(io.BytesIO(task.summary.encode()), f"{task.id}.md")
        content = f"{mention} {STATUS_ICON.get(task.status, '')} task finished"
        try:
            await status.reply(content, **kwargs)
        except discord.HTTPException:
            # e.g. no permission to post in this channel: the interaction webhook still works
            await send(content, **kwargs)

    async def on_message(self, message: discord.Message) -> None:
        """Free-form requests in DMs or when the bot is @mentioned, read by the brain."""
        if message.author.bot or message.author.id not in self.allowed_users:
            return
        if message.guild and (not self.user or self.user not in message.mentions):
            return
        ACTOR.set(f"discord:{getattr(message.author, 'name', message.author.id)}")
        text = message.content
        if self.user:
            text = re.sub(rf"<@!?{self.user.id}>", "", text)
        text = text.strip()
        if not text:
            return
        async with message.channel.typing():
            intent = await self.assistant.interpret(text, conversation=str(message.author.id))
        if intent.action in ("plan", "mission"):
            async with message.channel.typing():
                try:
                    if intent.action == "mission":
                        from dia.missions import Missions

                        plan = await Missions(self.dia).create(intent.project, intent.prompt)
                    else:
                        plan = await self.dia.create_plan(intent.project, intent.prompt)
                except TaskActionError as exc:
                    await message.reply(f"❌ {exc}")
                    return
            self.assistant.remember_turn(intent.conversation, text, f"prepared {plan.id}")
            await message.reply(**plan_message(plan))
            return
        if intent.action in ("run", "ask"):
            mode = Mode.EDIT if intent.action == "run" else Mode.READ_ONLY
            header = intent.reply or f"⏳ **{intent.project}**"
            status = await message.reply(f"{header}\n> {_cut(intent.prompt or text, 300)}")
            self.assistant.remember_turn(
                intent.conversation, text, f"started a task on {intent.project}"
            )
            self.spawn(
                self.report_task(
                    status,
                    message.author.mention,
                    intent.project,
                    intent.prompt,
                    intent.agent,
                    mode,
                )
            )
            return
        response = await self.assistant.execute(intent)
        await message.reply(_cut(response.text or "…", 1900))


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
        from dia.missions import Missions

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


class DiscordChannel(Channel):
    kind = "discord"

    def __init__(self, name: str, options: dict[str, Any], dia: Orchestrator) -> None:
        super().__init__(name, options, dia)
        users = options.get("allowed_users") or []
        if not users:
            raise ValueError(
                "'allowed_users' (your Discord user id) is required: Dia runs agents on "
                "your machine, so nobody else may command it"
            )
        self.allowed_users = {int(u) for u in users}
        self.guild_id = int(options["guild_id"]) if options.get("guild_id") else None
        # Where background news (CI results) goes; default: a DM to each allowed user.
        notify = options.get("notify_channel_id")
        self.notify_channel_id = int(notify) if notify else None
        self.token_env = options.get("token_env", "DIA_DISCORD_TOKEN")

    @property
    def token(self) -> str | None:
        return self.options.get("token") or os.environ.get(self.token_env)

    def check(self) -> str | None:
        if not self.token:
            return f"no bot token: set the {self.token_env} environment variable"
        return None

    async def run(self) -> None:
        if problem := self.check():
            raise RuntimeError(problem)
        bot = DiaBot(self)
        try:
            async with bot:
                await bot.start(self.token)
        except discord.LoginFailure:
            raise RuntimeError("Discord rejected the bot token (check DIA_DISCORD_TOKEN)") from None
        except OSError as exc:  # DNS, TLS, refused connections (aiohttp errors are OSErrors)
            raise RuntimeError(f"cannot reach Discord: {exc}") from None
