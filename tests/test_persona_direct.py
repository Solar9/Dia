"""persona.py: the character that is added to every model prompt (DIA-36)."""

import pytest

from dia import persona
from dia.core.config import parse_config


def config(tmp_path, language="en", **assistant):
    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a", "language": language},
        "agents": {"a": {"type": "command", "argv": ["true"]}},
        "projects": {},
        "assistant": assistant,
    }
    return parse_config(raw, tmp_path / "dia.toml")


def test_the_prompt_names_her_the_user_the_personality_and_the_language(tmp_path):
    cfg = config(tmp_path, "pl", name="Dia", user_name="Dawid", personality="butler")
    text = persona.persona_prompt(cfg)
    assert "Dawid" in text and "Always answer in Polish." in text
    assert persona.PRESETS["butler"] in text
    assert "Address the user as Dawid" in text


def test_a_preset_name_or_your_own_words_become_the_personality(tmp_path):
    preset = persona.persona(config(tmp_path, personality="mentor"))
    assert preset["personality"] == persona.PRESETS["mentor"]
    own = persona.persona(config(tmp_path, personality="calm, speaks like a ship's captain"))
    assert own["personality"] == "calm, speaks like a ship's captain"
    default = persona.persona(config(tmp_path))
    assert default["personality"] == persona.PRESETS["friendly"] and default["user_name"] == ""


@pytest.mark.parametrize(
    ("language", "name"),
    [("en", "English"), ("pl", "Polish"), ("de", "German"), ("fr", "French"), ("xx", "xx")],
)
def test_the_language_is_named_for_the_model_and_unknown_codes_pass_through(
    tmp_path, language, name
):
    assert persona.persona(config(tmp_path, language))["language"] == name


def test_without_a_user_name_nobody_is_addressed(tmp_path):
    assert "Address the user" not in persona.persona_prompt(config(tmp_path))


def test_greetings_follow_the_hour_and_the_language(tmp_path):
    pl, en = config(tmp_path, "pl", user_name="Dawid"), config(tmp_path, "en", user_name="Dawid")
    assert persona.greeting(pl, 9) == "Dzień dobry, Dawid"
    assert persona.greeting(pl, 21) == "Dobry wieczór, Dawid"
    assert persona.greeting(pl, 3) == "Dobry wieczór, Dawid"  # night is evening
    assert persona.greeting(en, 8) == "Good morning, Dawid"
    assert persona.greeting(en, 14) == "Good afternoon, Dawid"
    assert persona.greeting(en, 20) == "Good evening, Dawid"
    assert persona.greeting(config(tmp_path, "en"), 8) == "Good morning"  # no name: no comma


def test_adding_a_preference_stores_it_and_audits_it(tmp_path, repo):
    from dia.core.orchestrator import Orchestrator

    raw = {
        "dia": {"data_dir": str(tmp_path / "data"), "default_agent": "a"},
        "agents": {"a": {"type": "command", "argv": ["true"]}},
        "projects": {"demo": {"path": str(repo)}},
    }
    dia = Orchestrator(parse_config(raw, tmp_path / "dia.toml"), use_memory=False)
    stored = persona.add_preference(dia, "short answers")
    assert "short answers" in stored
    assert "short answers" in persona.persona_prompt(dia.config)  # kept at once
    assert any(e["action"] == "preference.add" for e in dia.store.audit())
