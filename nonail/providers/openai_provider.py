"""OpenAI-compatible provider (works with OpenAI, OpenRouter, local APIs)."""

from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from .base import Message, Provider


class OpenAIProvider(Provider):
    provider_name = "openai"

    def __init__(self, api_key: str, model: str, api_base: str | None = None):
        kwargs: dict[str, Any] = {"api_key": api_key}
        if api_base:
            kwargs["base_url"] = api_base
        self._client = AsyncOpenAI(**kwargs)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Message:
        api_msgs = []
        for m in messages:
            entry: dict[str, Any] = {"role": m.role}
            if m.content is not None:
                entry["content"] = m.content
            if m.tool_calls is not None:
                entry["tool_calls"] = m.tool_calls
            if m.tool_call_id is not None:
                entry["tool_call_id"] = m.tool_call_id
            if m.name is not None:
                entry["name"] = m.name
            api_msgs.append(entry)

        kwargs: dict[str, Any] = {"model": self._model, "messages": api_msgs}
        if tools:
            kwargs["tools"] = tools

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        return Message(
            role="assistant",
            content=msg.content,
            tool_calls=tool_calls,
        )
