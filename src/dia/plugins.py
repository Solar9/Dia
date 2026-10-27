"""Plugin discovery.

Every extension point is a Python entry-point group. Built-in plugins are
declared in ``pyproject.toml`` the same way an external package would declare
its own, so third parties get exactly the same powers as the core.

Extension points (groups):

* ``dia.agents`` -- coding agents (:class:`dia.agents.Agent`)
* ``dia.memory`` -- long-term memory backends (:class:`dia.memory.Memory`)
* ``dia.channels`` -- interfaces such as Discord (:class:`dia.channels.Channel`)
* ``dia.brains`` -- turn free-form messages into intents (:class:`dia.brains.Brain`)
* ``dia.stt`` / ``dia.tts`` / ``dia.wake`` -- speech engines (:mod:`dia.voice`)
* ``dia.forges`` -- publishing branches: git, GitHub, GitLab (:class:`dia.forges.Forge`)
* ``dia.toolchains`` -- project kinds: test, describe, launch (:class:`dia.toolchains.Toolchain`)
* ``dia.skills`` -- everyday abilities: weather, news... (:class:`dia.skills.Skill`)

See docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import entry_points
from typing import Any

# Fallback so a source checkout works before ``pip install -e .`` registers
# the entry points.
_BUILTINS: dict[str, dict[str, str]] = {
    "dia.agents": {
        "claude-code": "dia.agents.claude_code:ClaudeCodeAgent",
        "codex": "dia.agents.codex:CodexAgent",
        "cursor": "dia.agents.cursor:CursorAgent",
        "command": "dia.agents.command:CommandAgent",
    },
    "dia.brains": {
        "rules": "dia.brains.rules:RulesBrain",
        "agent": "dia.brains.agent_brain:AgentBrain",
        "openai": "dia.brains.openai_compat:OpenAICompatBrain",
        "ollama": "dia.brains.openai_compat:OllamaBrain",
    },
    "dia.channels": {
        "discord": "dia.channels.discord_bot:DiscordChannel",
        "voice": "dia.channels.voice:VoiceChannel",
    },
    "dia.forges": {
        "git": "dia.forges.builtin:GitForge",
        "github": "dia.forges.builtin:GitHubForge",
        "gitlab": "dia.forges.builtin:GitLabForge",
    },
    "dia.toolchains": {
        "godot": "dia.toolchains.godot:GodotToolchain",
    },
    "dia.skills": {
        "weather": "dia.skills.builtin:WeatherSkill",
        "news": "dia.skills.builtin:NewsSkill",
        "stocks": "dia.skills.builtin:StocksSkill",
        "crypto": "dia.skills.builtin:CryptoSkill",
        "briefing": "dia.skills.builtin:BriefingSkill",
        "system": "dia.skills.builtin:SystemSkill",
        "services": "dia.skills.builtin:ServicesSkill",
        "updates": "dia.skills.builtin:UpdatesSkill",
        "screen": "dia.skills.builtin:ScreenSkill",
        "security": "dia.skills.builtin:SecuritySkill",
        "calendar": "dia.skills.integrations:CalendarSkill",
        "mail": "dia.skills.integrations:MailSkill",
        "home": "dia.skills.integrations:HomeSkill",
        "camera": "dia.skills.builtin:CameraSkill",
        "tidy": "dia.skills.builtin:TidySkill",
        "clipboard": "dia.skills.builtin:ClipboardSkill",
        "analyze": "dia.skills.builtin:AnalyzeSkill",
        "balance": "dia.skills.builtin:BalanceSkill",
        "notion": "dia.skills.integrations:NotionSkill",
    },
    "dia.speakers": {
        "sherpa-onnx": "dia.voice.speaker:SherpaEmbedder",
    },
    "dia.wake": {
        "openwakeword": "dia.voice.wake:OpenWakeWord",
        "whisper-keyword": "dia.voice.wake:KeywordWake",
    },
    "dia.stt": {
        "faster-whisper": "dia.voice.stt:FasterWhisperSTT",
        "command": "dia.voice.stt:CommandSTT",
    },
    "dia.tts": {
        "piper": "dia.voice.tts:PiperTTS",
        "command": "dia.voice.tts:CommandTTS",
        "elevenlabs": "dia.voice.tts:ElevenLabsTTS",
    },
    "dia.memory": {
        "markdown": "dia.memory.markdown:MarkdownMemory",
        "obsidian": "dia.memory.markdown:MarkdownMemory",
    },
}


def _load(target: str) -> Any:
    module, _, attr = target.partition(":")
    return getattr(import_module(module), attr)


def available(group: str) -> dict[str, str]:
    """Plugin name -> import target for ``group`` (installed plugins win)."""
    found = dict(_BUILTINS.get(group, {}))
    found.update({ep.name: ep.value for ep in entry_points(group=group)})
    return found


def load(group: str, name: str) -> Any:
    plugins = available(group)
    if name not in plugins:
        known = ", ".join(sorted(plugins)) or "none"
        raise LookupError(f"no plugin '{name}' in group '{group}' (available: {known})")
    return _load(plugins[name])
