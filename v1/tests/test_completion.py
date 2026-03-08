from __future__ import annotations

from nonail.agent import Agent
from nonail.config import Config


def _cfg(tmp_path) -> Config:
    return Config(
        provider="openai",
        model="gpt-4o",
        api_key="test-key",
        cache_enabled=True,
        cache_path=str(tmp_path / "cache.db"),
    )


def test_tab_completion_only_when_line_starts_with_slash(tmp_path):
    agent = Agent(_cfg(tmp_path))

    assert agent._completion_candidates("install tree", "install", 0) == []
    assert agent._completion_candidates("echo /model", "/m", 5) == []

    root_matches = agent._completion_candidates("/mo", "/mo", 0)
    assert "/model" in root_matches


def test_model_completion_suggests_known_models(tmp_path):
    agent = Agent(_cfg(tmp_path))
    agent._store_model_completion_candidates(["gpt-4o-mini", "gpt-4.1"])

    matches = agent._completion_candidates("/model gpt-4", "gpt-4", len("/model "))
    assert "gpt-4o-mini" in matches
    assert "gpt-4.1" in matches
