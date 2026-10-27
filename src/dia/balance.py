"""Balance from what players actually did: "Dia, jak wygląda balans nova?"

The game writes events while people play (a few lines of GDScript, see
docs/COMPUTER.md): one JSON object per line in ``*.jsonl`` files (or CSV with
a header row), for example::

    {"event": "level_end", "level": "1-2", "result": "win", "seconds": 184}
    {"event": "death", "level": "1-2", "cause": "bat"}
    {"event": "damage", "weapon": "sword", "amount": 12}

Dia reads them and reports per level (attempts, win rate, median time,
deaths), per cause of death and per weapon (share of damage dealt), and
flags what looks off: a level almost nobody beats or everybody beats, one far
slower than the rest, one enemy behind most deaths, a weapon that does almost
all the damage or almost none. ``--agent`` lets an agent read the game code
next to the numbers and propose concrete changes (read-only).

    [projects.nova]
    balance = { data = "~/.local/share/godot/app_userdata/Nova/telemetry" }
    # min_attempts = 5, hard = 0.3, easy = 0.95, dominant = 0.6
"""

from __future__ import annotations

import csv
import json
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Balance:
    events: int = 0
    sessions: int = 0
    levels: list[dict[str, Any]] = field(default_factory=list)
    causes: list[dict[str, Any]] = field(default_factory=list)
    weapons: list[dict[str, Any]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_events(folder: Path) -> tuple[list[dict[str, Any]], int]:
    """Every event in ``folder`` (``*.jsonl``, ``*.json`` lines, ``*.csv``), and how
    many files (sessions) they came from. Broken lines are skipped."""
    events, files = [], 0
    for path in sorted(folder.rglob("*")):
        if path.suffix not in (".jsonl", ".json", ".csv") or not path.is_file():
            continue
        files += 1
        text = path.read_text(errors="replace")
        if path.suffix == ".csv":
            events += [dict(row) for row in csv.DictReader(text.splitlines())]
            continue
        for line in text.splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                events.append(item)
    return events, files


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def analyze(events: list[dict[str, Any]], options: dict[str, Any] | None = None) -> Balance:
    options = options or {}
    min_attempts = int(options.get("min_attempts", 5))
    hard, easy = float(options.get("hard", 0.3)), float(options.get("easy", 0.95))
    dominant = float(options.get("dominant", 0.6))
    result = Balance(events=len(events))

    ends: dict[str, list[dict[str, Any]]] = defaultdict(list)
    deaths_in: Counter[str] = Counter()
    causes: Counter[str] = Counter()
    damage: Counter[str] = Counter()
    for e in events:
        kind = e.get("event")
        if kind == "level_end" and e.get("level") is not None:
            ends[str(e["level"])].append(e)
        elif kind == "death":
            if e.get("level") is not None:
                deaths_in[str(e["level"])] += 1
            causes[str(e.get("cause") or "?")] += 1
        elif kind == "damage" and e.get("weapon"):
            damage[str(e["weapon"])] += _number(e.get("amount")) or 0

    for level in sorted(set(ends) | set(deaths_in)):
        runs = ends.get(level, [])
        wins = sum(str(r.get("result", "")).lower() in ("win", "won", "true", "1") for r in runs)
        times = [t for r in runs if (t := _number(r.get("seconds"))) is not None]
        result.levels.append(
            {
                "level": level,
                "attempts": len(runs),
                "win_rate": round(wins / len(runs), 2) if runs else None,
                "median_seconds": round(statistics.median(times)) if times else None,
                "deaths": deaths_in[level],
            }
        )
    medians = [lv["median_seconds"] for lv in result.levels if lv["median_seconds"]]
    typical = statistics.median(medians) if len(medians) >= 3 else None
    for lv in result.levels:
        if lv["attempts"] < min_attempts:
            continue
        if lv["win_rate"] is not None and lv["win_rate"] < hard:
            result.findings.append(
                f"level {lv['level']}: only {lv['win_rate']:.0%} of {lv['attempts']} attempts "
                "succeed (too hard?)"
            )
        elif lv["win_rate"] is not None and lv["win_rate"] > easy:
            result.findings.append(f"level {lv['level']}: {lv['win_rate']:.0%} succeed (too easy?)")
        if typical and lv["median_seconds"] and lv["median_seconds"] > 2 * typical:
            result.findings.append(
                f"level {lv['level']}: {lv['median_seconds']} s median, more than twice "
                f"the usual {typical:.0f} s"
            )

    total_deaths = sum(causes.values())
    result.causes = [
        {"cause": c, "deaths": n, "share": round(n / total_deaths, 2)}
        for c, n in causes.most_common()
    ]
    if total_deaths >= min_attempts and result.causes and result.causes[0]["share"] > 0.4:
        top = result.causes[0]
        result.findings.append(f"{top['cause']} causes {top['share']:.0%} of all deaths")

    total_damage = sum(damage.values())
    result.weapons = (
        [
            {"weapon": w, "damage": round(d), "share": round(d / total_damage, 2)}
            for w, d in damage.most_common()
        ]
        if total_damage
        else []
    )
    if len(result.weapons) >= 2:
        if result.weapons[0]["share"] > dominant:
            top = result.weapons[0]
            result.findings.append(
                f"{top['weapon']} deals {top['share']:.0%} of all damage (dominant?)"
            )
        for w in result.weapons:
            if w["share"] < 0.03:
                result.findings.append(f"{w['weapon']} deals {w['share']:.0%} of damage (unused?)")
    return result


def describe(result: Balance, language: str) -> str:
    pl = language == "pl"
    if not result.events:
        return (
            "Brak danych z rozgrywki: ustaw balance.data projektu i zbieraj zdarzenia "
            "(docs/COMPUTER.md)."
            if pl
            else "No gameplay data: set the project's balance.data and log events "
            "(docs/COMPUTER.md)."
        )
    lines = [
        f"Zdarzenia: {result.events} z {result.sessions} sesji."
        if pl
        else f"Events: {result.events} from {result.sessions} sessions."
    ]
    for lv in result.levels[:15]:
        rate = f"{lv['win_rate']:.0%}" if lv["win_rate"] is not None else "-"
        time = f"{lv['median_seconds']} s" if lv["median_seconds"] else "-"
        lines.append(
            f"  {lv['level']}: {lv['attempts']}×, {rate}, {time}, "
            + (f"śmierci {lv['deaths']}" if pl else f"deaths {lv['deaths']}")
        )
    if result.findings:
        lines.append("Do sprawdzenia:" if pl else "Worth a look:")
        lines += [f"- {f}" for f in result.findings]
    else:
        lines.append("Nic nie odstaje." if pl else "Nothing stands out.")
    return "\n".join(lines)


ADVICE_PROMPT = """\
These are statistics from playtests of this game, with what looks off:

{stats}

Read the relevant game code and data (levels, enemies, weapons) in the
current directory and propose, in {language}, concrete balance changes for
the findings that matter: which value in which file, from what to what, and
why. Do not change any files.
"""


def data_folder(project_options: dict[str, Any]) -> Path | None:
    data = (project_options.get("balance") or {}).get("data")
    return Path(os.path.expanduser(str(data))) if data else None


async def balance_report(dia: Any, project_name: str, advise: bool = False) -> str:
    from dia.agents import Mode

    project = dia.config.project(project_name)
    options = project.options.get("balance") or {}
    folder = data_folder(project.options)
    events, files = read_events(folder) if folder and folder.is_dir() else ([], 0)
    result = analyze(events, options)
    result.sessions = files
    text = describe(result, dia.config.language)
    if not advise or not result.findings:
        return text
    language = {"pl": "Polish", "en": "English"}.get(dia.config.language, "English")
    report = await dia.run_task(
        project.name,
        ADVICE_PROMPT.format(stats=text, language=language),
        mode=Mode.READ_ONLY,
        run_tests=False,
        details={"balance": result.to_dict()},
    )
    return text + "\n\n" + (report.task.summary or report.task.error or "")
