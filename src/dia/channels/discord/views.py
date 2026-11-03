"""Discord buttons and the views built from them."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Any

import discord

from dia.agents import Mode
from dia.audit import ACTOR
from dia.channels.discord.embeds import plan_embed, task_embed
from dia.core.orchestrator import TaskActionError
from dia.core.store import TaskRecord
from dia.knowledge.learn import MAX_FACTS

if TYPE_CHECKING:
    from dia.channels.discord.bot import DiaBot
    from dia.core.orchestrator import Orchestrator

log = logging.getLogger("dia.discord")


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


async def _authorize(interaction: discord.Interaction) -> bool:
    allowed: set[int] = interaction.client.allowed_users  # type: ignore[attr-defined]
    if interaction.user.id in allowed:
        ACTOR.set(f"discord:{getattr(interaction.user, 'name', interaction.user.id)}")
        return True
    log.warning("refused %s (%s)", interaction.user, interaction.user.id)
    if not interaction.response.is_done():
        await interaction.response.send_message("You are not allowed to use Dia.", ephemeral=True)
    return False
