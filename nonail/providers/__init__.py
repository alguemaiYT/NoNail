"""Provider registry — swap LLM backends via configuration.

Provider modules are imported lazily so that unused SDK libraries
(openai, anthropic, google-generativeai, groq) are never loaded.
"""

from __future__ import annotations

from .base import Message, Provider

PROVIDERS: dict[str, str] = {
    "openai": "openai_provider.OpenAIProvider",
    "anthropic": "anthropic_provider.AnthropicProvider",
    "groq": "groq_provider.GroqProvider",
    "gemini": "gemini_provider.GeminiProvider",
}


def _import_provider_class(name: str) -> type[Provider]:
    """Import a provider class on demand."""
    module_attr = PROVIDERS.get(name)
    if module_attr is None:
        raise ValueError(
            f"Unknown provider '{name}'. Available: {list(PROVIDERS.keys())}"
        )
    module_name, class_name = module_attr.rsplit(".", 1)
    import importlib

    mod = importlib.import_module(f".{module_name}", package=__package__)
    return getattr(mod, class_name)


def create_provider(
    name: str, api_key: str, model: str, api_base: str | None = None
) -> Provider:
    cls = _import_provider_class(name)
    return cls(api_key=api_key, model=model, api_base=api_base)


__all__ = [
    "Provider",
    "Message",
    "PROVIDERS",
    "create_provider",
]
