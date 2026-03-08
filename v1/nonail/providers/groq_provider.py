"""Groq provider — OpenAI-compatible high-speed LLM inference."""

from __future__ import annotations

from .openai_provider import OpenAIProvider


class GroqProvider(OpenAIProvider):
    """Groq is OpenAI-compatible, just swap the API base."""

    provider_name = "groq"

    def __init__(self, api_key: str, model: str, api_base: str | None = None):
        api_base = api_base or "https://api.groq.com/openai/v1"
        super().__init__(api_key=api_key, model=model, api_base=api_base)
