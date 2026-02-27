"""Base interface for LLM providers — inspired by ZeroClaw's Provider trait."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class Provider(ABC):
    """Swappable LLM backend — change provider without touching agent logic."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Message:
        """Send messages (with optional tool schemas) and get a response."""
        ...
