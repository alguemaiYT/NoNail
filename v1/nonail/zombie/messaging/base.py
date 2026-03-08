"""Abstract base for messaging bot integrations (Telegram, WhatsApp, Discord)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable


# Callback signature: async (sender_id: str, text: str) -> str
CommandCallback = Callable[[str, str], Awaitable[str]]


class MessagingBot(ABC):
    """Base class for all Zombie Mode messaging integrations."""

    name: str = "base"

    def __init__(self, config: dict[str, Any], on_command: CommandCallback):
        self.config = config
        self.on_command = on_command

    @abstractmethod
    async def start(self) -> None:
        """Start the bot (blocking — run in a task)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the bot."""
        ...

    @abstractmethod
    async def send(self, recipient: str, text: str) -> None:
        """Send a message to a specific recipient/channel."""
        ...

    def is_allowed(self, sender_id: str) -> bool:
        """Check if the sender is in the whitelist.  Empty list = allow all."""
        allowed = self.config.get("allowed_users") or self.config.get("allowed_numbers") or []
        if not allowed:
            return True
        return str(sender_id) in [str(a) for a in allowed]
