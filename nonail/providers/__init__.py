"""Provider registry — swap LLM backends via configuration."""

from __future__ import annotations

from .base import Message, Provider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider

PROVIDERS: dict[str, type[Provider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def create_provider(
    name: str, api_key: str, model: str, api_base: str | None = None
) -> Provider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown provider '{name}'. Available: {list(PROVIDERS.keys())}"
        )
    return cls(api_key=api_key, model=model, api_base=api_base)


__all__ = [
    "Provider",
    "Message",
    "OpenAIProvider",
    "AnthropicProvider",
    "PROVIDERS",
    "create_provider",
]
