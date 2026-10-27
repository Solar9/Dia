import json
from pathlib import Path

import pytest

from dia.assistant import Assistant
from dia.brains import BrainContext, parse_intent
from dia.brains.rules import RulesBrain
from dia.config import load_config, save_settings
from dia.orchestrator import Orchestrator
from dia.persona import persona_prompt
from dia.skills import builtin

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Pierwsza &amp; wiadomo\xc5\x9b\xc4\x87</title><link>https://a/1</link></item>
<item><title>Druga</title><link>https://a/2</link></item>
</channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom one</title>
<link href="https://b/1"/><updated>2026-10-24</updated></entry></feed>"""

FORECAST = {
    "current": {"temperature_2m": 11.4, "apparent_temperature": 9.6, "weather_code": 3},
    "daily": {
        "temperature_2m_max": [13.2, 15.0],
        "temperature_2m_min": [5.1, 7.8],
        "precipitation_probability_max": [40, 10],
        "weather_code": [61, 1],
    },
}


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "dia.toml"
    path.write_text(
        f'[dia]\ndata_dir = "{tmp_path / "data"}"\nlanguage = "pl"\n'
        '[assistant]\nname = "Dia"\n# a comment that must survive\n'
        '[skills.weather]\nplace = "Kraków"\n'
    )
    return path


@pytest.fixture
def web(monkeypatch):
    calls = []

    async def fake_json(url, params=None):
        calls.append((url, params))
        if "geocoding" in url:
            return {"results": [{"latitude": 50.06, "longitude": 19.94, "name": params["name"]}]}
        if "open-meteo" in url:
            return FORECAST
        if "yahoo" in url:
            price = {"AAPL": 210.0, "CDR.WA": 150.0}[url.rsplit("/", 1)[1]]
            return {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": price,
                                "chartPreviousClose": price / 1.05,
                                "currency": "USD",
                            }
                        }
                    ]
                }
            }
        if "coingecko" in url:
            return {
                "bitcoin": {"pln": 412345.6, "pln_24h_change": -1.234},
                "dogecoin": {"pln": 0.6123456, "pln_24h_change": 3.0},
            }
        raise AssertionError(url)

    async def fake_fetch(url, params=None, timeout=15):
        calls.append((url, params))
        return ATOM if "atom" in url else RSS

    monkeypatch.setattr(builtin, "fetch_json", fake_json)
    monkeypatch.setattr(builtin, "fetch", fake_fetch)
    return calls


def test_settings_overlay_keeps_the_toml_untouched(config_file: Path) -> None:
    before = config_file.read_text()
    config = load_config(config_file)
    new = save_settings(config, {"assistant": {"user_name": "Dawid", "personality": "butler"}})
    assert config_file.read_text() == before
    assert new.assistant == {"name": "Dia", "user_name": "Dawid", "personality": "butler"}
    assert load_config(config_file).assistant["user_name"] == "Dawid"
    settings = config_file.parent / "settings.json"
    assert json.loads(settings.read_text())["assistant"]["personality"] == "butler"
    assert settings.stat().st_mode & 0o777 == 0o600
    # None removes a setting; the TOML value shows through again.
    assert "user_name" not in save_settings(new, {"assistant": {"user_name": None}}).assistant


def test_persona_prompt(config_file: Path) -> None:
    config = save_settings(
        load_config(config_file), {"assistant": {"user_name": "Dawid", "personality": "butler"}}
    )
    prompt = persona_prompt(config)
    assert "You are Dia" in prompt and "J.A.R.V.I.S." in prompt
    assert "Polish" in prompt and "Dawid" in prompt


async def test_rules_route_everyday_phrases() -> None:
    brain = RulesBrain("rules", {}, None)
    ctx = BrainContext({}, [], skills={"weather": "", "news": "", "stocks": "", "briefing": ""})
    weather = await brain.interpret("Dia, jaka pogoda jutro w Gdańsku?", ctx)
    assert (weather.skill, weather.args) == ("weather", {"place": "Gdańsku", "day": "tomorrow"})
    assert (await brain.interpret("Hej Dia, dzień dobry", ctx)).skill == "briefing"
    assert (await brain.interpret("newsy", ctx)).skill == "news"
    assert (await brain.interpret("giełda", ctx)).skill == "stocks"
    crypto_ctx = BrainContext({}, [], skills={"crypto": ""})
    assert (await brain.interpret("kursy krypto", crypto_ctx)).skill == "crypto"
    assert await brain.interpret("pogoda", BrainContext({}, [])) is None  # skill disabled


def test_model_answer_with_skill() -> None:
    ctx = BrainContext({}, [], skills={"stocks": "stocks(...)"})
    raw = '{"action": "skill", "skill": "Stocks", "args": {"symbols": ["AAPL"]}, "reply": ""}'
    intent = parse_intent(raw, "jak tam apple?", ctx)
    assert intent.skill == "stocks" and intent.args == {"symbols": ["AAPL"]}
    unknown = parse_intent('{"action": "skill", "skill": "lights", "reply": "Hm?"}', "x", ctx)
    assert unknown.action == "chat" and unknown.reply == "Hm?"


async def test_skills_answer_in_polish(config_file: Path, web) -> None:
    dia = Orchestrator(load_config(config_file), use_memory=False)
    dia.apply_config(
        save_settings(
            dia.config,
            {
                "skills": {
                    "news": {"feeds": ["https://rss", "https://atom"]},
                    "stocks": {"symbols": ["AAPL", "CDR.WA"]},
                },
                "assistant": {"user_name": "Dawid"},
            },
        )
    )
    assistant = Assistant(dia, brains=[])

    weather = await assistant.run_skill("weather")
    assert "Teraz (Kraków) 11°C (odczuwalnie 10), pochmurno" in weather
    assert "od 5 do 13°C, deszcz, szansa opadów 40%" in weather
    tomorrow = await assistant.run_skill("weather", {"place": "Gdańsk", "day": "tomorrow"})
    assert tomorrow.startswith("Jutro (Gdańsk): lekkie zachmurzenie, od 8 do 15°C")

    news = await assistant.run_skill("news")
    assert news.splitlines()[1:] == ["- Pierwsza & wiadomość", "- Atom one", "- Druga"]

    stocks = await assistant.run_skill("stocks")
    assert "- AAPL: 210.00 USD (+5.00%)" in stocks

    crypto = await assistant.run_skill("crypto", {"coins": "btc, doge, nope", "currency": "pln"})
    assert crypto.splitlines() == [
        "- BTC: 412,345.60 PLN (-1.23% 24h)",
        "- DOGE: 0.612346 PLN (+3.00% 24h)",
        "- NOPE: brak danych",
    ]
    ids = next(params for url, params in web if "coingecko" in url)["ids"]
    assert ids == "bitcoin,dogecoin,nope"

    briefing = await assistant.run_skill("briefing")
    assert briefing.startswith(("Dzień dobry, Dawid.", "Dobry wieczór, Dawid."))
    assert "zadań gotowych" in briefing and "Atom one" in briefing and "AAPL" in briefing

    assert "unknown skill" in await assistant.run_skill("teleport")


def test_polish_place_names() -> None:
    from dia.skills.builtin import place_candidates

    for inflected, base in [
        ("Krakowie", "Kraków"),
        ("Gdańsku", "Gdańsk"),
        ("Poznaniu", "Poznań"),
        ("Warszawie", "Warszawa"),
        ("Zielonej Górze", "Zielona Góra"),
        ("Berlin", "Berlin"),
    ]:
        assert base in place_candidates(inflected), inflected


def test_skill_args_pairs_and_loose_words():
    from dia.cli import skill_args

    spec = {"place": "where", "days": "how many"}
    assert skill_args(spec, ["Nowy", "Sącz", "days=2"]) == {"place": "Nowy Sącz", "days": "2"}
    assert skill_args(spec, ["place=Gdańsk"]) == {"place": "Gdańsk"}
    assert skill_args({}, ["ignored"]) == {}


def test_dia_skill_runs_and_lists(config_file, monkeypatch, capsys):
    from dia.cli import main

    async def fake_fetch_json(url, params=None, timeout=15):
        assert params["vs_currencies"] == "pln"
        return {"bitcoin": {"pln": 300000.0, "pln_24h_change": 1.5}}

    monkeypatch.setattr(builtin, "fetch_json", fake_fetch_json)
    assert main(["-c", str(config_file), "skill", "crypto", "btc", "currency=pln"]) == 0
    assert "BTC: 300,000.00 PLN (+1.50% 24h)" in capsys.readouterr().out
    assert main(["-c", str(config_file), "skill"]) == 0
    listed = capsys.readouterr().out
    assert "crypto" in listed and "weather" in listed
    assert main(["-c", str(config_file), "skill", "nope"]) == 1
