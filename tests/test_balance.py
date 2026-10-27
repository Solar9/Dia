import json
from pathlib import Path

from dia.balance import analyze, balance_report, describe, read_events
from dia.config import parse_config
from dia.orchestrator import Orchestrator


def session(folder: Path, name: str, events: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("\n".join(json.dumps(e) for e in events) + "\nnot json\n")


def playtests(folder: Path) -> None:
    events = []
    for i in range(10):
        events.append({"event": "level_end", "level": "1-1", "result": "win", "seconds": 60 + i})
        win = i < 2
        result = "win" if win else "lose"
        events.append({"event": "level_end", "level": "1-2", "result": result, "seconds": 90})
        events.append({"event": "level_end", "level": "1-3", "result": "win", "seconds": 300})
        if not win:
            events.append({"event": "death", "level": "1-2", "cause": "bat"})
    events.append({"event": "death", "level": "1-1", "cause": "spikes"})
    events += [{"event": "damage", "weapon": "sword", "amount": 50}] * 9
    events += [{"event": "damage", "weapon": "bow", "amount": 10}]
    session(folder, "a.jsonl", events[: len(events) // 2])
    session(folder, "b.jsonl", events[len(events) // 2 :])
    (folder / "c.csv").write_text("event,level,result,seconds\nlevel_end,1-1,win,70\n")


def test_what_stands_out(tmp_path: Path) -> None:
    playtests(tmp_path / "t")
    events, files = read_events(tmp_path / "t")
    assert files == 3
    result = analyze(events)
    levels = {lv["level"]: lv for lv in result.levels}
    assert levels["1-1"]["attempts"] == 11 and levels["1-1"]["win_rate"] == 1.0
    assert levels["1-2"]["win_rate"] == 0.2 and levels["1-2"]["deaths"] == 8
    assert result.causes[0] == {"cause": "bat", "deaths": 8, "share": 0.89}
    assert result.weapons[0]["weapon"] == "sword"
    assert result.findings == [
        "level 1-1: 100% succeed (too easy?)",
        "level 1-2: only 20% of 10 attempts succeed (too hard?)",
        "level 1-3: 100% succeed (too easy?)",
        "level 1-3: 300 s median, more than twice the usual 90 s",
        "bat causes 89% of all deaths",
        "sword deals 98% of all damage (dominant?)",
        "bow deals 2% of damage (unused?)",
    ]
    assert "Do sprawdzenia:" in describe(result, "pl")


async def test_report_for_a_project(tmp_path: Path, repo: Path) -> None:
    raw = {
        "dia": {"data_dir": str(tmp_path / "d"), "language": "pl", "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["echo", "Zmniejsz HP nietoperza"]}},
        "projects": {"nova": {"path": str(repo), "balance": {"data": str(tmp_path / "t")}}},
    }
    dia = Orchestrator(parse_config(raw), use_memory=False)
    assert "Brak danych" in await balance_report(dia, "nova")
    playtests(tmp_path / "t")
    text = await balance_report(dia, "nova", advise=True)
    assert text.startswith("Zdarzenia:") and text.endswith("Zmniejsz HP nietoperza")
