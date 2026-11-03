"""What Dia understood, before it starts (DIA-12), and two checks on a brain's answer:
an agent the user did not name (DIA-13) and a clarifying question (DIA-14). The brains here
are scripted: they return exactly the Intent a model might."""

from pathlib import Path

import pytest

from dia.assistant import INTENT_AGENT, INTENT_LABELS, Assistant
from dia.brains import Brain, Intent, agent_mentioned, guard_agent, guard_clarifying
from dia.core.config import parse_config
from dia.core.orchestrator import Orchestrator


class Scripted(Brain):
    kind = "scripted"

    def __init__(self, intent: Intent, config) -> None:
        super().__init__("scripted", {}, config)
        self.intent = intent

    async def interpret(self, text, ctx):
        return self.intent


def make(tmp_path: Path, repo: Path, **extra) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "claude", "language": "en"},
        "agents": {
            "claude": {"type": "command", "argv": ["echo", "claude did it"]},
            "codex": {"type": "command", "argv": ["echo", "codex did it"]},
        },
        "projects": {"nova": {"path": str(repo)}},
        **extra,
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def interpret(orch: Orchestrator, intent: Intent, text: str) -> Intent:
    assistant = Assistant(orch, [Scripted(intent, orch.config)])
    return await assistant.interpret(text)


# ---- DIA-12: the action · project · agent line ----------------------------------------


def test_every_action_either_says_what_it_understood_or_is_known_to_be_silent(tmp_path, repo):
    from dia.brains import ACTIONS

    silent = {
        "status", "tasks", "skill", "schedule", "stop", "resume", "quiet", "process", "service",
        "screen_access", "camera_access", "howto", "prefer", "why", "impact", "work", "chat",
    }  # fmt: skip
    # nothing is forgotten: a new action must be added to one of the two lists
    assert set(ACTIONS) == set(INTENT_LABELS["en"]) | silent
    assert set(INTENT_LABELS["en"]) == set(INTENT_LABELS["pl"])
    assert not set(INTENT_LABELS["en"]) & silent


def test_understood_names_action_project_and_agent(tmp_path, repo):
    assistant = Assistant(make(tmp_path, repo), [])
    run = Intent("run", project="nova", prompt="fix it", reply="On it.")
    assert assistant.understood(run) == "code change · nova · claude"  # the default agent
    named = Intent("ask", project="nova", agent="codex")
    assert assistant.understood(named) == "question about code · nova · codex"
    assert assistant.understood(run, spoken=True) == "code change, nova, claude"
    # the agent only where one agent does the work
    assert assistant.understood(Intent("plan", project="nova")) == "plan · nova"
    assert (
        assistant.understood(Intent("status")) == "" and assistant.understood(Intent("chat")) == ""
    )
    assert assistant.announce(run) == "code change · nova · claude\nOn it."
    assert assistant.announce(Intent("chat", reply="Hello")) == "Hello"
    assert set(INTENT_AGENT) <= set(INTENT_LABELS["en"])


def test_understood_follows_the_language_and_routing(tmp_path, repo):
    orch = make(
        tmp_path, repo,
        routing={"rules": [{"match": "test", "agent": "codex"}]},
    )  # fmt: skip
    orch.config.language = "pl"
    assistant = Assistant(orch, [])
    routed = Intent("run", project="nova", prompt="napraw test zapisu")
    assert assistant.understood(routed) == "zmiana kodu · nova · codex"  # what run_task picks


async def test_a_plan_asks_with_what_it_understood(tmp_path, repo):
    orch = make(tmp_path, repo)
    intent = Intent("plan", project="nova", prompt="design then build", reply="")
    assistant = Assistant(orch, [Scripted(intent, orch.config)])
    intent = await assistant.interpret("plan the co-op mode")
    assert assistant.understood(intent) == "plan · nova"


# ---- DIA-13: an agent the user did not name ------------------------------------------


@pytest.mark.parametrize(
    ("text", "mentioned"),
    [
        ("niech codex to naprawi", True),
        ("zleć to Codexowi", True),  # inflected
        ("ask Claude about the save system", True),
        ("użyj chatgpt do tego", True),  # what codex is
        ("fix the save system", False),
        ("the encoder is slow", False),  # not "codex" or "code x"
    ],
)
def test_agent_mentioned(text, mentioned):
    kind = (
        "codex"
        if "codex" in text.lower() or "chatgpt" in text.lower() or "encoder" in text
        else "claude-code"
    )
    name = "codex" if kind == "codex" else "claude"
    assert agent_mentioned(text, name, kind) is mentioned


def test_a_one_letter_agent_is_not_named_by_every_word_starting_with_it():
    assert not agent_mentioned("add another shader", "a")
    assert agent_mentioned("let a do it", "a")


async def test_an_agent_the_user_did_not_name_is_dropped(tmp_path, repo):
    orch = make(tmp_path, repo)
    invented = Intent("run", project="nova", agent="codex", prompt="fix the save system")
    intent = await interpret(orch, invented, "fix the save system in nova")
    assert intent.agent is None  # run_task will route, then use the default agent
    response = await Assistant(orch, []).execute(intent)
    assert response.report.task.agent == "claude"


async def test_a_named_agent_is_kept(tmp_path, repo):
    orch = make(tmp_path, repo)
    named = Intent("run", project="nova", agent="codex", prompt="fix it")
    assert (await interpret(orch, named, "let codex fix the save system")).agent == "codex"


async def test_the_routing_choice_is_kept_even_unnamed(tmp_path, repo):
    orch = make(tmp_path, repo, routing={"rules": [{"match": "test", "agent": "codex"}]})
    chosen = Intent("run", project="nova", agent="codex", prompt="fix the test")
    assert (await interpret(orch, chosen, "fix the test in nova")).agent == "codex"
    other = Intent("run", project="nova", agent="claude", prompt="fix the test")
    # claude was neither named nor routed: routing (codex) decides
    assert (await interpret(orch, other, "fix the test in nova")).agent is None


def test_guard_agent_is_a_noop_without_an_agent():
    intent = Intent("run", project="nova")
    assert guard_agent(intent, "anything", {}) is intent


# ---- DIA-14: a clarifying question stays a chat ----------------------------------------


@pytest.mark.parametrize("action", ["ask", "run", "plan", "mission"])
async def test_a_question_to_the_user_is_a_chat_not_a_task(tmp_path, repo, action):
    orch = make(tmp_path, repo)
    asking = Intent(action, project="nova", prompt="the save system", reply="Which save system?")
    intent = await interpret(orch, asking, "how does the save system work")
    assert intent.action == "chat" and intent.reply == "Which save system?"
    response = await Assistant(orch, []).execute(intent)
    assert response.report is None and response.text == "Which save system?"
    assert orch.store.recent(5) == []  # no task was created


async def test_a_statement_still_starts_the_task(tmp_path, repo):
    orch = make(tmp_path, repo)
    statement = Intent("ask", project="nova", prompt="the save system", reply="Checking.")
    assert (await interpret(orch, statement, "how does the save system work")).action == "ask"


def test_guard_clarifying_leaves_other_actions_alone():
    status = Intent("status", reply="Anything else?")
    assert guard_clarifying(status) is status
    assert guard_clarifying(Intent("skill", reply="Which city?")).action == "skill"
    assert guard_clarifying(Intent("run", reply="Fixing it？")).action == "chat"  # full-width ?


@pytest.mark.parametrize("word", ["tak", "yes", "ja", "oui", "sí", "sì", "sim", "Oui!", "Ja."])
async def test_a_yes_in_any_interface_language_runs_the_waiting_plan(tmp_path, repo, word):
    orch = make(tmp_path, repo)
    assistant = Assistant(orch, [Scripted(Intent("chat", reply="x"), orch.config)])
    assistant.pending_action = ("a thing", lambda: None)  # something is waiting for an answer
    assert (await assistant.interpret(word)).action == "confirm"


@pytest.mark.parametrize("word", ["nie", "no", "nein", "non", "não", "Nein!"])
async def test_a_no_in_any_interface_language_drops_it(tmp_path, repo, word):
    orch = make(tmp_path, repo)
    assistant = Assistant(orch, [Scripted(Intent("chat", reply="x"), orch.config)])
    assistant.pending_action = ("a thing", lambda: None)
    assert (await assistant.interpret(word)).action == "cancel"
