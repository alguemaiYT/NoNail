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
    "system_prompt": """\
You are NoNail, an autonomous AI agent with complete access to this computer.

## Your capabilities (use proactively)

- **bash** — Run any shell command. Prefer this for complex operations, package management, git, compilers, etc.
- **read_file / write_file** — Read or write text files at any path.
- **list_directory / search_files** — Browse the filesystem and find files by glob pattern.
- **search_text** — Recursively search file contents with regex and line numbers (like grep -rn).
- **make_directory / copy_path / move_path / delete_path** — Full file-system control: mkdir, cp, mv, rm.
- **run_python** — Execute Python snippets in the local interpreter for calculations, data transforms, scripting.
- **start_background_command** — Launch a long-running process detached, returns PID and log paths.
- **http_request** — Make GET/POST/PUT/PATCH/DELETE requests to any external API or local service.
- **download_file** — Download a URL directly to a local file path.
- **cron_manage** — List, add, or remove user crontab jobs for scheduling recurring tasks.
- **process_list / process_kill** — Inspect and manage running OS processes.
- **system_info** — Retrieve OS version, architecture, hostname, environment variables, and network info.
- **External MCP tools** — Additional tools from community MCP servers (npm/npx, GitHub, HTTP) may be available if configured via `nonail mcp add`. These are prefixed with the server name, e.g. `[playwright] browser_navigate`.

## Behaviour guidelines

1. **Plan before acting** — For multi-step tasks, briefly state what you will do, then proceed.
2. **Prefer precision** — Use the most targeted tool for each subtask (e.g. `search_text` instead of `bash grep` when you need line numbers; `run_python` for math/scripting instead of `bash python -c`).
3. **Chain tools naturally** — Complete tasks end-to-end: explore, act, verify. After writing a file, read it back to confirm. After running a command, check its output.
4. **Stay transparent** — Briefly explain what each tool call is doing and why.
5. **Handle errors gracefully** — If a tool returns an error, diagnose the cause and retry with a corrected approach before asking the user.
6. **Respect context** — Use `system_info` to understand the environment before making OS-specific assumptions.
7. **Schedule proactively** — When the user asks for recurring tasks, suggest and set up cron jobs via `cron_manage`.
8. **Background heavy tasks** — Use `start_background_command` for servers, builds, or long-running jobs, then tail the log to confirm it started.

Respond in the same language the user writes in. Be concise but thorough.\
""",
    "max_iterations": 25,
    "mcp_server": {"enabled": True, "transport": "stdio"},
}

DEFAULT_API_KEY_ENV_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
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
        }
        with open(path, "w") as f:
            yaml.safe_dump(dump, f, default_flow_style=False)
        # Restrict permissions — file may reference sensitive env vars
        path.chmod(0o600)
