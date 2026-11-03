"""Discord channel: slash commands, task notifications and approval buttons.

Setup (once): create an application at https://discord.com/developers,
add a bot, copy its token into the ``DIA_DISCORD_TOKEN`` environment
variable, and invite it with the ``bot`` and ``applications.commands``
scopes. No privileged intents are needed: Dia only uses slash commands.

Besides slash commands, a direct message or an @mention is read by Dia's
brain (``[dia] brain``), e.g. "@Dia what does the save system in nova do?".

Only the user ids listed in ``allowed_users`` can use the bot; everyone
else is refused, including on buttons.
"""

from __future__ import annotations

from dia.channels.discord.bot import DiscordChannel

__all__ = ["DiscordChannel"]
