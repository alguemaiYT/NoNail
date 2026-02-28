"""Telegram bot integration for Zombie Mode master (requires aiogram>=3.0)."""

from __future__ import annotations

from typing import Any

from .base import CommandCallback, MessagingBot


class TelegramBot(MessagingBot):
    name = "telegram"

    def __init__(self, config: dict[str, Any], on_command: CommandCallback):
        super().__init__(config, on_command)
        from aiogram import Bot, Dispatcher
        from aiogram.types import Message

        self._token = config["token"]
        self._bot = Bot(token=self._token)
        self._dp = Dispatcher()

        allowed = [str(u) for u in (config.get("allowed_users") or [])]

        @self._dp.message()
        async def _handle(message: Message) -> None:
            sender = str(message.from_user.id)
            if allowed and sender not in allowed:
                await message.reply("⛔ Not authorised.")
                return
            text = message.text or ""
            if not text:
                return
            reply = await self.on_command(sender, text)
            # Telegram max message length = 4096
            for i in range(0, len(reply), 4000):
                await message.reply(reply[i : i + 4000])

    async def start(self) -> None:
        await self._dp.start_polling(self._bot)

    async def stop(self) -> None:
        await self._dp.stop_polling()
        await self._bot.session.close()

    async def send(self, recipient: str, text: str) -> None:
        await self._bot.send_message(int(recipient), text)
