"""Anthropic provider — uses the Anthropic SDK with tool use support."""

from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic

from .base import Message, Provider


def _messages_to_anthropic(messages: list[Message]) -> tuple[str, list[dict]]:
    """Split system prompt from conversation messages."""
    system = ""
    api_msgs: list[dict] = []

    for m in messages:
        if m.role == "system":
            system = m.content or ""
            continue

        if m.role == "tool":
            api_msgs.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id,
                            "content": m.content or "",
                        }
                    ],
                }
            )
            continue

        if m.role == "assistant" and m.tool_calls:
            blocks: list[dict] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    args = json.loads(args)
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": args,
                    }
                )
            api_msgs.append({"role": "assistant", "content": blocks})
            continue

        api_msgs.append({"role": m.role, "content": m.content or ""})

    return system, api_msgs


class AnthropicProvider(Provider):
    provider_name = "anthropic"

    def __init__(self, api_key: str, model: str, **_: Any):
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Message:
        system, api_msgs = _messages_to_anthropic(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 8192,
            "messages": api_msgs,
        }
        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"]["description"],
                    "input_schema": t["function"]["parameters"],
                }
                for t in tools
            ]

        resp = await self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    }
                )

        return Message(
            role="assistant",
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls if tool_calls else None,
        )
