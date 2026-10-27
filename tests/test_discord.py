import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")

from dia.agents import Mode  # noqa: E402
from dia.channels.discord_bot import (  # noqa: E402
    DiaBot,
    DiscordChannel,
    TaskButton,
    _authorize,
    task_embed,
    task_view,
)
from dia.config import ConfigError, parse_config  # noqa: E402
from dia.orchestrator import Orchestrator  # noqa: E402

ME = 1234


def make(tmp_path: Path, repo: Path, argv: list[str], **discord_opts) -> Orchestrator:
    return Orchestrator(
        parse_config(
            {
                "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "fake"},
                "agents": {"fake": {"type": "command", "argv": argv}},
                "projects": {"demo": {"path": str(repo)}},
                "channels": {"discord": {"allowed_users": [ME], **discord_opts}},
            }
        )
    )


def fake_interaction(bot_like, user_id: int = ME):
    message = SimpleNamespace(edit=AsyncMock(), reply=AsyncMock())
    return SimpleNamespace(
        client=bot_like,
        user=SimpleNamespace(id=user_id, mention=f"<@{user_id}>"),
        response=SimpleNamespace(
            is_done=MagicMock(return_value=False), send_message=AsyncMock(), defer=AsyncMock()
        ),
        followup=SimpleNamespace(send=AsyncMock()),
        edit_original_response=AsyncMock(),
        original_response=AsyncMock(return_value=message),
    ), message


def test_channel_requires_allowed_users(tmp_path: Path, repo: Path, monkeypatch) -> None:
    orch = make(tmp_path, repo, ["true"])
    orch.config.channels["discord"]["allowed_users"] = []
    with pytest.raises(ConfigError, match="allowed_users"):
        orch.config.channel("discord", orch)

    orch.config.channels["discord"]["allowed_users"] = [ME]
    monkeypatch.delenv("DIA_DISCORD_TOKEN", raising=False)
    channel = orch.config.channel("discord", orch)
    assert isinstance(channel, DiscordChannel)
    assert "DIA_DISCORD_TOKEN" in channel.check()
    monkeypatch.setenv("DIA_DISCORD_TOKEN", "x")
    assert channel.check() is None


async def test_bot_registers_commands(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["true"])
    bot = DiaBot(orch.config.channel("discord", orch))
    names = {c.name for c in bot.tree.get_commands()}
    assert names == {
        "mission",
        "run",
        "ask",
        "plan",
        "launch",
        "tasks",
        "task",
        "search",
        "status",
        "stop",
        "resume",
    }


async def test_only_allowed_users_get_through() -> None:
    bot_like = SimpleNamespace(allowed_users={ME})
    ok, _ = fake_interaction(bot_like)
    assert await _authorize(ok)
    stranger, _ = fake_interaction(bot_like, user_id=999)
    assert not await _authorize(stranger)
    stranger.response.send_message.assert_awaited_once()


def test_button_ids_round_trip() -> None:
    button = TaskButton("merge", "20261024-131144-5268")
    assert button.item.custom_id == "dia:merge:20261024-131144-5268"
    match = re.fullmatch(TaskButton.__discord_ui_compiled_template__, button.item.custom_id)
    assert match["action"] == "merge" and match["task"] == "20261024-131144-5268"


async def test_run_report_and_merge_button(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "echo hi > hi.txt; echo wrote hi.txt"])
    bot = DiaBot(orch.config.channel("discord", orch))
    interaction, message = fake_interaction(bot)

    await bot.run_and_report(interaction, "demo", "write hi", None, Mode.EDIT)

    message.edit.assert_awaited()  # announced the task id
    args, kwargs = message.reply.await_args
    assert "<@1234>" in args[0]
    embed, view = kwargs["embed"], kwargs["view"]
    assert embed.description == "wrote hi.txt" and "hi.txt" in embed.fields[-1].value
    assert [i.custom_id.split(":")[1] for i in view.children] == [
        "diff",
        "review",
        "merge",
        "publish",
        "discard",
    ]

    task_id = embed.footer.text.removeprefix("task ")
    click, _ = fake_interaction(bot)
    await TaskButton("merge", task_id).callback(click)
    assert (repo / "hi.txt").exists()
    assert orch.store.get(task_id).status == "merged"
    assert click.edit_original_response.await_args.kwargs["view"] is None
    assert "Merged" in click.followup.send.await_args.args[0]


async def test_failed_task_cannot_be_merged_from_buttons(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", "echo x > x.txt"])
    orch.config.projects["demo"].test_command = "exit 1"
    report = await orch.run_task("demo", "x")
    view = task_view(report.task)
    merge = next(i for i in view.children if i.custom_id.startswith("dia:merge"))
    assert merge.item.disabled
    assert task_embed(report.task, report).fields  # renders with test output


async def test_free_form_dm_is_routed_through_the_brain(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", 'echo "answer: $0"', "{prompt}"])
    orch.config.agents["llm"] = {
        "type": "command",
        "argv": ["echo", '{"action": "ask", "project": "demo", "prompt": "Co tu jest?"}'],
    }
    orch.config.brains = {"router": {"type": "agent", "agent": "llm"}}
    orch.config.brain_order = ["rules", "router"]
    bot = DiaBot(orch.config.channel("discord", orch))

    status = SimpleNamespace(
        edit=AsyncMock(), reply=AsyncMock(), channel=SimpleNamespace(send=AsyncMock())
    )

    class Typing:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return None

    def dm(author_id: int):
        return SimpleNamespace(
            author=SimpleNamespace(id=author_id, bot=False, mention=f"<@{author_id}>"),
            guild=None,
            content="co jest w projekcie demo?",
            channel=SimpleNamespace(typing=Typing),
            reply=AsyncMock(return_value=status),
        )

    stranger = dm(999)
    await bot.on_message(stranger)
    stranger.reply.assert_not_awaited()

    message = dm(ME)
    await bot.on_message(message)
    await asyncio.gather(*bot._background)

    assert "Co tu jest?" in message.reply.await_args.args[0]
    embed = status.reply.await_args.kwargs["embed"]
    assert embed.description == "answer: Co tu jest?"


async def test_ci_news_is_sent_as_dm_with_fix_button(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["true"])
    bot = DiaBot(orch.config.channel("discord", orch))
    user = SimpleNamespace(send=AsyncMock())
    bot.fetch_user = AsyncMock(return_value=user)
    task = SimpleNamespace(
        id="20261024-1-abcd",
        project="demo",
        details={"ci": {"state": "failed", "url": "https://ci/1", "failed": [{"name": "tests"}]}},
    )
    from dia.orchestrator import Event

    await bot.on_dia_event(Event("ci", task, "failed"))
    kwargs = user.send.await_args.kwargs
    assert "❌" in kwargs["content"] and "https://ci/1" in kwargs["content"]
    assert "• tests" in kwargs["content"]
    assert kwargs["view"].children[0].item.custom_id == "dia:fixci:20261024-1-abcd"


async def test_plan_button_runs_the_stored_plan(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["sh", "-c", 'echo step >> steps.txt; echo "did: $0"', "{prompt}"])
    orch.config.pipelines["two"] = {
        "steps": [{"agent": "fake", "prompt": "one"}, {"agent": "fake", "prompt": "two"}]
    }
    bot = DiaBot(orch.config.channel("discord", orch))
    plan = await orch.create_plan("demo", "goal", pipeline="two")
    from dia.channels.discord_bot import plan_embed

    assert "**1. Step 1** · fake" in plan_embed(plan).description

    status = SimpleNamespace(edit=AsyncMock(), reply=AsyncMock(), channel=None)
    click, _ = fake_interaction(bot)
    click.response.edit_message = AsyncMock()
    click.followup.send = AsyncMock(return_value=status)
    await TaskButton("runplan", plan.id).callback(click)
    await asyncio.gather(*bot._background)

    click.response.edit_message.assert_awaited_once_with(view=None)
    embed = status.reply.await_args.kwargs["embed"]
    assert orch.store.get(plan.id).status == "done"
    assert embed.footer.text == f"task {plan.id}"


async def test_long_plan_steps_come_with_the_full_plan_file(tmp_path: Path, repo: Path) -> None:
    from dia.channels.discord_bot import plan_message

    orch = make(tmp_path, repo, ["true"])
    orch.config.pipelines["long"] = {"steps": [{"agent": "fake", "prompt": "x" * 400}]}
    orch.config.pipelines["two"] = {"steps": [{"agent": "fake", "prompt": "short"}]}
    plan = await orch.create_plan("demo", "goal", pipeline="long")
    message = plan_message(plan)
    assert message["file"].filename == f"plan-{plan.id}.md"
    assert "file" not in plan_message(await orch.create_plan("demo", "g", pipeline="two"))


async def test_review_comments_are_sent_with_address_button(tmp_path: Path, repo: Path) -> None:
    orch = make(tmp_path, repo, ["true"])
    bot = DiaBot(orch.config.channel("discord", orch))
    user = SimpleNamespace(send=AsyncMock())
    bot.fetch_user = AsyncMock(return_value=user)
    task = SimpleNamespace(
        id="20261024-1-abcd",
        project="demo",
        details={
            "published": {"url": "https://pr/1"},
            "comments_pending": [
                {"author": "ana", "body": "Rename\nthis", "path": "a.gd", "line": 3},
            ],
        },
    )
    from dia.orchestrator import Event

    await bot.on_dia_event(Event("review", task, "1 new comment(s) from ana"))
    kwargs = user.send.await_args.kwargs
    assert "> **ana** (a.gd:3): Rename this" in kwargs["content"]
    assert kwargs["view"].children[0].item.custom_id == "dia:fixreview:20261024-1-abcd"
