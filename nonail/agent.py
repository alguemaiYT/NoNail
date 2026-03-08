"""Core agent loop — orchestrates LLM ↔ tools conversation.

Inspired by Claude Code, Gemini CLI, and GitHub Copilot CLI for
the interactive REPL experience with slash-command support.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .ui import cprint, cinput, print_table, print_panel, print_rule

from .cache import CacheStore
from .config import Config, DEFAULT_API_KEY_ENV_BY_PROVIDER, DEFAULT_CONFIG_PATH
from .fastpath import contains_any, prefix_matches
from .providers import PROVIDERS, Message, create_provider
from .tools import ALL_TOOLS, load_custom_tools, save_custom_tool, remove_custom_tool
from .tools.dynamic import DynamicTool, SuggestToolTool
from .tools.packages import PackageManagerTool

SAFE_CACHE_TOOLS = {
    "read_file",
    "list_directory",
    "search_files",
    "search_text",
    "system_info",
    "process_list",
}

RATE_LIMIT_PATTERNS = (
    "rate_limit_exceeded",
    "rate limit",
    "too many requests",
    "resource_exhausted",
    "quota exceeded",
    "insufficient_quota",
    "tokens per day",
    "tpm",
    "rpm",
    "429",
)

FALLBACK_MODEL_DEFAULTS = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "groq": "llama-3.1-8b-instant",
}

FALLBACK_API_BASES = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}

SLASH_COMMANDS = (
    "/help",
    "/tools",
    "/model",
    "/provider",
    "/config",
    "/history",
    "/clear",
    "/status",
    "/compact",
    "/mcp",
    "/cache",
    "/cache-limit",
    "/yolo",
    "/allow",
    "/reset-prompt",
    "/quit",
    "/exit",
)


def _looks_like_rate_limit_error(exc: Exception | str) -> bool:
    return contains_any(str(exc).lower(), RATE_LIMIT_PATTERNS)


# ---------------------------------------------------------------------------
# Terminal UI helpers
# ---------------------------------------------------------------------------


def _arrow_select(options: list[str]) -> int:
    """Interactive arrow-key menu rendered inline in the terminal.

    Returns the index of the chosen option, or -1 if the user pressed Ctrl+C.
    Works only when stdin is a real TTY; falls back to 0 (first option) otherwise.
    """
    import termios
    import tty

    if not sys.stdin.isatty():
        return 0

    selected = 0
    n = len(options)

    def _draw(first: bool = False) -> None:
        if not first:
            # Move cursor up n lines to overwrite previous draw
            sys.stdout.write(f"\033[{n}A")
        for i, opt in enumerate(options):
            # Erase entire line, then write option
            sys.stdout.write("\033[2K\r")
            if i == selected:
                sys.stdout.write(f"  \033[1;36m❯ {opt}\033[0m")
            else:
                sys.stdout.write(f"    \033[2m{opt}\033[0m")
            if i < n - 1:
                sys.stdout.write("\r\n")
        sys.stdout.write("\r\n")
        sys.stdout.flush()

    _draw(first=True)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1)
            if ch in (b"\r", b"\n"):
                break
            if ch == b"\x03":  # Ctrl+C → deny
                selected = -1
                break
            if ch == b"\x1b":
                rest = os.read(fd, 2)
                if rest == b"[A":  # Up
                    selected = (selected - 1) % n
                elif rest == b"[B":  # Down
                    selected = (selected + 1) % n
                else:
                    continue
                _draw()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return selected


def _modify_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Let the user edit tool arguments interactively before execution."""
    new_args = dict(args)
    cprint("  [dim]Edit args (Enter to keep current value):[/dim]")
    for key, val in args.items():
        if isinstance(val, str):
            cprint(f"    [dim]{key}:[/dim] [cyan]{val}[/cyan]")
            try:
                new_val = cinput(
                    f"  [nn.info]  {key}: [/nn.info]"
                ).strip()
                if new_val:
                    new_args[key] = new_val
            except (EOFError, KeyboardInterrupt):
                pass
        else:
            serialised = json.dumps(val)
            cprint(f"    [dim]{key}:[/dim] [cyan]{serialised}[/cyan]")
            try:
                new_val = cinput(
                    f"  [nn.info]  {key} (JSON): [/nn.info]"
                ).strip()
                if new_val:
                    try:
                        new_args[key] = json.loads(new_val)
                    except json.JSONDecodeError:
                        new_args[key] = new_val
            except (EOFError, KeyboardInterrupt):
                pass
    return new_args


# ---------------------------------------------------------------------------
# Readline helpers  (arrow keys, cursor movement, persistent history)
# ---------------------------------------------------------------------------

_RL_HIST = Path.home() / ".nonail" / "history"


def _setup_readline():
    """Enable readline for the REPL (arrow keys, cursor movement, history).

    Returns the readline module or None if unavailable.
    """
    try:
        import readline as _rl  # noqa: PLC0415

        if _RL_HIST.exists():
            _rl.read_history_file(str(_RL_HIST))
        _rl.set_history_length(500)
        return _rl
    except (ImportError, OSError):
        return None


def _save_readline(_rl) -> None:
    """Persist readline history to disk."""
    if _rl is None:
        return
    try:
        _RL_HIST.parent.mkdir(parents=True, exist_ok=True)
        _rl.write_history_file(str(_RL_HIST))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    """NoNail agent — connects an LLM provider to local + external MCP tools."""

    def __init__(self, config: Config):
        self.config = config
        self.provider = create_provider(
            name=config.provider,
            api_key=config.api_key,
            model=config.model,
            api_base=config.api_base,
        )
        self.tools: list = list(ALL_TOOLS)
        self._tools_by_name: dict[str, Any] = {t.name: t for t in self.tools}
        self._mcp_manager = None
        self.history: list[Message] = [
            Message(role="system", content=config.system_prompt)
        ]
        self._model_completion_cache: dict[str, list[str]] = {
            config.provider: [config.model]
        }
        self._tool_call_count = 0
        self._start_time = time.time()
        self.yolo: bool = False  # /yolo — skip per-tool approval prompts
        self._cache_bypass_once: bool = False
        self._active_run_id: str | None = None
        self._cache: CacheStore | None = None
        if self.config.cache_enabled:
            try:
                self._cache = CacheStore(
                    self.config.cache_path,
                    max_entries=self.config.cache_max_entries,
                    ttl_seconds=self.config.cache_ttl_seconds,
                )
            except Exception as exc:
                cprint(f"[nn.error]Cache disabled: {exc}[/nn.error]")
                self.config.cache_enabled = False
        self._setup_approval_callbacks()

    # ------------------------------------------------------------------
    # External MCP
    # ------------------------------------------------------------------

    async def _load_external_tools(self) -> None:
        from .mcp_client import MCPClientManager, load_servers

        servers = load_servers()
        if not servers:
            return
        manager = MCPClientManager()
        external_tools = await manager.connect_all(servers)
        if external_tools:
            self._mcp_manager = manager
            self.tools.extend(external_tools)
            self._tools_by_name = {t.name: t for t in self.tools}

    def _load_custom_tools(self) -> None:
        """Load user-defined YAML tools from ~/.nonail/custom-tools/."""
        custom = load_custom_tools()
        if custom:
            self.tools.extend(custom)
            self._tools_by_name = {t.name: t for t in self.tools}

    def _setup_approval_callbacks(self) -> None:
        """Wire approval prompts for package_manager and suggest_tool."""
        for tool in self.tools:
            if isinstance(tool, PackageManagerTool):
                tool.approval_callback = self._approve_package_action
            elif isinstance(tool, SuggestToolTool):
                tool.approval_callback = self._approve_tool_suggestion

    async def _approve_package_action(self, message: str) -> bool:
        """Show package install/remove approval prompt."""
        print_panel(message, title="🔧 Package Manager")
        try:
            answer = cinput("  Proceed? [Y/n] › ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in ("", "y", "yes")

    async def _approve_tool_suggestion(self, spec: dict[str, Any]) -> bool:
        """Show tool suggestion panel and get user decision."""
        lines = []
        lines.append(f"Name:    {spec['name']}")
        lines.append(f"Desc:    {spec.get('description', '')}")
        lines.append(f"Type:    {spec.get('type', 'shell')}")
        if spec.get("command_template"):
            lines.append(f"Command: {spec['command_template']}")
        if spec.get("python_code"):
            lines.append(f"Code:    {spec['python_code'][:100]}...")
        if spec.get("requires"):
            lines.append(f"Requires: {', '.join(spec['requires'])}")
        if spec.get("parameters"):
            lines.append("\nParameters:")
            for pname, pdef in spec["parameters"].items():
                desc = pdef.get("description", "")
                ptype = pdef.get("type", "string")
                lines.append(f"  • {pname} ({ptype}): {desc}")
        lines.append("\n[A]pprove  [E]dit  [R]eject")

        print_panel("\n".join(lines), title="🧩 Tool Suggestion")
        try:
            choice = cinput("  Choice › ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False

        if choice in ("a", "approve"):
            path = save_custom_tool(spec)
            new_tool = DynamicTool(spec, source_path=path)
            self.tools.append(new_tool)
            self._tools_by_name[new_tool.name] = new_tool
            cprint(f"  ✓ Tool '{spec['name']}' saved to {path} and loaded.")
            return True
        elif choice in ("e", "edit"):
            cprint("  Edit the YAML spec (Ctrl+D to finish):")
            import yaml as _yaml
            cprint(_yaml.safe_dump(spec, default_flow_style=False))
            cprint("  (Editing not yet implemented — saving as-is)")
            path = save_custom_tool(spec)
            new_tool = DynamicTool(spec, source_path=path)
            self.tools.append(new_tool)
            self._tools_by_name[new_tool.name] = new_tool
            cprint(f"  ✓ Tool '{spec['name']}' saved and loaded.")
            return True
        else:
            cprint("  Tool suggestion rejected.")
            return False

    def _store_model_completion_candidates(self, model_ids: list[str]) -> None:
        provider_name = self.config.provider
        merged: list[str] = []
        for model_id in [*self._model_completion_cache.get(provider_name, []), *model_ids]:
            value = (model_id or "").strip()
            if value and value not in merged:
                merged.append(value)
        if self.config.model and self.config.model not in merged:
            merged.insert(0, self.config.model)
        self._model_completion_cache[provider_name] = merged[:200]

    def _model_completion_candidates(self) -> list[str]:
        candidates = ["list", "select", self.config.model]
        fallback_model = FALLBACK_MODEL_DEFAULTS.get(self.config.provider)
        if fallback_model:
            candidates.append(fallback_model)
        candidates.extend(self._model_completion_cache.get(self.config.provider, []))
        merged: list[str] = []
        for value in candidates:
            value = value.strip()
            if value and value not in merged:
                merged.append(value)
        return merged

    def _completion_candidates(
        self,
        line_buffer: str,
        text: str,
        begidx: int,
    ) -> list[str]:
        if not line_buffer.startswith("/"):
            return []
        if begidx == 0:
            return prefix_matches(text, SLASH_COMMANDS)

        command = line_buffer.split(None, 1)[0].lower()
        if command == "/model":
            return prefix_matches(text, self._model_completion_candidates())
        if command == "/provider":
            return prefix_matches(text, list(PROVIDERS.keys()))
        if command == "/cache":
            return prefix_matches(text, ["status", "clear", "mode", "bypass"])
        return []

    def _configure_readline_completion(self, _rl) -> None:
        if _rl is None:
            return

        def _completer(text: str, state: int) -> str | None:
            line_buffer = _rl.get_line_buffer()
            begidx = _rl.get_begidx()
            candidates = self._completion_candidates(line_buffer, text, begidx)
            if state < len(candidates):
                return candidates[state]
            return None

        _rl.set_completer_delims(" \t\n")
        _rl.set_completer(_completer)
        _rl.parse_and_bind("tab: complete")

    def _set_model(self, model: str) -> None:
        old = self.config.model
        self.config.model = model
        self.provider = create_provider(
            name=self.config.provider,
            api_key=self.config.api_key,
            model=self.config.model,
            api_base=self.config.api_base,
        )
        self._store_model_completion_candidates([model])
        cprint(f"[nn.agent]  ✓ Model switched: {old} → {model}[/nn.agent]")

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def _cache_enabled(self) -> bool:
        return bool(
            self._cache
            and self.config.cache_enabled
            and self.config.cache_mode in {"aggressive", "safe"}
        )

    def _tool_cache_allowed(self, tool_name: str) -> bool:
        if not self._cache_enabled():
            return False
        if self.config.cache_mode == "aggressive":
            return True
        return tool_name in SAFE_CACHE_TOOLS

    def _fallback_candidates(self) -> list[dict[str, str | None]]:
        """Return fallback providers in priority order based on available keys."""
        order = ("gemini", "anthropic", "openai", "groq")
        current_key = (
            self.config.provider,
            self.config.model,
            self.config.api_base or "",
        )
        candidates: list[dict[str, str | None]] = []

        for provider_name in order:
            if provider_name not in PROVIDERS:
                continue
            env_name = DEFAULT_API_KEY_ENV_BY_PROVIDER.get(provider_name, "")
            if not env_name:
                continue
            api_key = os.environ.get(env_name, "")
            if not api_key:
                continue

            model = os.environ.get(
                f"NONAIL_{provider_name.upper()}_FALLBACK_MODEL",
                FALLBACK_MODEL_DEFAULTS.get(provider_name, self.config.model),
            )
            api_base = FALLBACK_API_BASES.get(provider_name)
            candidate_key = (provider_name, model, api_base or "")
            if candidate_key == current_key:
                continue
            candidates.append(
                {
                    "provider": provider_name,
                    "model": model,
                    "api_key": api_key,
                    "api_key_env": env_name,
                    "api_base": api_base,
                }
            )
        return candidates

    async def _query_llm_target(
        self,
        *,
        provider_name: str,
        model: str,
        api_key: str,
        api_base: str | None,
        tool_schemas: list[dict[str, Any]],
        bypass_cache: bool,
    ) -> tuple[Message, bool, str | None, Any]:
        """Get one LLM response for a specific provider/model target."""
        llm_cache_hit = False
        request_hash: str | None = None

        if self._cache_enabled() and self._cache and not bypass_cache:
            request_hash = self._cache.llm_hash(
                provider=provider_name,
                model=model,
                messages=self.history,
            )
            llm_cached = self._cache.get_llm(request_hash)
            if llm_cached is not None:
                llm_cache_hit = True
                cached_content, cached_tool_calls = llm_cached
                provider_obj = (
                    self.provider
                    if (
                        provider_name == self.config.provider
                        and model == self.config.model
                        and (api_base or "") == (self.config.api_base or "")
                        and api_key == self.config.api_key
                    )
                    else create_provider(
                        name=provider_name,
                        api_key=api_key,
                        model=model,
                        api_base=api_base,
                    )
                )
                return (
                    Message(
                        role="assistant",
                        content=cached_content,
                        tool_calls=cached_tool_calls,
                    ),
                    llm_cache_hit,
                    request_hash,
                    provider_obj,
                )

        if (
            provider_name == self.config.provider
            and model == self.config.model
            and (api_base or "") == (self.config.api_base or "")
            and api_key == self.config.api_key
        ):
            provider_obj = self.provider
        else:
            provider_obj = create_provider(
                name=provider_name,
                api_key=api_key,
                model=model,
                api_base=api_base,
            )

        response = await provider_obj.chat(self.history, tools=tool_schemas)

        if self._cache_enabled() and self._cache and not bypass_cache:
            if request_hash is None:
                request_hash = self._cache.llm_hash(
                    provider=provider_name,
                    model=model,
                    messages=self.history,
                )
            self._cache.put_llm(
                request_hash=request_hash,
                provider=provider_name,
                model=model,
                content=response.content,
                tool_calls=response.tool_calls,
            )

        return response, llm_cache_hit, request_hash, provider_obj

    async def _query_llm_with_fallback(
        self,
        *,
        tool_schemas: list[dict[str, Any]],
        bypass_cache: bool,
        run_id: str | None,
        iteration: int,
    ) -> tuple[Message, bool, str | None, str, str, bool]:
        """Query current provider and fallback on rate-limit/quota errors."""
        try:
            response, llm_cache_hit, request_hash, provider_obj = await self._query_llm_target(
                provider_name=self.config.provider,
                model=self.config.model,
                api_key=self.config.api_key,
                api_base=self.config.api_base,
                tool_schemas=tool_schemas,
                bypass_cache=bypass_cache,
            )
            if provider_obj is not self.provider:
                self.provider = provider_obj
            return (
                response,
                llm_cache_hit,
                request_hash,
                self.config.provider,
                self.config.model,
                False,
            )
        except Exception as exc:
            if not _looks_like_rate_limit_error(exc):
                raise

            if run_id and self._cache:
                self._cache.add_event(
                    run_id=run_id,
                    iteration=iteration,
                    actor="system",
                    event_type="fallback_trigger",
                    payload={
                        "provider": self.config.provider,
                        "model": self.config.model,
                        "reason": "rate_limit",
                    },
                )

            for candidate in self._fallback_candidates():
                provider_name = (candidate["provider"] or "").strip()
                model = (candidate["model"] or "").strip()
                api_key = candidate["api_key"] or ""
                api_base = candidate["api_base"]
                try:
                    response, llm_cache_hit, request_hash, provider_obj = await self._query_llm_target(
                        provider_name=provider_name,
                        model=model,
                        api_key=api_key,
                        api_base=api_base,
                        tool_schemas=tool_schemas,
                        bypass_cache=bypass_cache,
                    )

                    self.config.provider = provider_name
                    self.config.model = model
                    self.config.api_key = api_key
                    self.config.api_key_env = candidate["api_key_env"] or self.config.api_key_env
                    self.config.api_base = api_base
                    self.provider = provider_obj

                    cprint(
                        f"  [nn.info]Rate limit detectado. Fallback para "
                        f"[cyan]{provider_name}[/cyan]/[cyan]{model}[/cyan].[/nn.info]"
                    )

                    if run_id and self._cache:
                        self._cache.add_event(
                            run_id=run_id,
                            iteration=iteration,
                            actor="system",
                            event_type="fallback_success",
                            payload={
                                "provider": provider_name,
                                "model": model,
                            },
                        )

                    return (
                        response,
                        llm_cache_hit,
                        request_hash,
                        provider_name,
                        model,
                        True,
                    )
                except Exception as fallback_exc:
                    if run_id and self._cache:
                        self._cache.add_event(
                            run_id=run_id,
                            iteration=iteration,
                            actor="system",
                            event_type="fallback_failed",
                            payload={
                                "provider": provider_name,
                                "model": model,
                                "rate_limited": _looks_like_rate_limit_error(fallback_exc),
                            },
                        )
                    continue

            raise RuntimeError(
                "Limite de uso atingido no modelo atual e nenhum fallback disponível. "
                "Configure GEMINI_API_KEY (recomendado) ou outra chave de provedor."
            ) from None

    def _prompt_tool_approval(
        self, fn_name: str, args: dict[str, Any]
    ) -> tuple[bool, dict[str, Any]]:
        """Show approval prompt for a tool call.

        Returns ``(approved, final_args)``.  ``final_args`` may differ from
        ``args`` when the user chooses *Modify*.
        """
        args_display = ", ".join(f"{k}={v!r}" for k, v in args.items())
        cprint(f"\n  [nn.tool]⚙ {fn_name}({args_display})[/nn.tool]")

        idx = _arrow_select(["Approve", "Modify", "Deny"])

        if idx == 0:  # Approve
            return (True, args)
        elif idx == 1:  # Modify
            args = _modify_tool_args(args)
            return (True, args)
        else:  # Deny or Ctrl+C
            cprint("  [nn.dim]  ✗ Denied[/nn.dim]")
            return (False, args)

    async def step(self, user_input: str) -> str:
        self.history.append(Message(role="user", content=user_input))
        tool_schemas = [t.to_openai_schema() for t in self.tools]
        bypass_cache = self._cache_bypass_once
        self._cache_bypass_once = False

        run_id: str | None = None
        if self._cache_enabled() and self._cache:
            run_id = self._cache.start_run(
                provider=self.config.provider,
                model=self.config.model,
                cwd=os.getcwd(),
            )
            self._active_run_id = run_id
            self._cache.add_event(
                run_id=run_id,
                iteration=0,
                actor="user",
                event_type="prompt",
                payload={"content": user_input, "bypass_cache": bypass_cache},
            )

        try:
            for iteration in range(self.config.max_iterations):
                (
                    response,
                    llm_cache_hit,
                    request_hash,
                    response_provider,
                    response_model,
                    fallback_used,
                ) = await self._query_llm_with_fallback(
                    tool_schemas=tool_schemas,
                    bypass_cache=bypass_cache,
                    run_id=run_id,
                    iteration=iteration,
                )

                self.history.append(response)

                if run_id and self._cache:
                    self._cache.add_event(
                        run_id=run_id,
                        iteration=iteration,
                        actor="assistant",
                        event_type="decision",
                        payload={
                            "cache_hit": llm_cache_hit,
                            "request_hash": request_hash,
                            "provider": response_provider,
                            "model": response_model,
                            "fallback_used": fallback_used,
                            "content": response.content,
                            "tool_calls": response.tool_calls,
                        },
                    )

                if not response.tool_calls:
                    if run_id and self._cache:
                        self._cache.add_event(
                            run_id=run_id,
                            iteration=iteration,
                            actor="assistant",
                            event_type="completion",
                            payload={"content": response.content or ""},
                        )
                        self._cache.complete_run(run_id, status="completed")
                    return response.content or ""

                # If the LLM sent text alongside tool_calls (narrating before
                # acting), suppress it — the user only sees tool execution output.
                for tc in response.tool_calls:
                    fn_name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    args: dict[str, Any] = (
                        json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    )

                    tool = self._tools_by_name.get(fn_name)
                    tool_hash: str | None = None
                    tool_cache_hit = False

                    if tool is None:
                        approved = False
                        is_err = True
                        result_text = f"Error: unknown tool '{fn_name}'"
                        cprint(f"  [nn.error]{result_text}[/nn.error]")
                    else:
                        if self.yolo:
                            args_display = ", ".join(f"{k}={v!r}" for k, v in args.items())
                            cprint(f"  [nn.tool]⚙ {fn_name}({args_display})[/nn.tool]")
                            approved = True
                        else:
                            approved, args = self._prompt_tool_approval(fn_name, args)

                        if not approved:
                            is_err = True
                            result_text = "Tool call denied by user."
                            cprint("  [nn.dim]✗ denied[/nn.dim]")
                        else:
                            self._tool_call_count += 1

                            cached_tool = None
                            if self._tool_cache_allowed(fn_name) and self._cache and not bypass_cache:
                                tool_hash = self._cache.tool_hash(
                                    tool_name=fn_name,
                                    args=args,
                                    cwd=os.getcwd(),
                                )
                                cached_tool = self._cache.get_tool(tool_hash)

                            if cached_tool is not None:
                                tool_cache_hit = True
                                is_err = cached_tool.is_error
                                result_text = cached_tool.error if is_err else cached_tool.output
                            else:
                                result = await tool.run(**args)
                                is_err = result.is_error
                                result_text = result.error if is_err else result.output
                                if self._tool_cache_allowed(fn_name) and self._cache:
                                    if tool_hash is None:
                                        tool_hash = self._cache.tool_hash(
                                            tool_name=fn_name,
                                            args=args,
                                            cwd=os.getcwd(),
                                        )
                                    self._cache.put_tool(
                                        tool_hash=tool_hash,
                                        tool_name=fn_name,
                                        args=args,
                                        cwd=os.getcwd(),
                                        output=result.output,
                                        error=result.error,
                                        is_error=result.is_error,
                                    )

                            # Show tool output to the user
                            if result_text:
                                max_preview = 2000
                                preview = result_text[:max_preview]
                                if len(result_text) > max_preview:
                                    preview += f"\n… ({len(result_text) - max_preview} more chars)"
                                if tool_cache_hit:
                                    preview = f"[cache_hit=true]\n{preview}"
                                if is_err:
                                    cprint(f"  [nn.error]{preview}[/nn.error]")
                                else:
                                    cprint(f"  [dim]{preview}[/dim]")

                    self.history.append(
                        Message(
                            role="tool",
                            content=result_text,
                            tool_call_id=tc["id"],
                            name=fn_name,
                        )
                    )

                    if run_id and self._cache:
                        self._cache.add_event(
                            run_id=run_id,
                            iteration=iteration,
                            actor="tool",
                            event_type="execution",
                            payload={
                                "name": fn_name,
                                "args": args,
                                "approved": approved,
                                "cache_hit": tool_cache_hit,
                                "tool_hash": tool_hash,
                            },
                        )
                        self._cache.add_event(
                            run_id=run_id,
                            iteration=iteration,
                            actor="tool",
                            event_type="observation",
                            payload={
                                "name": fn_name,
                                "is_error": is_err,
                                "content": result_text,
                            },
                        )

                cprint("  [bold green]✓ done[/bold green]")

            if run_id and self._cache:
                self._cache.complete_run(run_id, status="max_iterations")
            return "(max iterations reached)"
        except Exception:
            if run_id and self._cache:
                self._cache.complete_run(run_id, status="error")
            raise
        finally:
            self._active_run_id = None

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    async def _handle_slash(self, cmd: str) -> bool:
        """Process a slash command. Returns True if handled (no LLM call)."""
        parts = cmd.strip().split(None, 1)
        command = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        handlers: dict[str, Any] = {
            "/help": self._cmd_help,
            "/tools": self._cmd_tools,
            "/model": self._cmd_model,
            "/provider": self._cmd_provider,
            "/config": self._cmd_config,
            "/history": self._cmd_history,
            "/clear": self._cmd_clear,
            "/status": self._cmd_status,
            "/compact": self._cmd_compact,
            "/mcp": self._cmd_mcp,
            "/cache": self._cmd_cache,
            "/cache-limit": self._cmd_cache_limit,
            "/yolo": self._cmd_yolo,
            "/allow": self._cmd_yolo,
            "/reset-prompt": self._cmd_reset_prompt,
            "/quit": None,
            "/exit": None,
        }

        if command not in handlers:
            cprint(f"[nn.error]Unknown command: {command}[/nn.error]")
            cprint("[nn.dim]Type /help to see available commands.[/nn.dim]")
            return True

        handler = handlers[command]
        if handler is None:
            return False  # quit signal
        import asyncio
        result = handler(arg)
        if asyncio.iscoroutine(result):
            await result
        return True

    def _cmd_help(self, _arg: str) -> None:
        cmds = [
            ("/help", "Show this help message"),
            ("/tools [add|remove]", "List, add, or remove tools"),
            ("/model [name|list|select]", "Select model with arrows or switch directly"),
            ("/provider [name]", "Show or switch provider (openai, groq, anthropic, gemini)"),
            ("/config [key=value]", "Show or update config settings"),
            ("/history", "Show conversation history summary"),
            ("/clear", "Clear conversation history and start fresh"),
            ("/compact", "Summarize and compact the conversation context"),
            ("/status", "Show session stats (uptime, tool calls, tokens)"),
            ("/mcp", "Show connected external MCP servers"),
            ("/cache [status|clear|mode|bypass]", "Manage execution cache"),
            ("/cache-limit <max_entries> [ttl_seconds]", "Set cache SQLite limits for token economy"),
            ("/yolo or /allow", "Toggle auto-approve mode (skip per-tool approval)"),
            ("/reset-prompt", "Reset system prompt to the built-in default"),
            ("/quit or /exit", "Exit the chat session"),
        ]
        print_table(
            "Slash Commands",
            ["Command", "Description"],
            [[c, d] for c, d in cmds],
            col_widths=[38, 55],
        )

    def _cmd_tools(self, arg: str) -> None:
        if arg.startswith("add "):
            self._tools_add(arg[4:].strip())
            return
        if arg.startswith("remove "):
            self._tools_remove(arg[7:].strip())
            return

        builtin_names = {t.name for t in ALL_TOOLS}
        custom_tools = load_custom_tools()
        custom_names = {t.name for t in custom_tools}

        rows: list[list[str]] = []
        for i, t in enumerate(self.tools, 1):
            if t.name in custom_names:
                marker = " (custom)"
            elif t.name not in builtin_names:
                marker = " (external)"
            else:
                marker = ""
            rows.append([str(i), t.name + marker, t.description])
        print_table(
            "Available Tools",
            ["#", "Tool", "Description"],
            rows,
            col_widths=[4, 28, 50],
        )
        ext = len(self.tools) - len(ALL_TOOLS) - len(custom_tools)
        parts = [f"{len(ALL_TOOLS)} built-in"]
        if custom_tools:
            parts.append(f"{len(custom_tools)} custom")
        if ext > 0:
            parts.append(f"{ext} external")
        cprint(f"  {' + '.join(parts)}")
        cprint("  Manage: /tools add <name>  |  /tools remove <name>\n")

    def _tools_add(self, name: str) -> None:
        """Interactive add a custom YAML tool."""
        if not name:
            cprint("[nn.error]  Usage: /tools add <tool-name>[/nn.error]")
            return
        try:
            desc = cinput("[nn.info]  Description: [/nn.info]").strip()
            ttype = cinput("[nn.info]  Type (shell/python) [shell]: [/nn.info]").strip() or "shell"
            if ttype == "shell":
                cmd = cinput("[nn.info]  Command template: [/nn.info]").strip()
            else:
                cmd = cinput("[nn.info]  Python code: [/nn.info]").strip()
            requires_raw = cinput("[nn.info]  Requires (comma-sep, or empty): [/nn.info]").strip()
            requires = [r.strip() for r in requires_raw.split(",") if r.strip()] if requires_raw else []
        except (EOFError, KeyboardInterrupt):
            cprint("\n[nn.dim]  Cancelled.[/nn.dim]")
            return

        spec: dict[str, Any] = {
            "name": name,
            "description": desc,
            "type": ttype,
        }
        if ttype == "shell":
            spec["command_template"] = cmd
        else:
            spec["python_code"] = cmd
        if requires:
            spec["requires"] = requires

        path = save_custom_tool(spec)
        new_tool = DynamicTool(spec, source_path=path)
        self.tools.append(new_tool)
        self._tools_by_name[new_tool.name] = new_tool
        cprint(f"[nn.agent]  ✓ Tool '{name}' created at {path} and loaded.[/nn.agent]")

    def _tools_remove(self, name: str) -> None:
        """Remove a custom tool by name."""
        if not name:
            cprint("[nn.error]  Usage: /tools remove <tool-name>[/nn.error]")
            return
        if remove_custom_tool(name):
            self.tools = [t for t in self.tools if t.name != name]
            self._tools_by_name.pop(name, None)
            cprint(f"[nn.agent]  ✓ Custom tool '{name}' removed.[/nn.agent]")
        else:
            cprint(f"[nn.error]  Custom tool '{name}' not found.[/nn.error]")

    async def _fetch_provider_models(self) -> list[dict]:
        cprint(
            f"\n[nn.info]  Fetching models from [cyan]{self.config.provider}[/cyan]…[/nn.info]"
        )
        models = await self.provider.list_models()
        if models:
            self._store_model_completion_candidates(
                [m.get("id", "") for m in models if m.get("id")]
            )
        return models

    def _render_models_table(self, models: list[dict]) -> None:
        current = self.config.model
        rows: list[list[str]] = []
        for i, model_data in enumerate(models, 1):
            model_id = model_data["id"]
            owner = model_data.get("owned_by") or ""
            label = f"{model_id} ◀ current" if model_id == current else model_id
            rows.append([str(i), label, owner])
        print_table(
            f"Models — {self.config.provider}",
            ["#", "Model ID", "Owner / Name"],
            rows,
            col_widths=[4, 35, 20],
        )

    async def _cmd_model_select(self) -> None:
        if not sys.stdin.isatty():
            cprint(
                "[nn.error]  Arrow selection requires an interactive TTY.[/nn.error]"
            )
            return

        models = await self._fetch_provider_models()
        if not models:
            cprint(
                "[nn.error]  Could not retrieve models. "
                "Check your API key or provider.[/nn.error]\n"
            )
            return

        self._render_models_table(models)
        options = [m["id"] for m in models]
        options.append("[cancel]")
        cprint("[nn.dim]  Use ↑/↓ + Enter to select a model.[/nn.dim]")
        idx = _arrow_select(options)
        if idx < 0 or idx == len(options) - 1:
            cprint("[nn.dim]  Selection cancelled.[/nn.dim]")
            return

        selected = models[idx]["id"]
        if selected == self.config.model:
            cprint(f"[nn.dim]  Model already active: {selected}[/nn.dim]")
            return
        self._set_model(selected)

    async def _cmd_model(self, arg: str) -> None:
        mode = (arg or "").strip().lower()
        if mode in {"", "select"}:
            await self._cmd_model_select()
            return
        if mode == "list":
            models = await self._fetch_provider_models()
            if not models:
                cprint(
                    "[nn.error]  Could not retrieve models. "
                    "Check your API key or provider.[/nn.error]\n"
                )
                return
            self._render_models_table(models)
            cprint(
                f"[nn.dim]  {len(models)} model(s) available  •  "
                "Use /model (arrows) or /model <model-id>[/nn.dim]\n"
            )
            return
        self._set_model(arg.strip())

    def _cmd_provider(self, arg: str) -> None:
        if not arg:
            cprint(
                f"[nn.info]  Current provider: [cyan]{self.config.provider}[/cyan][/nn.info]"
            )
            cprint(
                f"[nn.dim]  Available: {', '.join(PROVIDERS.keys())}[/nn.dim]"
            )
            return
        if arg not in PROVIDERS:
            cprint(
                f"[nn.error]  Unknown provider '{arg}'. "
                f"Available: {', '.join(PROVIDERS.keys())}[/nn.error]"
            )
            return
        old = self.config.provider
        self.config.provider = arg
        env_var = DEFAULT_API_KEY_ENV_BY_PROVIDER.get(arg, "NONAIL_API_KEY")
        new_key = os.environ.get(env_var, "")
        if new_key:
            self.config.api_key = new_key
            self.config.api_key_env = env_var
        self.provider = create_provider(
            name=self.config.provider,
            api_key=self.config.api_key,
            model=self.config.model,
            api_base=self.config.api_base,
        )
        self._store_model_completion_candidates([self.config.model])
        cprint(f"[nn.agent]  ✓ Provider switched: {old} → {arg}[/nn.agent]")
        if not new_key:
            cprint(
                f"[nn.error]  ⚠ No API key found for ${env_var}[/nn.error]"
            )

    def _cmd_config(self, arg: str) -> None:
        if not arg:
            rows = [
                ["provider", self.config.provider],
                ["model", self.config.model],
                ["api_key_env", self.config.api_key_env],
                ["api_key", "••••" + self.config.api_key[-4:] if len(self.config.api_key) > 4 else "(not set)"],
                ["api_base", self.config.api_base or "(default)"],
                ["max_iterations", str(self.config.max_iterations)],
                ["cache_enabled", str(self.config.cache_enabled)],
                ["cache_mode", self.config.cache_mode],
                ["cache_path", self.config.cache_path],
                ["cache_max_entries", str(self.config.cache_max_entries)],
                ["cache_ttl_seconds", str(self.config.cache_ttl_seconds)],
                ["config_path", str(DEFAULT_CONFIG_PATH)],
            ]
            print_table(
                "Current Configuration",
                ["Key", "Value"],
                rows,
                col_widths=[20, 40],
            )
            cprint("  Set values: /config key=value  |  Save: /config save\n")
            return

        if arg == "save":
            self.config.save()
            cprint(
                f"[nn.agent]  ✓ Config saved to {DEFAULT_CONFIG_PATH}[/nn.agent]"
            )
            return

        if "=" not in arg:
            cprint("[nn.error]  Usage: /config key=value[/nn.error]")
            return

        key, val = arg.split("=", 1)
        key, val = key.strip(), val.strip()
        settable = {
            "model": "model",
            "provider": "provider",
            "max_iterations": "max_iterations",
            "api_base": "api_base",
            "cache_mode": "cache_mode",
            "cache_enabled": "cache_enabled",
            "cache_ttl_seconds": "cache_ttl_seconds",
            "cache_max_entries": "cache_max_entries",
            "cache_path": "cache_path",
        }
        if key not in settable:
            cprint(
                f"[nn.error]  Cannot set '{key}'. "
                f"Settable: {', '.join(settable)}[/nn.error]"
            )
            return
        attr = settable[key]
        if key in {"max_iterations", "cache_ttl_seconds", "cache_max_entries"}:
            val = int(val)  # type: ignore[assignment]
        if key == "cache_enabled":
            val = val.lower() in {"1", "true", "yes", "on"}
        if key == "cache_mode" and val not in {"aggressive", "safe", "off"}:
            cprint("[nn.error]  cache_mode must be aggressive|safe|off[/nn.error]")
            return
        setattr(self.config, attr, val)
        cprint(f"[nn.agent]  ✓ {key} = {val}[/nn.agent]")

    def _cmd_history(self, _arg: str) -> None:
        user_msgs = [m for m in self.history if m.role == "user"]
        assistant_msgs = [m for m in self.history if m.role == "assistant"]
        tool_msgs = [m for m in self.history if m.role == "tool"]
        cprint(
            f"\n[nn.info]  Conversation: {len(user_msgs)} user, "
            f"{len(assistant_msgs)} assistant, {len(tool_msgs)} tool messages[/nn.info]"
        )
        total_chars = sum(len(m.content or "") for m in self.history)
        cprint(f"[nn.dim]  ~{total_chars:,} characters in context[/nn.dim]\n")

    def _cmd_clear(self, _arg: str) -> None:
        self.history = [Message(role="system", content=self.config.system_prompt)]
        self._inject_system_context()
        self._tool_call_count = 0
        self._start_time = time.time()
        cprint("[nn.agent]  ✓ Conversation cleared.[/nn.agent]")

    def _cmd_compact(self, _arg: str) -> None:
        user_msgs = [m for m in self.history if m.role == "user"]
        if len(user_msgs) < 2:
            cprint("[nn.dim]  Nothing to compact yet.[/nn.dim]")
            return
        # Keep system prompt + last 4 exchanges
        keep_count = 8
        kept: list[Message] = [self.history[0]]  # system
        kept.extend(self.history[-keep_count:])
        old_len = len(self.history)
        self.history = kept
        cprint(
            f"[nn.agent]  ✓ Compacted: {old_len} → {len(self.history)} messages[/nn.agent]"
        )

    def _cmd_status(self, _arg: str) -> None:
        elapsed = time.time() - self._start_time
        mins, secs = divmod(int(elapsed), 60)
        hrs, mins = divmod(mins, 60)
        uptime = f"{hrs}h {mins}m {secs}s" if hrs else f"{mins}m {secs}s"
        total_chars = sum(len(m.content or "") for m in self.history)
        est_tokens = total_chars // 4

        rows: list[list[str]] = [
            ["Session uptime", uptime],
            ["Provider / Model", f"{self.config.provider} / {self.config.model}"],
            ["Messages", str(len(self.history))],
            ["Tool calls", str(self._tool_call_count)],
            ["Est. tokens", f"~{est_tokens:,}"],
            ["Built-in tools", str(len(ALL_TOOLS))],
        ]
        ext = len(self.tools) - len(ALL_TOOLS)
        if ext:
            rows.append(["External tools", str(ext)])
        if self._cache_enabled() and self._cache:
            stats = self._cache.stats()
            rows.append(["Cache mode", self.config.cache_mode])
            rows.append(["Cache entries", f"{stats['llm_entries']} llm / {stats['tool_entries']} tool"])
            rows.append(["Cache hits", f"{stats['llm_hits']} llm / {stats['tool_hits']} tool"])
        print_table(None, ["", ""], rows, col_widths=[20, 40])

    def _cmd_mcp(self, _arg: str) -> None:
        from .mcp_client import load_servers

        servers = load_servers()
        ext = len(self.tools) - len(ALL_TOOLS)
        if not servers and ext == 0:
            cprint("  No external MCP servers. Use 'nonail mcp add' to configure one.")
            return
        rows: list[list[str]] = []
        for name, s in servers.items():
            st = "● connected" if s.enabled else "○ disabled"
            rows.append([name, s.type, st])
        print_table(None, ["Server", "Type", "Status"], rows)
        cprint(f"  {ext} external tool(s) loaded\n")

    def _cmd_cache(self, arg: str) -> None:
        cmd = (arg or "status").strip()
        parts = cmd.split(None, 1)
        action = parts[0].lower() if parts else "status"
        rest = parts[1].strip() if len(parts) > 1 else ""

        if action == "bypass":
            self._cache_bypass_once = True
            cprint("[nn.agent]  ✓ Next request will bypass cache reads.[/nn.agent]")
            return

        if self._cache is None or not self.config.cache_enabled:
            cprint("[nn.dim]  Cache backend is disabled in config.[/nn.dim]")
            return

        if action == "status":
            stats = self._cache.stats()
            rows = [
                ["Path", stats["path"]],
                ["Mode", self.config.cache_mode],
                ["LLM entries", str(stats["llm_entries"])],
                ["Tool entries", str(stats["tool_entries"])],
                ["Runs", str(stats["runs"])],
                ["Events", str(stats["events"])],
                ["LLM hits", str(stats["llm_hits"])],
                ["Tool hits", str(stats["tool_hits"])],
            ]
            print_table(None, ["", ""], rows, col_widths=[20, 40])
            return

        if action == "clear":
            self._cache.clear()
            cprint("[nn.agent]  ✓ Cache cleared.[/nn.agent]")
            return

        if action == "mode":
            mode = rest.lower()
            if mode not in {"aggressive", "safe", "off"}:
                cprint("[nn.error]  Usage: /cache mode <aggressive|safe|off>[/nn.error]")
                return
            self.config.cache_mode = mode
            cprint(f"[nn.agent]  ✓ cache mode = {mode}[/nn.agent]")
            return

        cprint("[nn.error]  Usage: /cache [status|clear|mode <...>|bypass][/nn.error]")

    def _cmd_cache_limit(self, arg: str) -> None:
        parts = [p for p in arg.split() if p]
        if self._cache is None:
            cprint("[nn.error]  Cache backend is not initialized.[/nn.error]")
            return

        if not parts:
            cprint(
                f"[nn.info]  cache_max_entries={self.config.cache_max_entries} "
                f"cache_ttl_seconds={self.config.cache_ttl_seconds}[/nn.info]"
            )
            cprint("[nn.dim]  Usage: /cache-limit <max_entries> [ttl_seconds][/nn.dim]")
            return

        try:
            max_entries = int(parts[0])
            ttl_seconds = int(parts[1]) if len(parts) > 1 else self.config.cache_ttl_seconds
        except ValueError:
            cprint("[nn.error]  Values must be integers.[/nn.error]")
            return

        if max_entries < 100 or ttl_seconds < 60:
            cprint("[nn.error]  Min values: max_entries>=100 and ttl_seconds>=60[/nn.error]")
            return

        self.config.cache_max_entries = max_entries
        self.config.cache_ttl_seconds = ttl_seconds
        self._cache.set_limits(max_entries=max_entries, ttl_seconds=ttl_seconds)
        cprint(
            f"[nn.agent]  ✓ cache limits updated: max_entries={max_entries}, "
            f"ttl_seconds={ttl_seconds}[/nn.agent]"
        )

    def _cmd_yolo(self, _arg: str) -> None:
        self.yolo = not self.yolo
        if self.yolo:
            cprint(
                "[bold yellow]  ⚡ YOLO mode ON[/bold yellow] — "
                "[dim]all tool calls will execute without approval.[/dim]"
            )
        else:
            cprint(
                "[nn.agent]  ✓ YOLO mode OFF[/nn.agent] — "
                "[dim]approval prompts restored.[/dim]"
            )

    def _cmd_reset_prompt(self, _arg: str) -> None:
        from .config import DEFAULTS

        self.config.system_prompt = DEFAULTS["system_prompt"]
        self.history[0] = Message(role="system", content=self.config.system_prompt)
        self._inject_system_context()
        cprint("[nn.agent]  ✓ System prompt reset to built-in default.[/nn.agent]")

    # ------------------------------------------------------------------
    # System context injection
    # ------------------------------------------------------------------

    def _inject_system_context(self) -> None:
        """Auto-inject OS/env info into the system prompt so the LLM
        never needs to call system_info just to know the basics."""
        import platform
        import shutil
        import socket

        pkg_mgr = "unknown"
        for name in ("apt", "dnf", "yum", "pacman", "zypper", "brew", "apk", "pkg"):
            if shutil.which(name):
                pkg_mgr = name
                break

        ctx = (
            f"\n\n## System context (auto-detected at startup)\n"
            f"- OS: {platform.system()} {platform.release()} ({platform.machine()})\n"
            f"- Distro: {platform.freedesktop_os_release().get('PRETTY_NAME', 'unknown') if hasattr(platform, 'freedesktop_os_release') else 'unknown'}\n"
            f"- Hostname: {socket.gethostname()}\n"
            f"- User: {os.environ.get('USER', 'unknown')}\n"
            f"- Shell: {os.environ.get('SHELL', 'unknown')}\n"
            f"- Package manager: {pkg_mgr}\n"
            f"- CWD: {os.getcwd()}\n"
            f"- Python: {platform.python_version()}"
        )
        self.history[0] = Message(
            role="system",
            content=(self.history[0].content or "") + ctx,
        )

    # ------------------------------------------------------------------
    # Banner & REPL
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        ext_count = len(self.tools) - len(ALL_TOOLS)
        ext_note = f" + {ext_count} external" if ext_count else ""
        now = datetime.now().strftime("%H:%M")

        lines = (
            f"🔨 NoNail  v0.1.0  •  {now}\n"
            f"   Provider: {self.config.provider}  Model: {self.config.model}\n"
            f"   Tools: {len(ALL_TOOLS)} built-in{ext_note}"
            f"  Iterations: {self.config.max_iterations}\n"
            f"   Type /help for commands  •  /quit to exit"
        )
        print_panel(lines)

    async def chat_loop(self) -> None:
        """Interactive REPL loop with slash-command support."""
        self._load_custom_tools()
        await self._load_external_tools()
        self._inject_system_context()
        self._print_banner()
        print()

        _rl = _setup_readline()
        self._configure_readline_completion(_rl)

        try:
            while True:
                try:
                    cwd = os.getcwd()
                    home = os.path.expanduser("~")
                    display_cwd = cwd.replace(home, "~", 1) if cwd.startswith(home) else cwd
                    user_input = cinput(f"{display_cwd}\nyou › ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not user_input:
                    continue

                # Slash commands
                if user_input.startswith("/"):
                    if user_input.lower() in ("/quit", "/exit"):
                        print("Goodbye!")
                        break
                    await self._handle_slash(user_input)
                    continue

                # Regular LLM call
                try:
                    t0 = time.time()
                    reply = await self.step(user_input)
                    elapsed = time.time() - t0
                    print()
                    print_rule(f"  {self.config.model}  ⏱ {elapsed:.1f}s  ")
                    if reply and reply.strip():
                        print()
                        print(reply)
                    print()
                except Exception as exc:
                    cprint(f"Error: {exc}")
        finally:
            _save_readline(_rl)
            if self._mcp_manager:
                await self._mcp_manager.close()
            if self._cache:
                self._cache.close()
