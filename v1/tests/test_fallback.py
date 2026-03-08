from __future__ import annotations

import asyncio

from nonail.agent import Agent, _looks_like_rate_limit_error
from nonail.config import Config


def _cfg(tmp_path) -> Config:
    return Config(
        provider="openai",
        model="gpt-4o",
        api_key="test-key",
        cache_enabled=True,
        cache_path=str(tmp_path / "cache.db"),
        cache_mode="aggressive",
        cache_max_entries=5000,
        cache_ttl_seconds=86400,
    )


def test_rate_limit_error_detection_patterns():
    assert _looks_like_rate_limit_error("429 Too Many Requests")
    assert _looks_like_rate_limit_error("RESOURCE_EXHAUSTED: quota exceeded")
    assert _looks_like_rate_limit_error("rate_limit_exceeded")
    assert _looks_like_rate_limit_error("tokens per day (TPD)")
    assert not _looks_like_rate_limit_error("authentication_error invalid API key")


def test_fallback_candidates_prioritize_gemini(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")

    agent = Agent(_cfg(tmp_path))
    candidates = agent._fallback_candidates()

    assert candidates
    assert candidates[0]["provider"] == "gemini"


def test_cache_limit_command_updates_store(tmp_path):
    agent = Agent(_cfg(tmp_path))
    assert agent._cache is not None

    agent._cmd_cache_limit("1200 7200")

    assert agent.config.cache_max_entries == 1200
    assert agent.config.cache_ttl_seconds == 7200
    assert agent._cache.max_entries == 1200
    assert agent._cache.ttl_seconds == 7200


def test_query_llm_target_cache_hit_returns_target_provider(tmp_path):
    agent = Agent(_cfg(tmp_path))
    assert agent._cache is not None

    request_hash = agent._cache.llm_hash(
        provider="gemini",
        model="gemini-2.0-flash",
        messages=agent.history,
    )
    agent._cache.put_llm(
        request_hash=request_hash,
        provider="gemini",
        model="gemini-2.0-flash",
        content="cached",
        tool_calls=None,
    )

    _, llm_cache_hit, _, provider_obj = asyncio.run(
        agent._query_llm_target(
            provider_name="gemini",
            model="gemini-2.0-flash",
            api_key="gemini-key",
            api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
            tool_schemas=[],
            bypass_cache=False,
        )
    )

    assert llm_cache_hit is True
    assert provider_obj.provider_name == "gemini"
