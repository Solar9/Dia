"""The Discord client and the channel that runs it."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

from dia.agents import Mode
from dia.assistant import Assistant
from dia.audit import ACTOR
from dia.channels import Channel
from dia.channels.discord.commands import register_commands
from dia.channels.discord.embeds import STATUS_ICON, _cut, _location, task_embed
from dia.channels.discord.views import TaskButton, _authorize, plan_message, task_view
from dia.core.orchestrator import Event, TaskActionError
from dia.core.store import TaskRecord

if TYPE_CHECKING:
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia.discord")


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
                        from dia.work.missions import Missions

                        plan = await Missions(self.dia).create(intent.project, intent.prompt)
                    else:
                        plan = await self.dia.create_plan(intent.project, intent.prompt)
                except TaskActionError as exc:
                    await message.reply(f"❌ {exc}")
                    return
            self.assistant.remember_turn(intent.conversation, text, f"prepared {plan.id}")
            await message.reply(self.assistant.understood(intent) or None, **plan_message(plan))
            return
        if intent.action in ("run", "ask"):
            mode = Mode.EDIT if intent.action == "run" else Mode.READ_ONLY
            header = self.assistant.announce(intent) or f"⏳ **{intent.project}**"
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
