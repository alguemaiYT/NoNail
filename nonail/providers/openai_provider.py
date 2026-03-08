"""OpenAI-compatible provider (works with OpenAI, OpenRouter, local APIs)."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from openai import AsyncOpenAI, BadRequestError

from .base import Message, Provider


# ---------------------------------------------------------------------------
# Regex patterns to catch text-based tool calls emitted by some models
# (e.g. Llama, Mixtral, DeepSeek) that don't always use the structured
# tool_calls API field.
# ---------------------------------------------------------------------------

# <function/tool_name>{"key": "value"} or <function/tool_name>({"key": "value"})
_FUNC_TAG_RE = re.compile(
    r"<function/(\w+)>\s*\(?\s*(\{.*?\})\s*\)?\s*>?",
    re.DOTALL,
)
# ```tool_call\n{"name":"...", "arguments":{...}}\n```
_FENCED_RE = re.compile(
    r"```(?:tool_call|json)?\s*\n(\{.*?\})\s*\n```",
    re.DOTALL,
)


def _extract_text_tool_calls(content: str) -> tuple[list[dict] | None, str]:
    """Try to extract tool calls embedded as text in the response content.

    Returns ``(tool_calls_list_or_None, cleaned_content)``.
    """
    calls: list[dict] = []

    # Pattern 1: <function/name>{...}
    for m in _FUNC_TAG_RE.finditer(content):
        fn_name = m.group(1)
        try:
            args = json.loads(m.group(2))
        except json.JSONDecodeError:
            continue
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": fn_name,
                "arguments": json.dumps(args),
            },
        })

    # Pattern 2: fenced json blocks with name+arguments
    if not calls:
        for m in _FENCED_RE.finditer(content):
            try:
                obj = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            if "name" in obj and "arguments" in obj:
                args = obj["arguments"]
                calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": obj["name"],
                        "arguments": json.dumps(args) if not isinstance(args, str) else args,
                    },
                })

    if not calls:
        return None, content

    # Remove matched spans from content so the user sees clean text
    cleaned = content
    for m in _FUNC_TAG_RE.finditer(content):
        cleaned = cleaned.replace(m.group(0), "")
    for m in _FENCED_RE.finditer(content):
        cleaned = cleaned.replace(m.group(0), "")
    cleaned = cleaned.strip()

    return calls, cleaned


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

        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            # Some OpenAI-compatible providers (e.g. Groq + certain models) can
            # fail tool parsing with `tool_use_failed`. Retry once without tools
            # so conversational requests still succeed instead of crashing.
            if tools and ("tool_use_failed" in str(exc) or "failed_generation" in str(exc)):
                retry_kwargs = dict(kwargs)
                retry_kwargs.pop("tools", None)
                resp = await self._client.chat.completions.create(**retry_kwargs)
            else:
                raise
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

        content = msg.content

        # Fallback: some models (Llama, Mixtral, …) emit tool calls as plain
        # text instead of using the structured tool_calls field.  Parse them.
        if not tool_calls and content:
            parsed, content = _extract_text_tool_calls(content)
            if parsed:
                tool_calls = parsed
                content = content or None

        return Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
        )

    async def list_models(self) -> list[dict]:
        """Fetch available models from the OpenAI-compatible /v1/models endpoint."""
        try:
            page = await self._client.models.list()
            models = []
            for m in page.data:
                models.append({
                    "id": m.id,
                    "owned_by": getattr(m, "owned_by", None),
                })
            models.sort(key=lambda x: x["id"])
            return models
        except Exception:
            return []
