from pathlib import Path

from dia.assistant import Assistant
from dia.brains import Brain, BrainContext, Intent
from dia.brains.rules import RulesBrain
from dia.config import parse_config
from dia.orchestrator import Orchestrator


class Recorder(Brain):
    """Answers every message and remembers the history it was given."""

    kind = "recorder"
    seen: list[list[tuple[str, str]]] = []

    async def interpret(self, text: str, ctx: BrainContext) -> Intent:
        Recorder.seen.append(list(ctx.history))
        return Intent("chat", reply=f"re: {text}")


def make(tmp_path: Path) -> Orchestrator:
    config = parse_config({"dia": {"data_dir": str(tmp_path / "data"), "language": "pl"}})
    return Orchestrator(config, use_memory=False)


async def test_follow_ups_see_the_conversation(tmp_path: Path) -> None:
    dia = make(tmp_path)
    Recorder.seen = []
    assistant = Assistant(dia, brains=[Recorder("r", {}, dia.config)])
    await assistant.handle("jaka pogoda w Krakowie?", "ann")
    await assistant.handle("a jutro?", "ann")
    await assistant.handle("cześć", "bob")  # someone else: their own conversation
    assert Recorder.seen[0] == []
    assert Recorder.seen[1] == [("jaka pogoda w Krakowie?", "re: jaka pogoda w Krakowie?")]
    assert Recorder.seen[2] == []


async def test_quiet_mode_by_phrase(tmp_path: Path) -> None:
    dia = make(tmp_path)
    assistant = Assistant(dia, brains=[RulesBrain("rules", {}, dia.config)])
    assert (await assistant.handle("Dia, tryb cichy")).text.startswith("Tryb cichy")
    assert dia.quiet and make(tmp_path).quiet  # kept across restarts
    await assistant.handle("możesz mówić")
    assert not dia.quiet
    assert [r["detail"] for r in dia.store.audit(action="dia.quiet")] == ["off", "on"]


async def test_one_conversation_across_devices(tmp_path: Path) -> None:
    from dia.devices import Devices

    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "language": "pl"},
        "assistant": {"owner_ids": ["4242"]},  # the owner's Discord id
    }
    dia = Orchestrator(parse_config(raw), use_memory=False)
    Devices(dia.config.data_dir).pair("pixel")
    Recorder.seen = []
    desk = Assistant(dia, brains=[Recorder("r", {}, dia.config)])  # the UI
    phone = Assistant(dia, brains=[Recorder("r", {}, dia.config)])  # another channel
    await desk.handle("jaka pogoda w Krakowie?", "ui")
    await phone.handle("a jutro?", "pixel")
    await phone.handle("a w Gdańsku?", "4242")
    assert Recorder.seen[1] == [("jaka pogoda w Krakowie?", "re: jaka pogoda w Krakowie?")]
    assert len(Recorder.seen[2]) == 2
    await phone.handle("cześć", "someone-else")
    assert Recorder.seen[3] == []
    # kept across a restart
    again = Orchestrator(parse_config(raw), use_memory=False)
    assert len(again.conversations.history("default")) == 3


async def test_a_plan_asked_for_on_one_device_is_approved_on_another(tmp_path: Path) -> None:
    raw = {"dia": {"data_dir": str(tmp_path / "data"), "language": "pl"}}
    dia = Orchestrator(parse_config(raw), use_memory=False)
    desk, voice = Assistant(dia, brains=[]), Assistant(dia, brains=[])
    desk._conversation = "ui"
    desk.pending_plan = "plan-1"
    intent = await voice.interpret("tak", "default")
    assert intent.action == "confirm" and voice.pending_plan == "plan-1"
    assert dia.conversations.canonical("guest") == "guest"


async def test_sessions_keep_their_own_plan_and_context(tmp_path: Path) -> None:
    raw = {"dia": {"data_dir": str(tmp_path / "data"), "language": "pl"}}
    dia = Orchestrator(parse_config(raw), use_memory=False)
    chats = dia.conversations
    combat, steam = chats.create(), chats.create("Steam")
    Recorder.seen = []
    assistant = Assistant(dia, brains=[Recorder("r", {}, dia.config)])
    await assistant.handle("parry w nova", combat)
    await assistant.handle("tekst na stronę", steam)
    await assistant.handle("a block?", combat)
    assert Recorder.seen[2] == [("parry w nova", "re: parry w nova")]  # only its own thread
    chats.set_pending_plan(combat, "plan-combat")
    assert chats.pending_plan(steam) is None and chats.pending_plan("ui") is None
    assert (await assistant.interpret("tak", combat)).action == "confirm"
    assert [m["text"] for m in chats.messages(combat)][:2] == ["parry w nova", "re: parry w nova"]
    assert chats.sessions()[0]["id"] == "owner"
    chats.delete(steam)
    assert steam not in {s["id"] for s in chats.sessions()}
