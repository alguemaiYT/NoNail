"""Gemini provider via Google's OpenAI-compatible endpoint."""

from __future__ import annotations

from .openai_provider import OpenAIProvider


class GeminiProvider(OpenAIProvider):
    """Gemini uses an OpenAI-compatible chat completions API surface."""

    provider_name = "gemini"

    def __init__(self, api_key: str, model: str, api_base: str | None = None):
        api_base = api_base or "https://generativelanguage.googleapis.com/v1beta/openai/"
        super().__init__(api_key=api_key, model=model, api_base=api_base)
