"""Configuration management for NoNail."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".nonail" / "config.yaml"

DEFAULTS = {
    "provider": "openai",
    "model": "gpt-4o",
    "api_key_env": "NONAIL_API_KEY",
    "system_prompt": (
        "You are NoNail, a powerful AI agent with full access to this computer. "
        "You can run shell commands, read/write files, manage processes, and "
        "query system information. Be helpful, precise, and safe."
    ),
    "max_iterations": 25,
    "mcp_server": {"enabled": True, "transport": "stdio"},
}


@dataclass
class Config:
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    api_base: str | None = None
    system_prompt: str = DEFAULTS["system_prompt"]
    max_iterations: int = 25
    mcp_transport: str = "stdio"
    mcp_enabled: bool = True
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        data: dict = {}
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}

        api_key = data.get("api_key", "") or os.environ.get(
            data.get("api_key_env", DEFAULTS["api_key_env"]), ""
        )

        mcp = data.get("mcp_server", {})

        return cls(
            provider=data.get("provider", DEFAULTS["provider"]),
            model=data.get("model", DEFAULTS["model"]),
            api_key=api_key,
            api_base=data.get("api_base"),
            system_prompt=data.get("system_prompt", DEFAULTS["system_prompt"]),
            max_iterations=data.get("max_iterations", DEFAULTS["max_iterations"]),
            mcp_transport=mcp.get("transport", "stdio"),
            mcp_enabled=mcp.get("enabled", True),
            extra=data,
        )

    def save(self, path: str | Path | None = None) -> None:
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        dump = {
            "provider": self.provider,
            "model": self.model,
            "api_base": self.api_base,
            "system_prompt": self.system_prompt,
            "max_iterations": self.max_iterations,
            "mcp_server": {
                "enabled": self.mcp_enabled,
                "transport": self.mcp_transport,
            },
        }
        with open(path, "w") as f:
            yaml.safe_dump(dump, f, default_flow_style=False)
