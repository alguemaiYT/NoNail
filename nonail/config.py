"""Configuration management for NoNail."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".nonail" / "config.yaml"
DEFAULT_CACHE_PATH = Path.home() / ".nonail" / "cache.db"

DEFAULTS = {
    "provider": "openai",
    "model": "gpt-4o",
    "api_key_env": "NONAIL_API_KEY",
    "system_prompt": """\
You are NoNail, an autonomous AI agent with complete access to this computer.

## ABSOLUTE RULE — NO TEXT BEFORE TOOLS

When the user asks you to DO something (install, run, fix, create, delete, check…):
- Your FIRST response MUST be a tool call. NO text before it.
- NEVER explain what you will do. NEVER list steps. NEVER ask which OS.
- If you need info (like which package manager), get it yourself with a tool call.
- After the task is done, give ONE short sentence confirming the result.

WRONG (never do this):
  User: "install tree"
  You: "I'll check your OS first, then install tree using apt..."

RIGHT (always do this):
  User: "install tree"
  You: [calls package_manager(action='install', packages='tree')]
  You: "Done — tree installed."

## Your tools

- **bash** — Run any shell command.
- **read_file / write_file** — Read or write files.
- **list_directory / search_files / search_text** — Find files and content.
- **make_directory / copy_path / move_path / delete_path** — File system ops.
- **run_python** — Execute Python snippets locally.
- **start_background_command** — Detached long-running processes.
- **http_request / download_file** — HTTP requests and downloads.
- **cron_manage** — Manage cron jobs.
- **process_list / process_kill** — Process management.
- **system_info** — OS, arch, network info.
- **package_manager** — Install/remove/search system packages (auto-detects apt/dnf/pacman/brew).
- **suggest_tool** — Create new custom tools on the fly.
- **exec_terminal** — Open TUI apps (btop, htop, vim…) in a separate terminal window.

## Behaviour

1. **Act first** — Call tools immediately. Text comes AFTER tools finish.
2. **Be autonomous** — Gather info yourself (use system_info, bash, etc.). Don't ask the user for things you can look up.
3. **Chain tools** — Complete tasks end-to-end: act, verify, report.
4. **Handle errors** — If a tool fails, diagnose and retry automatically.
5. **Use exec_terminal** for TUI apps — btop, htop, vim open in separate window.

Respond in the same language the user writes in. Be extremely concise.\
    """,
    "max_iterations": 25,
    "mcp_server": {"enabled": True, "transport": "stdio"},
    "cache": {
        "enabled": True,
        "path": str(DEFAULT_CACHE_PATH),
        "mode": "aggressive",
        "max_entries": 5000,
        "ttl_seconds": 86400,
    },
}

DEFAULT_API_KEY_ENV_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


@dataclass
class Config:
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = ""
    api_key_env: str = DEFAULTS["api_key_env"]
    api_base: str | None = None
    system_prompt: str = DEFAULTS["system_prompt"]
    max_iterations: int = 25
    mcp_transport: str = "stdio"
    mcp_enabled: bool = True
    cache_enabled: bool = True
    cache_path: str = str(DEFAULT_CACHE_PATH)
    cache_mode: str = "aggressive"
    cache_max_entries: int = 5000
    cache_ttl_seconds: int = 86400
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        data: dict = {}
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}

        provider = data.get("provider", DEFAULTS["provider"])
        api_key_env = data.get("api_key_env") or DEFAULT_API_KEY_ENV_BY_PROVIDER.get(
            provider, DEFAULTS["api_key_env"]
        )
        api_key = data.get("api_key", "")
        if not api_key:
            env_candidates = [api_key_env, DEFAULTS["api_key_env"]]
            for env_name in env_candidates:
                api_key = os.environ.get(env_name, "")
                if api_key:
                    break

        mcp = data.get("mcp_server", {})
        cache = data.get("cache", {})
        cache_mode = cache.get("mode", DEFAULTS["cache"]["mode"])
        if cache_mode not in {"aggressive", "safe", "off"}:
            cache_mode = DEFAULTS["cache"]["mode"]

        return cls(
            provider=provider,
            model=data.get("model", DEFAULTS["model"]),
            api_key=api_key,
            api_key_env=api_key_env,
            api_base=data.get("api_base"),
            system_prompt=data.get("system_prompt", DEFAULTS["system_prompt"]),
            max_iterations=data.get("max_iterations", DEFAULTS["max_iterations"]),
            mcp_transport=mcp.get("transport", "stdio"),
            mcp_enabled=mcp.get("enabled", True),
            cache_enabled=cache.get("enabled", DEFAULTS["cache"]["enabled"]),
            cache_path=cache.get("path", DEFAULTS["cache"]["path"]),
            cache_mode=cache_mode,
            cache_max_entries=cache.get("max_entries", DEFAULTS["cache"]["max_entries"]),
            cache_ttl_seconds=cache.get("ttl_seconds", DEFAULTS["cache"]["ttl_seconds"]),
            extra=data,
        )

    def save(self, path: str | Path | None = None) -> None:
        path = Path(path) if path else DEFAULT_CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        dump = {
            "provider": self.provider,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "api_base": self.api_base,
            "system_prompt": self.system_prompt,
            "max_iterations": self.max_iterations,
            "mcp_server": {
                "enabled": self.mcp_enabled,
                "transport": self.mcp_transport,
            },
            "cache": {
                "enabled": self.cache_enabled,
                "path": self.cache_path,
                "mode": self.cache_mode,
                "max_entries": self.cache_max_entries,
                "ttl_seconds": self.cache_ttl_seconds,
            },
        }
        with open(path, "w") as f:
            yaml.safe_dump(dump, f, default_flow_style=False)
        # Restrict permissions — file may reference sensitive env vars
        path.chmod(0o600)
