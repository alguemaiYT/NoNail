"""Discord bot integration for Zombie Mode master (requires discord.py)."""

from __future__ import annotations

import asyncio
from typing import Any

from .base import CommandCallback, MessagingBot


class DiscordBot(MessagingBot):
    name = "discord"

    def __init__(self, config: dict[str, Any], on_command: CommandCallback):
        super().__init__(config, on_command)
        import discord

        self._token = config["token"]
        self._channel_id = int(config.get("channel_id", 0))
        self._allowed_guilds = [int(g) for g in (config.get("allowed_guild_ids") or [])]

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)
        self._ready = asyncio.Event()

        @self._client.event
        async def on_ready() -> None:
            self._ready.set()

        @self._client.event
        async def on_message(message: discord.Message) -> None:
            if message.author.bot:
                return
            # Filter by channel
            if self._channel_id and message.channel.id != self._channel_id:
                return
            # Filter by guild
            if self._allowed_guilds and message.guild:
                if message.guild.id not in self._allowed_guilds:
                    return

            text = message.content.strip()
            if not text:
                return

            sender = str(message.author.id)
            reply = await self.on_command(sender, text)
            # Discord max = 2000 chars
            for i in range(0, len(reply), 1900):
                await message.reply(reply[i : i + 1900])

    async def start(self) -> None:
        await self._client.start(self._token)

    async def stop(self) -> None:
        await self._client.close()

    async def send(self, recipient: str, text: str) -> None:
        await self._ready.wait()
        channel = self._client.get_channel(self._channel_id)
        if channel:
            await channel.send(text[:1900])
