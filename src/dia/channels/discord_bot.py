"""The Discord channel moved to :mod:`dia.channels.discord`; this module keeps the
``dia.channels`` entry point (``dia.channels.discord_bot:DiscordChannel``) working."""

from dia.channels.discord import DiscordChannel

__all__ = ["DiscordChannel"]
