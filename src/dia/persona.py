"""Who Dia is when it talks: its name, how it addresses you, its personality.

``[assistant]`` in the config (or Settings → Assistant in the UI)::

    [assistant]
    name = "Dia"
    user_name = "..."            # how Dia addresses you; empty: no name
    personality = "butler"       # a preset below, or your own description
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dia.preferences import Preferences, preferences_text

if TYPE_CHECKING:
    from dia.config import Config
    from dia.orchestrator import Orchestrator

PRESETS = {
    "friendly": "Warm, helpful and a little playful. Short, natural sentences.",
    "butler": (
        "Composed, polite and quietly witty, like a very capable butler (think "
        "J.A.R.V.I.S.). Calm even when things break; dry humour, never servile."
    ),
    "concise": "Brief and to the point. No small talk, no filler.",
    "buddy": "Casual and relaxed, like a friend who codes. Jokes are welcome.",
    "mentor": "Patient and encouraging; explains the why, not only the what.",
}

LANGUAGES = {"pl": "Polish", "en": "English"}


def persona(config: Config) -> dict[str, str]:
    options = config.assistant
    style = str(options.get("personality") or "friendly").strip()
    return {
        "name": str(options.get("name") or "Dia").strip(),
        "user_name": str(options.get("user_name") or "").strip(),
        "personality": PRESETS.get(style, style),
        "language": LANGUAGES.get(config.language, config.language),
    }


def persona_prompt(config: Config) -> str:
    """The part of every model prompt that gives Dia its character."""
    p = persona(config)
    lines = [
        f"You are {p['name']}, the user's personal assistant.",
        f"Personality: {p['personality']}",
        f"Always answer in {p['language']}.",
    ]
    if p["user_name"]:
        lines.append(f"Address the user as {p['user_name']} (now and then, not in every line).")
    if prefs := preferences_text(config):
        lines.append(f"What the user prefers (follow it):\n{prefs}")
    return "\n".join(lines)


def add_preference(dia: Orchestrator, text: str) -> str:
    """A preference the user stated ("zapamiętaj, że wolę ..."); kept at once."""
    stored = Preferences(dia.config).add(text)
    dia.audit("preference.add", None, stored)
    return stored


def greeting(config: Config, hour: int) -> str:
    """The greeting in the configured language, e.g. "Good morning, Dawid"."""
    name = persona(config)["user_name"]
    if config.language == "pl":
        text = "Dzień dobry" if 5 <= hour < 18 else "Dobry wieczór"
    else:
        text = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    return f"{text}, {name}" if name else text
