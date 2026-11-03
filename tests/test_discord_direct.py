"""Discord: embeds, review buttons, slash commands and background news, each on its own
(DIA-36). Interactions and messages are stand-ins; nothing touches the network."""

import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

discord = pytest.importorskip("discord")

from dia.agents import Mode  # noqa: E402
from dia.channels.discord import embeds  # noqa: E402
from dia.channels.discord.bot import DiaBot, DiaTree  # noqa: E402
from dia.channels.discord.views import TaskButton, plan_message, task_view  # noqa: E402
from dia.core.config import parse_config  # noqa: E402
from dia.core.orchestrator import Orchestrator, TaskActionError, TaskReport  # noqa: E402
from dia.core.store import TaskRecord  # noqa: E402
from dia.core.types import Event  # noqa: E402

ME = 4321


def record(**kw) -> TaskRecord:
    base = dict(
        id="20261103-100000-aaaa", project="demo", agent="claude", mode="edit",
        prompt="Fix the save system\nwith care", status="done", summary="Fixed it.",
        branch="dia/20261103-100000-aaaa", commit_sha="0123456789abcdef", tests_ok=True,
    )  # fmt: skip
    return TaskRecord(**{**base, **kw})


def fields(embed: discord.Embed) -> dict[str, str]:
    return {f.name: f.value for f in embed.fields}


# ---- embeds ---------------------------------------------------------------------------------


def test_a_finished_edit_shows_status_agent_tests_and_branch() -> None:
    embed = embeds.task_embed(record())
    assert embed.title == "✅ demo · Fix the save system"
    assert embed.description == "Fixed it." and embed.colour.value == 0x2E9E5B
    shown = fields(embed)
    assert shown["Status"] == "done" and shown["Agent"] == "claude" and shown["Tests"] == "passed"
    assert shown["Branch"] == "`dia/20261103-100000-aaaa` @ `0123456789`"
    assert embed.footer.text == "task 20261103-100000-aaaa"


@pytest.mark.parametrize(
    ("tests_ok", "word"), [(None, "not run"), (True, "passed"), (False, "FAILED")]
)
def test_the_test_result_is_in_words(tests_ok, word) -> None:
    assert fields(embeds.task_embed(record(tests_ok=tests_ok)))["Tests"] == word


def test_a_read_only_task_has_no_tests_and_no_branch() -> None:
    embed = embeds.task_embed(record(mode="read-only", branch=None, commit_sha=None))
    assert "Tests" not in fields(embed) and "Branch" not in fields(embed)


def test_a_failed_task_shows_its_error_test_output_diffstat_and_warnings() -> None:
    task = record(status="failed", tests_ok=False, error="agent crashed")
    report = TaskReport(
        task, diff_stat=" a.py | 2 +-", test_output="x" * 50 + "boom", warnings=["w1"]
    )
    embed = embeds.task_embed(task, report)
    shown = fields(embed)
    assert shown["Error"] == "agent crashed" and embed.colour.value == 0xC93C37
    assert "a.py" in shown["Changes"] and shown["Test output"].endswith("boom```")
    assert shown["Warnings"] == "• w1"


def test_the_last_review_is_summarised() -> None:
    reviews = [
        {"verdict": "changes_requested", "reviewer": "codex", "findings": "Add a test."},
        {"verdict": "approved", "reviewer": "codex", "findings": ""},
    ]
    approved = fields(embeds.task_embed(record(details={"reviews": reviews})))["Review"]
    assert approved == "✅ approved by codex (after 1 fix round(s))"
    open_ = fields(embeds.task_embed(record(details={"reviews": reviews[:1]})))["Review"]
    assert open_.startswith("✏️ changes requested by codex") and "Add a test." in open_
    unclear = [{"verdict": "unclear", "reviewer": "r", "findings": "?"}]
    assert "❔" in fields(embeds.task_embed(record(details={"reviews": unclear})))["Review"]


def test_long_texts_are_cut_to_what_discord_allows() -> None:
    assert embeds._cut("short", 10) == "short"
    assert embeds._cut("a" * 50, 10) == "a" * 8 + " …"
    embed = embeds.task_embed(record(summary="s" * 9000, prompt="p" * 400, status="weird"))
    assert len(embed.description) <= 3500 and len(embed.title) <= 256
    assert embed.title.startswith("• demo") and embed.colour.value == 0x808080


def test_plans_and_missions_say_how_they_run() -> None:
    steps = [
        {"agent": "a", "title": "Design", "prompt": "do " * 200},
        {"agent": "b", "prompt": "x"},
    ]
    plan = embeds.plan_embed(record(status="planned", details={"plan": steps}))
    assert "**1. Design** · a" in plan.description and "**2. b** · b" in plan.description
    assert plan.footer.text.endswith("runs on one branch, step by step")
    mission = embeds.plan_embed(record(mode="mission", details={"plan": steps}))
    assert "independent steps run in parallel" in mission.footer.text


def test_the_task_list_and_its_empty_state() -> None:
    assert embeds.tasks_embed([]).description == "No tasks yet."
    listing = embeds.tasks_embed([record(), record(id="b", status="failed")])
    assert (
        "✅ `20261103-100000-aaaa` **demo** · claude · Fix the save system" in listing.description
    )
    assert "❌ `b`" in listing.description


def test_an_inline_review_comment_names_its_file_and_line() -> None:
    assert embeds._location({"path": "a.py", "line": 7}) == " (a.py:7)"
    assert embeds._location({"path": "a.py"}) == " (a.py)"
    assert embeds._location({"body": "general"}) == ""


# ---- the buttons ----------------------------------------------------------------------------


def make(tmp_path: Path, repo: Path) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "fake"},
        "agents": {"fake": {"type": "command", "argv": ["echo", "ok"]}},
        "projects": {"demo": {"path": str(repo)}},
        "channels": {"discord": {"allowed_users": [ME]}},
    }
    return Orchestrator(parse_config(raw), use_memory=False)


def click(client, user_id: int = ME):
    message = SimpleNamespace(
        edit=AsyncMock(), reply=AsyncMock(), channel=SimpleNamespace(send=AsyncMock())
    )
    response = SimpleNamespace(
        is_done=MagicMock(return_value=False), send_message=AsyncMock(), defer=AsyncMock(),
        edit_message=AsyncMock(),
    )  # fmt: skip
    return SimpleNamespace(
        client=client, user=SimpleNamespace(id=user_id, mention=f"<@{user_id}>", name="me"),
        response=response, followup=SimpleNamespace(send=AsyncMock(return_value=message)),
        edit_original_response=AsyncMock(), original_response=AsyncMock(return_value=message),
        command_failed=False,
    )  # fmt: skip


@pytest.fixture
def dia_stub():
    stored = {"a1a1": record(id="a1a1")}
    dia = SimpleNamespace(
        store=SimpleNamespace(get=lambda task_id: stored.get(task_id)),
        task_diff=AsyncMock(return_value="+a\n-b"),
        merge_task=AsyncMock(return_value="abcdef0123456789"),
        publish_task=AsyncMock(return_value=SimpleNamespace(message="opened PR #3")),
        discard_task=AsyncMock(),
        review_task=AsyncMock(return_value=TaskReport(record(id="a1a1"))),
        fix_ci=AsyncMock(), address_comments=AsyncMock(),
        fix_build=AsyncMock(return_value=TaskReport(record(id="a1a1"))),
        decide_facts=MagicMock(return_value=["fact one", "fact two"]),
        stored=stored,
    )  # fmt: skip
    return dia


@pytest.fixture
def client(dia_stub):
    return SimpleNamespace(
        dia=dia_stub, allowed_users={ME}, spawn=MagicMock(), report_task=MagicMock()
    )


async def press(action: str, client, task_id: str = "a1a1", **kw):
    interaction = click(client, **kw)
    await TaskButton(action, task_id).callback(interaction)
    return interaction


async def test_diff_is_shown_inline_or_as_a_file(client, dia_stub) -> None:
    short = await press("diff", client)
    assert short.followup.send.await_args.args[0] == "```diff\n+a\n-b\n```"
    dia_stub.task_diff.return_value = "x" * 5000
    long = await press("diff", client)
    assert isinstance(long.followup.send.await_args.kwargs["file"], discord.File)
    dia_stub.task_diff.side_effect = TaskActionError("no such task")
    refused = await press("diff", client)
    assert refused.followup.send.await_args.args[0] == "❌ no such task"


async def test_merge_publish_and_discard_are_the_users_click(client, dia_stub) -> None:
    merged = await press("merge", client)
    assert "🔀 Merged task `a1a1` (`abcdef0123`)." in merged.followup.send.await_args.args[0]
    merged.edit_original_response.assert_awaited_once()  # the card loses its buttons
    published = await press("publish", client)
    assert published.followup.send.await_args.args[0] == "🚀 Task `a1a1`: opened PR #3"
    discarded = await press("discard", client)
    assert "🗑️ Discarded task `a1a1` and its branch." in discarded.followup.send.await_args.args[0]
    dia_stub.merge_task.side_effect = TaskActionError("conflicts")
    failed = await press("merge", client)
    assert failed.followup.send.await_args.args[0] == "❌ conflicts"
    assert failed.followup.send.await_args.kwargs == {"ephemeral": True}


async def test_a_stranger_cannot_press_anything(client, dia_stub) -> None:
    interaction = click(client, user_id=999)
    assert await TaskButton("merge", "a1a1").interaction_check(interaction) is False
    interaction.response.send_message.assert_awaited_once()
    dia_stub.merge_task.assert_not_awaited()


@pytest.mark.parametrize(
    ("action", "method", "says"),
    [
        ("fixci", "fix_ci", "🛠️ Fix for `a1a1` pushed; CI runs again."),
        ("fixreview", "address_comments", "💬 Changes for the comments on `a1a1` pushed"),
    ],
)
async def test_fix_buttons_push_and_say_so_or_say_why_not(
    client, dia_stub, action, method, says
) -> None:
    done = await press(action, client)
    assert done.followup.send.await_args.args[0].startswith(says)
    getattr(dia_stub, method).side_effect = TaskActionError("nothing to fix")
    failed = await press(action, client)
    assert failed.followup.send.await_args.args[0] == "❌ nothing to fix"


async def test_review_and_fix_build_answer_with_a_task_card(client, dia_stub) -> None:
    reviewed = await press("review", client)
    assert isinstance(reviewed.followup.send.await_args.kwargs["embed"], discord.Embed)
    built = await press("fixbuild", client)
    assert isinstance(built.followup.send.await_args.kwargs["embed"], discord.Embed)
    dia_stub.review_task.side_effect = TaskActionError("no commit")
    dia_stub.fix_build.side_effect = TaskActionError("not a check")
    assert (await press("review", client)).followup.send.await_args.args[0] == "❌ no commit"
    assert (await press("fixbuild", client)).followup.send.await_args.args[0] == "❌ not a check"


async def test_remembering_or_skipping_what_dia_learnt(client, dia_stub) -> None:
    yes = await press("learnyes", client)
    assert yes.followup.send.await_args.args[0] == "🧠 Remembered 2 fact(s)."
    yes.response.edit_message.assert_awaited_once_with(view=None)
    no = await press("learnno", client)
    assert no.followup.send.await_args.args[0] == "✖️ Skipped."
    assert dia_stub.decide_facts.call_args.kwargs["accept"] == []
    dia_stub.decide_facts.side_effect = TaskActionError("already decided")
    late = await press("learnyes", client)
    assert late.followup.send.await_args.args[0] == "❌ already decided"


async def test_a_plan_runs_once(client, dia_stub) -> None:
    dia_stub.stored["b1b1"] = record(id="b1b1", status="planned")
    interaction = click(client)
    await TaskButton("runplan", "b1b1").callback(interaction)
    client.report_task.assert_called_once()
    assert client.report_task.call_args.kwargs["plan_id"] == "b1b1"
    client.spawn.assert_called_once()
    again = click(client)
    await TaskButton("runplan", "a1a1").callback(again)  # not planned: it already started
    assert again.response.send_message.await_args.args[0] == "This plan was already started."
    ghost = click(client)
    await TaskButton("runplan", "dead").callback(ghost)
    assert ghost.response.send_message.await_args.args[0] == "This plan was already started."


def test_which_buttons_a_task_card_gets() -> None:
    def labels(task):
        view = task_view(task)
        return [] if view is None else [c.item.label for c in view.children]

    done = labels(record())
    assert "Merge" in done and "Discard" in done and "Diff" in done
    assert "Review" in labels(record(status="failed"))
    assert labels(record(status="merged", mode="read-only", commit_sha=None)) == []


def test_a_plan_message_has_an_embed_and_a_run_button() -> None:
    steps = [{"agent": "a", "prompt": "x" * 300}]
    long = plan_message(record(status="planned", details={"plan": steps}))
    assert isinstance(long["embed"], discord.Embed) and isinstance(long["file"], discord.File)
    assert long["view"].children[0].item.label == "Run plan"
    short = plan_message(
        record(status="planned", details={"plan": [{"agent": "a", "prompt": "x"}]})
    )
    assert "file" not in short


# ---- slash commands -------------------------------------------------------------------------


@pytest.fixture
def bot(tmp_path: Path, repo: Path):
    orch = make(tmp_path, repo)
    bot = DiaBot(orch.config.channel("discord", orch))
    bot.spawn = MagicMock(side_effect=lambda coro: coro.close())  # a command starts background work
    bot.run_and_report = AsyncMock()
    return bot


def command(bot: DiaBot, name: str):
    return bot.tree.get_command(name).callback


async def test_run_and_ask_start_a_task_in_the_right_mode(bot) -> None:
    interaction = click(bot)
    await command(bot, "run")(interaction, "demo", "fix it", None, False, True)
    assert "⏳ **demo**" in interaction.response.send_message.await_args.args[0]
    args = bot.run_and_report.call_args.args
    assert args[1:] == ("demo", "fix it", None, Mode.EDIT, True)
    await command(bot, "run")(interaction, "demo", "look", "claude", True, None)
    assert bot.run_and_report.call_args.args[1:] == ("demo", "look", "claude", Mode.READ_ONLY, None)
    await command(bot, "ask")(interaction, "demo", "how does it work?", None)
    assert bot.run_and_report.call_args.args[1:] == (
        "demo",
        "how does it work?",
        None,
        Mode.READ_ONLY,
    )


async def test_plan_and_mission_reply_with_a_plan_card_or_the_error(bot, monkeypatch) -> None:
    plan = record(status="planned", details={"plan": [{"agent": "a", "prompt": "x"}]})
    bot.dia.create_plan = AsyncMock(return_value=plan)
    interaction = click(bot)
    await command(bot, "plan")(interaction, "demo", "build co-op", None)
    interaction.response.defer.assert_awaited_once()
    assert isinstance(interaction.followup.send.await_args.kwargs["embed"], discord.Embed)
    bot.dia.create_plan.side_effect = TaskActionError("no pipeline")
    refused = click(bot)
    await command(bot, "plan")(refused, "demo", "x", "ghost")
    assert refused.followup.send.await_args.args[0] == "❌ no pipeline"

    class Missions:
        def __init__(self, dia) -> None:
            pass

        async def create(self, project, goal):
            return plan

    monkeypatch.setattr("dia.work.missions.Missions", Missions)
    mission = click(bot)
    await command(bot, "mission")(mission, "demo", "get ready")
    assert isinstance(mission.followup.send.await_args.kwargs["embed"], discord.Embed)


async def test_launch_says_what_it_did_privately(bot) -> None:
    bot.dia.launch = AsyncMock(return_value="started the game")
    ok = click(bot)
    await command(bot, "launch")(ok, "demo")
    assert ok.response.send_message.await_args.args[0] == "🎮 started the game"
    assert ok.response.send_message.await_args.kwargs == {"ephemeral": True}
    bot.dia.launch.side_effect = TaskActionError("no launch command")
    bad = click(bot)
    await command(bot, "launch")(bad, "demo")
    assert bad.response.send_message.await_args.args[0] == "❌ no launch command"


async def test_tasks_and_task_show_the_store(bot) -> None:
    bot.dia.store.save(record(id="20261103-100000-aaaa"))
    listing = click(bot)
    await command(bot, "tasks")(listing, None)
    assert (
        "20261103-100000-aaaa"
        in listing.response.send_message.await_args.kwargs["embed"].description
    )
    one = click(bot)
    await command(bot, "task")(one, " 20261103-100000-aaaa ")
    sent = one.response.send_message.await_args.kwargs
    assert isinstance(sent["embed"], discord.Embed) and "view" in sent
    missing = click(bot)
    await command(bot, "task")(missing, "nope")
    assert missing.response.send_message.await_args.args[0] == "No task `nope`."


async def test_search_needs_memory_and_lists_the_hits(bot) -> None:
    off = click(bot)
    bot.dia.memory = None
    await command(bot, "search")(off, "ecs")
    assert off.response.send_message.await_args.args[0] == "Memory is off."
    bot.dia.memory = SimpleNamespace(
        search=lambda query, limit: [SimpleNamespace(link="[[Nova]]", snippet="ECS was dropped")]
    )
    on = click(bot)
    await command(bot, "search")(on, "ecs")
    embed = on.response.send_message.await_args.kwargs["embed"]
    assert "[[Nova]]" in embed.description and "ECS was dropped" in embed.description
    bot.dia.memory = SimpleNamespace(search=lambda query, limit: [])
    none = click(bot)
    await command(bot, "search")(none, "zzz")
    assert none.response.send_message.await_args.kwargs["embed"].description == "No matching notes."


async def test_stop_resume_and_status(bot) -> None:
    stop = click(bot)
    await command(bot, "stop")(
        stop,
    )
    assert stop.response.send_message.await_args.args[0].startswith("🛑 Stopped 0 process(es).")
    resume = click(bot)
    await command(bot, "resume")(resume)
    assert resume.response.send_message.await_args.args[0] == "▶️ Resumed."
    status = click(bot)
    await command(bot, "status")(status)
    text = status.followup.send.await_args.args[0]
    assert "agent **fake**" in text and "project **demo**" in text and "active tasks: 0" in text
    assert status.followup.send.await_args.kwargs == {"ephemeral": True}


async def test_status_flags_a_limited_agent_and_a_broken_one(bot) -> None:
    bot.dia.limit_status = lambda: {"fake": "2026-11-03T10:00:00+00:00"}
    limited = click(bot)
    await command(bot, "status")(limited)
    assert "usage limit until <t:" in limited.followup.send.await_args.args[0]
    bot.dia.limit_status = lambda: {}

    class Broken:
        async def check(self):
            raise RuntimeError("cannot start")

    bot.dia.config.agent = lambda name, project=None: Broken()
    broken = click(bot)
    await command(bot, "status")(broken)
    assert "⚠️ agent **fake**: cannot start" in broken.followup.send.await_args.args[0]


async def test_the_choices_offered_while_typing(bot) -> None:
    run = bot.tree.get_command("run")
    interaction = click(bot)
    projects = await run._params["project"].autocomplete(interaction, "DE")
    assert [c.value for c in projects] == ["demo"]
    agents = await run._params["agent"].autocomplete(interaction, "fa")
    assert [c.value for c in agents] == ["fake"]
    assert await run._params["project"].autocomplete(interaction, "zzz") == []
    plan = bot.tree.get_command("plan")
    assert await plan._params["pipeline"].autocomplete(interaction, "") == []


async def test_the_command_tree_rejects_strangers_and_reports_errors(bot) -> None:
    tree = bot.tree
    assert isinstance(tree, DiaTree)
    assert await tree.interaction_check(click(bot)) is True
    stranger = click(bot, user_id=999)
    assert await tree.interaction_check(stranger) is False
    quiet = click(bot)
    await tree.on_error(quiet, discord.app_commands.CheckFailure())
    quiet.response.send_message.assert_not_awaited()  # a refusal was already answered
    failing = click(bot)
    await tree.on_error(failing, discord.app_commands.AppCommandError("boom"))
    assert failing.response.send_message.await_args.args[0] == "❌ boom"
    late = click(bot)
    late.response.is_done.return_value = True
    await tree.on_error(late, discord.app_commands.AppCommandError("again"))
    assert late.followup.send.await_args.args[0] == "❌ again"


# ---- background news ------------------------------------------------------------------------


@pytest.fixture
def dm(bot):
    user = SimpleNamespace(send=AsyncMock())
    bot.fetch_user = AsyncMock(return_value=user)
    return user


def buttons(kwargs) -> list[str]:
    return [c.item.custom_id.split(":")[1] for c in kwargs["view"].children]


async def test_what_dia_learnt_comes_with_remember_and_skip(bot, dm) -> None:
    task = record(id="a1")
    await bot.on_dia_event(Event("learn", task, "ECS was dropped\nuse sparse sets"))
    kwargs = dm.send.await_args.kwargs
    assert "• ECS was dropped\n• use sparse sets" in kwargs["content"]
    assert buttons(kwargs) == ["learnyes", "learnno"]


async def test_a_failed_check_offers_a_fix_a_fixed_one_does_not(bot, dm) -> None:
    watch = {"sha": "abcdef0123456", "subject": "Break it", "author": "me"}
    check = record(id="e1e1", details={"watch": watch, "test_tail": "FAILED test_x"})
    await bot.on_dia_event(Event("watch", check, "failed"))
    kwargs = dm.send.await_args.kwargs
    assert "❌ Build · **demo** · `abcdef0123` Break it (me): failed" in kwargs["content"]
    assert "FAILED test_x" in kwargs["content"] and buttons(kwargs) == ["fixbuild"]
    await bot.on_dia_event(Event("watch", check, "fixed"))
    fixed = dm.send.await_args.kwargs
    assert "✅" in fixed["content"] and "view" not in fixed


async def test_an_imported_issue_can_be_started(bot, dm) -> None:
    task = record(id="c1c1", details={"issue": {"url": "https://example/issues/9"}})
    await bot.on_dia_event(Event("issue", task, "#9 Crash on save"))
    kwargs = dm.send.await_args.kwargs
    assert "📥 Issue · **demo**: #9 Crash on save\nhttps://example/issues/9" in kwargs["content"]
    assert buttons(kwargs) == ["runplan"]


async def test_builds_system_news_schedules_and_limits(bot, dm) -> None:
    await bot.on_dia_event(Event("build", record(), "1.0 built"))
    assert dm.send.await_args.kwargs["content"] == "📦 Build · **demo**: 1.0 built"
    await bot.on_dia_event(Event("build", record(status="failed"), "tests fail"))
    assert dm.send.await_args.kwargs["content"].startswith("❌ Build")
    await bot.on_dia_event(Event("system", None, "CPU is hot"))
    assert dm.send.await_args.kwargs["content"] == "🖥️ CPU is hot"
    await bot.on_dia_event(Event("schedule", None, "Sunny", {"job": {"text": "weather"}}))
    assert dm.send.await_args.kwargs["content"] == "⏰ **weather**\nSunny"
    await bot.on_dia_event(Event("limit", record(), "claude until 15:00"))
    assert (
        "⏳ Limit · **demo** · `20261103-100000-aaaa`: claude until 15:00"
        in dm.send.await_args.kwargs["content"]
    )
    await bot.on_dia_event(Event("limit", None, "codex until 16:00"))
    assert dm.send.await_args.kwargs["content"] == "⏳ Limit: codex until 16:00"
    sent = dm.send.await_count
    await bot.on_dia_event(Event("voice", None, "listening"))  # not news for Discord
    assert dm.send.await_count == sent


async def test_ci_and_review_news(bot, dm) -> None:
    ci = record(id="b1b1", details={"ci": {"url": "https://ci/1", "failed": [{"name": "tests"}]}})
    await bot.on_dia_event(Event("ci", ci, "success"))
    ok = dm.send.await_args.kwargs
    assert ok["content"].startswith("✅ CI · **demo**") and "view" not in ok
    comments = [{"author": "rev", "body": "rename\nthis", "path": "a.py", "line": 3}]
    review = record(id="d1d1", details={"comments_pending": comments,
                                       "published": {"url": "https://pr/1"}})  # fmt: skip
    await bot.on_dia_event(Event("review", review, "1 new comment"))
    kwargs = dm.send.await_args.kwargs
    assert "💬 Review · **demo**" in kwargs["content"] and "https://pr/1" in kwargs["content"]
    assert "> **rev** (a.py:3): rename this" in kwargs["content"]
    assert buttons(kwargs) == ["fixreview"]
    await bot.on_dia_event(Event("review", record(id="d2d2"), "all resolved"))
    assert "view" not in dm.send.await_args.kwargs
    sent = dm.send.await_count
    await bot.on_dia_event(Event("ci", None, "failed"))  # no task: nothing to say
    assert dm.send.await_count == sent


async def test_news_goes_to_the_notify_channel_when_there_is_one(bot) -> None:
    channel = SimpleNamespace(send=AsyncMock())
    bot.notify_channel_id = 77
    bot.get_channel = MagicMock(return_value=channel)
    await bot.on_dia_event(Event("system", None, "hello"))
    channel.send.assert_awaited_once_with(content="🖥️ hello")
    bot.get_channel.return_value = None  # a channel the bot cannot see: no crash
    await bot.on_dia_event(Event("system", None, "again"))


async def test_a_user_who_cannot_be_reached_is_skipped(bot) -> None:
    bot.fetch_user = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=404), "nope"))
    await bot.on_dia_event(Event("system", None, "hello"))  # no exception


# ---- running a task from Discord ------------------------------------------------------------


def status_message():
    return SimpleNamespace(
        edit=AsyncMock(), reply=AsyncMock(), channel=SimpleNamespace(send=AsyncMock())
    )


async def test_a_finished_task_is_reported_with_a_card_and_a_ping(tmp_path, repo) -> None:
    orch = make(tmp_path, repo)
    bot = DiaBot(orch.config.channel("discord", orch))
    status = status_message()
    await bot.report_task(status, "<@1>", "demo", "say ok", None, Mode.READ_ONLY)
    status.edit.assert_awaited()  # "running" while it works
    assert (
        "task finished" in status.reply.await_args.args[0]
        and "<@1>" in status.reply.await_args.args[0]
    )
    assert isinstance(status.reply.await_args.kwargs["embed"], discord.Embed)


async def test_a_long_summary_comes_as_a_file(tmp_path, repo) -> None:
    orch = make(tmp_path, repo)
    orch.config.agents["fake"] = {
        "type": "command",
        "argv": ["sh", "-c", "yes word | head -c 5000"],
    }
    bot = DiaBot(orch.config.channel("discord", orch))
    status = status_message()
    await bot.report_task(status, "<@1>", "demo", "x", None, Mode.READ_ONLY)
    assert isinstance(status.reply.await_args.kwargs["file"], discord.File)


async def test_a_task_that_cannot_start_says_why(tmp_path, repo) -> None:
    orch = make(tmp_path, repo)
    bot = DiaBot(orch.config.channel("discord", orch))
    status = status_message()
    await bot.report_task(status, "<@1>", "ghost", "x", None, Mode.EDIT)
    assert status.channel.send.await_args.args[0].startswith("❌")
    fallback = AsyncMock()
    await bot.report_task(status, "<@1>", "ghost", "x", None, Mode.EDIT, fallback=fallback)
    assert fallback.await_args.args[0].startswith("❌")


async def test_when_the_channel_refuses_the_reply_the_webhook_is_used(tmp_path, repo) -> None:
    orch = make(tmp_path, repo)
    bot = DiaBot(orch.config.channel("discord", orch))
    status = status_message()
    status.reply = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no access"))
    fallback = AsyncMock()
    await bot.report_task(status, "<@1>", "demo", "x", None, Mode.READ_ONLY, fallback=fallback)
    assert "task finished" in fallback.await_args.args[0]


async def test_run_and_report_is_the_slash_flavour(bot, tmp_path) -> None:
    bot.report_task = AsyncMock()
    interaction = click(bot)
    bot_run = DiaBot.run_and_report
    await bot_run(bot, interaction, "demo", "x", "claude", Mode.EDIT, True)
    args, kwargs = bot.report_task.call_args
    assert args[2:6] == ("demo", "x", "claude", Mode.EDIT)
    assert kwargs["review"] is True and kwargs["fallback"] is interaction.followup.send


async def test_spawn_keeps_background_work_alive_until_it_ends(tmp_path, repo) -> None:
    orch = make(tmp_path, repo)
    plain = DiaBot(orch.config.channel("discord", orch))
    done = asyncio.Event()

    async def work():
        await done.wait()

    plain.spawn(work())
    assert len(plain._background) == 1
    done.set()
    await asyncio.sleep(0.05)
    assert plain._background == set()


# ---- messages -------------------------------------------------------------------------------


class Typing:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return None


def message(text: str, author_id: int = ME, guild=None, mentions=None):
    return SimpleNamespace(
        author=SimpleNamespace(id=author_id, bot=False, mention=f"<@{author_id}>", name="me"),
        guild=guild, content=text, mentions=mentions or [], channel=SimpleNamespace(typing=Typing),
        reply=AsyncMock(return_value=status_message()),
    )  # fmt: skip


async def test_in_a_server_the_bot_answers_only_when_mentioned(bot) -> None:
    bot._connection.user = SimpleNamespace(id=555)  # who the bot is, once logged in
    guild = SimpleNamespace(id=1)
    ignored = message("status", guild=guild)
    await bot.on_message(ignored)
    ignored.reply.assert_not_awaited()
    asked = message("<@555> status", guild=guild, mentions=[bot.user])
    await bot.on_message(asked)
    assert "Agents ready" in asked.reply.await_args.args[0]
    empty = message("<@555>", guild=guild, mentions=[bot.user])
    await bot.on_message(empty)
    empty.reply.assert_not_awaited()
    robot = message("status")
    robot.author.bot = True
    await bot.on_message(robot)
    robot.reply.assert_not_awaited()


async def test_a_request_for_a_plan_in_a_dm_answers_with_the_plan_card(bot, monkeypatch) -> None:
    plan = record(status="planned", details={"plan": [{"agent": "a", "prompt": "x"}]})
    bot.dia.create_plan = AsyncMock(return_value=plan)
    bot.assistant.interpret = AsyncMock(
        return_value=SimpleNamespace(
            action="plan", project="demo", prompt="build co-op", conversation=str(ME), reply="",
        )
    )  # fmt: skip
    bot.assistant.understood = lambda intent, spoken=False: "plan · demo"
    dm_message = message("make a plan")
    await bot.on_message(dm_message)
    sent = dm_message.reply.await_args
    assert sent.args[0] == "plan · demo" and isinstance(sent.kwargs["embed"], discord.Embed)
    bot.dia.create_plan.side_effect = TaskActionError("no agents")
    failing = message("make a plan")
    await bot.on_message(failing)
    assert failing.reply.await_args.args[0] == "❌ no agents"


async def test_a_run_request_starts_the_task_and_reports_it(bot) -> None:
    bot.report_task = AsyncMock()
    bot.spawn = MagicMock(side_effect=lambda coro: asyncio.ensure_future(coro))
    bot.assistant.interpret = AsyncMock(
        return_value=SimpleNamespace(
            action="run", project="demo", prompt="fix saving", conversation=str(ME), agent=None,
            reply="On it.",
        )
    )  # fmt: skip
    bot.assistant.understood = lambda intent, spoken=False: "code change · demo · fake"
    request = message("fix saving in demo")
    await bot.on_message(request)
    await asyncio.sleep(0.05)
    header = request.reply.await_args.args[0]
    assert header.startswith("code change · demo · fake") and "On it." in header
    bot.report_task.assert_awaited_once()


async def test_the_channel_checks_its_token_and_reports_why_it_cannot_start(
    tmp_path, repo, monkeypatch
) -> None:
    orch = make(tmp_path, repo)
    channel = orch.config.channel("discord", orch)
    monkeypatch.delenv("DIA_DISCORD_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DIA_DISCORD_TOKEN"):
        await channel.run()
    monkeypatch.setenv("DIA_DISCORD_TOKEN", "bad")

    async def start(self, token):
        raise discord.LoginFailure("Improper token")

    monkeypatch.setattr(DiaBot, "start", start)
    with pytest.raises(RuntimeError, match="rejected the bot token"):
        await channel.run()

    async def offline(self, token):
        raise OSError("no route")

    monkeypatch.setattr(DiaBot, "start", offline)
    with pytest.raises(RuntimeError, match="cannot reach Discord: no route"):
        await channel.run()
    assert channel.guild_id is None and channel.notify_channel_id is None


async def test_the_bot_registers_its_buttons_and_syncs(tmp_path, repo) -> None:
    orch = make(tmp_path, repo)
    orch.config.channels["discord"].update(guild_id="99", notify_channel_id="7")
    channel = orch.config.channel("discord", orch)
    assert channel.guild_id == 99 and channel.notify_channel_id == 7
    bot = DiaBot(channel)
    bot.tree.sync = AsyncMock()
    bot.add_dynamic_items = MagicMock()
    await bot.setup_hook()
    bot.add_dynamic_items.assert_called_once_with(TaskButton)
    assert bot.on_dia_event in orch.listeners
    bot.tree.sync.assert_awaited_once()
    assert bot.tree.sync.await_args.kwargs["guild"].id == 99  # a guild: commands appear at once
    plain = DiaBot(orch.config.channel("discord", orch))
    plain.guild_id = None
    plain.tree.sync = AsyncMock()
    plain.add_dynamic_items = MagicMock()
    await plain.setup_hook()
    plain.tree.sync.assert_awaited_once_with()


def test_a_file_object_is_made_from_bytes() -> None:
    assert discord.File(io.BytesIO(b"x"), "a.md").filename == "a.md"  # (what report_task relies on)
