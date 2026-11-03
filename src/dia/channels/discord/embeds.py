"""Discord embeds for tasks, plans and task lists."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from dia.agents import Mode
from dia.core.orchestrator import TaskReport
from dia.core.store import TaskRecord

if TYPE_CHECKING:
    pass

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


def tasks_embed(tasks: list[TaskRecord]) -> discord.Embed:
    lines = [
        f"{STATUS_ICON.get(t.status, '•')} `{t.id}` **{t.project}** · {t.agent} · "
        f"{_cut(_title(t), 50)}"
        for t in tasks
    ]
    return discord.Embed(title="Recent tasks", description="\n".join(lines) or "No tasks yet.")
