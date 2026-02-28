"""Core agent loop — orchestrates LLM ↔ tools conversation.

Inspired by Claude Code, Gemini CLI, and GitHub Copilot CLI for
the interactive REPL experience with slash-command support.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from .config import Config, DEFAULT_API_KEY_ENV_BY_PROVIDER, DEFAULT_CONFIG_PATH
from .providers import PROVIDERS, Message, create_provider
from .tools import ALL_TOOLS

# ---------------------------------------------------------------------------
# Custom Rich theme
# ---------------------------------------------------------------------------

NONAIL_THEME = Theme(
    {
        "nn.user": "bold cyan",
        "nn.agent": "bold green",
        "nn.tool": "dim yellow",
        "nn.error": "bold red",
        "nn.info": "dim white",
        "nn.accent": "bold magenta",
        "nn.dim": "dim",
        "nn.slash": "bold bright_blue",
    }
)

console = Console(theme=NONAIL_THEME)


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
        self._tool_call_count = 0
        self._start_time = time.time()

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

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    async def step(self, user_input: str) -> str:
        self.history.append(Message(role="user", content=user_input))
        tool_schemas = [t.to_openai_schema() for t in self.tools]

        for _ in range(self.config.max_iterations):
            response = await self.provider.chat(self.history, tools=tool_schemas)
            self.history.append(response)

            if not response.tool_calls:
                return response.content or ""

            for tc in response.tool_calls:
                fn_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                args: dict[str, Any] = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )
                tool = self._tools_by_name.get(fn_name)
                if tool is None:
                    result_text = f"Error: unknown tool '{fn_name}'"
                else:
                    args_display = ", ".join(f"{k}={v!r}" for k, v in args.items())
                    console.print(f"  [nn.tool]⚙ {fn_name}({args_display})[/nn.tool]")
                    self._tool_call_count += 1
                    result = await tool.run(**args)
                    result_text = result.error if result.is_error else result.output

                self.history.append(
                    Message(
                        role="tool",
                        content=result_text,
                        tool_call_id=tc["id"],
                        name=fn_name,
                    )
                )

        return "(max iterations reached)"

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    def _handle_slash(self, cmd: str) -> bool:
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
            "/quit": None,
            "/exit": None,
        }

        if command not in handlers:
            console.print(f"[nn.error]Unknown command: {command}[/nn.error]")
            console.print("[nn.dim]Type /help to see available commands.[/nn.dim]")
            return True

        handler = handlers[command]
        if handler is None:
            return False  # quit signal
        handler(arg)
        return True

    def _cmd_help(self, _arg: str) -> None:
        table = Table(
            title="[nn.accent]Slash Commands[/nn.accent]",
            show_edge=False,
            pad_edge=False,
            box=None,
        )
        table.add_column("Command", style="nn.slash", min_width=22)
        table.add_column("Description", style="white")
        cmds = [
            ("/help", "Show this help message"),
            ("/tools", "List all available tools (built-in + external)"),
            ("/model [name]", "Show or switch the current LLM model"),
            ("/provider [name]", "Show or switch provider (openai, groq, anthropic)"),
            ("/config [key=value]", "Show or update config settings"),
            ("/history", "Show conversation history summary"),
            ("/clear", "Clear conversation history and start fresh"),
            ("/compact", "Summarize and compact the conversation context"),
            ("/status", "Show session stats (uptime, tool calls, tokens)"),
            ("/mcp", "Show connected external MCP servers"),
            ("/quit or /exit", "Exit the chat session"),
        ]
        for c, d in cmds:
            table.add_row(c, d)
        console.print()
        console.print(table)
        console.print()

    def _cmd_tools(self, _arg: str) -> None:
        table = Table(title="Available Tools", show_lines=False, pad_edge=False)
        table.add_column("#", style="dim", justify="right", width=3)
        table.add_column("Tool", style="cyan", min_width=24)
        table.add_column("Description", style="white")
        builtin_count = len(ALL_TOOLS)
        for i, t in enumerate(self.tools, 1):
            marker = "" if i <= builtin_count else " [dim](external)[/dim]"
            table.add_row(str(i), t.name + marker, t.description)
        console.print()
        console.print(table)
        console.print(
            f"\n[nn.dim]  {builtin_count} built-in"
            + (
                f" + {len(self.tools) - builtin_count} external"
                if len(self.tools) > builtin_count
                else ""
            )
            + "[/nn.dim]"
        )
        console.print()

    def _cmd_model(self, arg: str) -> None:
        if not arg:
            console.print(
                f"[nn.info]  Current model: [cyan]{self.config.model}[/cyan] "
                f"(provider: [cyan]{self.config.provider}[/cyan])[/nn.info]"
            )
            console.print("[nn.dim]  Usage: /model <model-name>[/nn.dim]")
            return
        old = self.config.model
        self.config.model = arg
        self.provider = create_provider(
            name=self.config.provider,
            api_key=self.config.api_key,
            model=self.config.model,
            api_base=self.config.api_base,
        )
        console.print(f"[nn.agent]  ✓ Model switched: {old} → {arg}[/nn.agent]")

    def _cmd_provider(self, arg: str) -> None:
        if not arg:
            console.print(
                f"[nn.info]  Current provider: [cyan]{self.config.provider}[/cyan][/nn.info]"
            )
            console.print(
                f"[nn.dim]  Available: {', '.join(PROVIDERS.keys())}[/nn.dim]"
            )
            return
        if arg not in PROVIDERS:
            console.print(
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
        console.print(f"[nn.agent]  ✓ Provider switched: {old} → {arg}[/nn.agent]")
        if not new_key:
            console.print(
                f"[nn.error]  ⚠ No API key found for ${env_var}[/nn.error]"
            )

    def _cmd_config(self, arg: str) -> None:
        if not arg:
            table = Table(
                title="Current Configuration",
                show_edge=False,
                pad_edge=False,
                box=None,
            )
            table.add_column("Key", style="cyan", min_width=18)
            table.add_column("Value", style="white")
            table.add_row("provider", self.config.provider)
            table.add_row("model", self.config.model)
            table.add_row("api_key_env", self.config.api_key_env)
            table.add_row("api_key", "••••" + self.config.api_key[-4:] if len(self.config.api_key) > 4 else "(not set)")
            table.add_row("api_base", self.config.api_base or "(default)")
            table.add_row("max_iterations", str(self.config.max_iterations))
            table.add_row("config_path", str(DEFAULT_CONFIG_PATH))
            console.print()
            console.print(table)
            console.print(
                "\n[nn.dim]  Set values: /config key=value  |  "
                "Save: /config save[/nn.dim]\n"
            )
            return

        if arg == "save":
            self.config.save()
            console.print(
                f"[nn.agent]  ✓ Config saved to {DEFAULT_CONFIG_PATH}[/nn.agent]"
            )
            return

        if "=" not in arg:
            console.print("[nn.error]  Usage: /config key=value[/nn.error]")
            return

        key, val = arg.split("=", 1)
        key, val = key.strip(), val.strip()
        settable = {
            "model": "model",
            "provider": "provider",
            "max_iterations": "max_iterations",
            "api_base": "api_base",
        }
        if key not in settable:
            console.print(
                f"[nn.error]  Cannot set '{key}'. "
                f"Settable: {', '.join(settable)}[/nn.error]"
            )
            return
        attr = settable[key]
        if key == "max_iterations":
            val = int(val)  # type: ignore[assignment]
        setattr(self.config, attr, val)
        console.print(f"[nn.agent]  ✓ {key} = {val}[/nn.agent]")

    def _cmd_history(self, _arg: str) -> None:
        user_msgs = [m for m in self.history if m.role == "user"]
        assistant_msgs = [m for m in self.history if m.role == "assistant"]
        tool_msgs = [m for m in self.history if m.role == "tool"]
        console.print(
            f"\n[nn.info]  Conversation: {len(user_msgs)} user, "
            f"{len(assistant_msgs)} assistant, {len(tool_msgs)} tool messages[/nn.info]"
        )
        total_chars = sum(len(m.content or "") for m in self.history)
        console.print(f"[nn.dim]  ~{total_chars:,} characters in context[/nn.dim]\n")

    def _cmd_clear(self, _arg: str) -> None:
        self.history = [Message(role="system", content=self.config.system_prompt)]
        self._tool_call_count = 0
        self._start_time = time.time()
        console.print("[nn.agent]  ✓ Conversation cleared.[/nn.agent]")

    def _cmd_compact(self, _arg: str) -> None:
        user_msgs = [m for m in self.history if m.role == "user"]
        if len(user_msgs) < 2:
            console.print("[nn.dim]  Nothing to compact yet.[/nn.dim]")
            return
        # Keep system prompt + last 4 exchanges
        keep_count = 8
        kept: list[Message] = [self.history[0]]  # system
        kept.extend(self.history[-keep_count:])
        old_len = len(self.history)
        self.history = kept
        console.print(
            f"[nn.agent]  ✓ Compacted: {old_len} → {len(self.history)} messages[/nn.agent]"
        )

    def _cmd_status(self, _arg: str) -> None:
        elapsed = time.time() - self._start_time
        mins, secs = divmod(int(elapsed), 60)
        hrs, mins = divmod(mins, 60)
        uptime = f"{hrs}h {mins}m {secs}s" if hrs else f"{mins}m {secs}s"
        total_chars = sum(len(m.content or "") for m in self.history)
        est_tokens = total_chars // 4

        table = Table(show_edge=False, pad_edge=False, box=None)
        table.add_column("", style="dim", min_width=18)
        table.add_column("", style="white")
        table.add_row("Session uptime", uptime)
        table.add_row("Provider / Model", f"{self.config.provider} / {self.config.model}")
        table.add_row("Messages", str(len(self.history)))
        table.add_row("Tool calls", str(self._tool_call_count))
        table.add_row("Est. tokens", f"~{est_tokens:,}")
        table.add_row("Built-in tools", str(len(ALL_TOOLS)))
        ext = len(self.tools) - len(ALL_TOOLS)
        if ext:
            table.add_row("External tools", str(ext))
        console.print()
        console.print(table)
        console.print()

    def _cmd_mcp(self, _arg: str) -> None:
        from .mcp_client import load_servers

        servers = load_servers()
        ext = len(self.tools) - len(ALL_TOOLS)
        if not servers and ext == 0:
            console.print(
                "[nn.dim]  No external MCP servers. "
                "Use 'nonail mcp add' to configure one.[/nn.dim]"
            )
            return
        table = Table(show_edge=False, pad_edge=False, box=None)
        table.add_column("Server", style="cyan")
        table.add_column("Type", style="dim")
        table.add_column("Status")
        for name, s in servers.items():
            st = "[green]● connected[/green]" if s.enabled else "[dim]○ disabled[/dim]"
            table.add_row(name, s.type, st)
        console.print()
        console.print(table)
        console.print(f"[nn.dim]  {ext} external tool(s) loaded[/nn.dim]\n")

    # ------------------------------------------------------------------
    # Banner & REPL
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        ext_count = len(self.tools) - len(ALL_TOOLS)
        ext_note = f" + {ext_count} external" if ext_count else ""
        now = datetime.now().strftime("%H:%M")

        banner = Text()
        banner.append("🔨 NoNail", style="bold green")
        banner.append(f"  v0.1.0  •  {now}\n", style="dim")
        banner.append("   Provider: ", style="dim")
        banner.append(f"{self.config.provider}", style="cyan")
        banner.append("  Model: ", style="dim")
        banner.append(f"{self.config.model}\n", style="cyan")
        banner.append("   Tools: ", style="dim")
        banner.append(f"{len(ALL_TOOLS)} built-in{ext_note}", style="cyan")
        banner.append("  Iterations: ", style="dim")
        banner.append(f"{self.config.max_iterations}\n", style="cyan")
        banner.append(
            "   Type ", style="dim"
        )
        banner.append("/help", style="nn.slash")
        banner.append(" for commands  •  ", style="dim")
        banner.append("/quit", style="nn.slash")
        banner.append(" to exit", style="dim")

        console.print(
            Panel(
                banner,
                border_style="bright_blue",
                padding=(0, 1),
            )
        )

    async def chat_loop(self) -> None:
        """Interactive REPL loop with slash-command support."""
        await self._load_external_tools()
        self._print_banner()
        console.print()

        try:
            while True:
                try:
                    user_input = console.input(
                        "[nn.user]you ›[/nn.user] "
                    ).strip()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[nn.dim]Goodbye![/nn.dim]")
                    break

                if not user_input:
                    continue

                # Slash commands
                if user_input.startswith("/"):
                    if user_input.lower() in ("/quit", "/exit"):
                        console.print("[nn.dim]Goodbye![/nn.dim]")
                        break
                    self._handle_slash(user_input)
                    continue

                # Regular LLM call
                try:
                    t0 = time.time()
                    reply = await self.step(user_input)
                    elapsed = time.time() - t0
                    console.print()
                    console.print(Markdown(reply))
                    console.print(
                        f"\n[nn.dim]  ⏱ {elapsed:.1f}s[/nn.dim]\n"
                    )
                except Exception as exc:
                    console.print(f"[nn.error]Error: {exc}[/nn.error]")
        finally:
            if self._mcp_manager:
                await self._mcp_manager.close()
