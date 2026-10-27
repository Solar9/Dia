from pathlib import Path

from dia.assistant import Assistant
from dia.brains import Brain, BrainContext, Intent, parse_intent
from dia.config import parse_config
from dia.orchestrator import Orchestrator
from dia.shadow import describe_difference, replay


class Cloud(Brain):
    kind = "cloud"

    async def interpret(self, text: str, ctx: BrainContext) -> Intent:
        if "pogoda" in text:
            return Intent("skill", skill="weather")
        if "nova" in text:
            return Intent("run", project="nova", prompt=text)
        return Intent("chat", reply="hej")


class Local(Brain):
    """Agrees on everything except the projects."""

    kind = "local"
    calls: list[str] = []

    async def interpret(self, text: str, ctx: BrainContext) -> Intent | None:
        Local.calls.append(text)
        if "pogoda" in text:
            return Intent("skill", skill="weather")
        if "nova" in text:
            return Intent("ask", project="nova")
        if "zepsuj" in text:
            raise RuntimeError("model timed out")
        return Intent("chat")


def make(tmp_path: Path, **assistant) -> Orchestrator:
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["true"]}},
        "projects": {"nova": {"path": str(tmp_path)}},
        "assistant": assistant,
    }
    return Orchestrator(parse_config(raw), use_memory=False)


async def test_a_candidate_brain_is_compared_on_real_requests(tmp_path) -> None:
    dia = make(tmp_path)
    assistant = Assistant(dia, brains=[Cloud("cloud", {}, dia.config)])
    for text in ("jaka pogoda?", "popraw menu w nova", "cześć", "zepsuj się"):
        await assistant.interpret(text, "ann")
    logged = dia.store.intents()
    assert [i["action"] for i in logged] == ["chat", "chat", "run", "skill"]
    assert logged[2]["project"] == "nova" and logged[0]["brain"] == "cloud"

    Local.calls = []
    result = await replay(Local("local", {}, dia.config), dia.store, assistant.context())
    assert Local.calls[0] == "jaka pogoda?"  # oldest first
    assert (result["requests"], result["agreed"], result["errors"]) == (4, 2, 1)
    assert result["agreement"] == 0.5 and result["same_action"] == 2
    lines = [describe_difference(r) for r in result["differences"]]
    assert '"popraw menu w nova": was run nova, now ask nova' in lines
    assert any("error: model timed out" in line for line in lines)
    # Nothing ran: replay only interprets.
    assert dia.store.recent() == []
    # A brain is not compared with itself.
    assert (await replay(Cloud("cloud", {}, dia.config), dia.store, assistant.context()))[
        "requests"
    ] == 0


async def test_logging_can_be_turned_off(tmp_path) -> None:
    dia = make(tmp_path, log_intents=False)
    await Assistant(dia, brains=[Cloud("cloud", {}, dia.config)]).interpret("cześć")
    assert dia.store.intents() == []


def test_experiment_intent_needs_a_project() -> None:
    ctx = BrainContext(projects={"nova": "game"}, agents=["claude", "codex"])
    raw = (
        '{"action": "experiment", "project": "nova", "prompt": "inventory as ECS",'
        ' "args": {"approaches": ["ECS", "cache lookups"]}}'
    )
    intent = parse_intent(raw, "sprawdź, czy ECS przyspieszy nova", ctx)
    assert intent.action == "experiment" and intent.args["approaches"] == ["ECS", "cache lookups"]
    assert parse_intent('{"action": "experiment"}', "x", ctx).action == "chat"
