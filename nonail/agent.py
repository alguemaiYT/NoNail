"""Core agent loop — orchestrates LLM ↔ tools conversation."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .config import Config
from .providers import Message, create_provider
from .tools import ALL_TOOLS

console = Console()


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
        # Start with built-in tools; external MCP tools appended in _load_external_tools
        self.tools: list = list(ALL_TOOLS)
        self._tools_by_name: dict[str, Any] = {t.name: t for t in self.tools}
        self._mcp_manager = None
        self.history: list[Message] = [
            Message(role="system", content=config.system_prompt)
        ]

    async def _load_external_tools(self) -> None:
        """Connect to configured external MCP servers and extend the tool list."""
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

    async def step(self, user_input: str) -> str:
        """Run one full user→agent exchange (may invoke tools multiple times)."""
        self.history.append(Message(role="user", content=user_input))
        tool_schemas = [t.to_openai_schema() for t in self.tools]

        for _ in range(self.config.max_iterations):
            response = await self.provider.chat(self.history, tools=tool_schemas)
            self.history.append(response)

            if not response.tool_calls:
                return response.content or ""

            # Execute every requested tool call
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
                    console.print(
                        f"  [dim]⚙ {fn_name}({', '.join(f'{k}={v!r}' for k,v in args.items())})[/dim]"
                    )
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

    async def chat_loop(self) -> None:
        """Interactive REPL loop."""
        await self._load_external_tools()

        ext_count = len(self.tools) - len(ALL_TOOLS)
        ext_note = f" + [cyan]{ext_count}[/cyan] external" if ext_count else ""
        console.print(
            Panel(
                "[bold green]NoNail Agent[/bold green] — full computer access, MCP-compatible\n"
                f"Provider: [cyan]{self.config.provider}[/cyan] | Model: [cyan]{self.config.model}[/cyan]\n"
                f"Tools: [cyan]{len(ALL_TOOLS)}[/cyan] built-in{ext_note}\n"
                "Type [bold]/quit[/bold] to exit.",
                title="🔨 NoNail",
            )
        )

        try:
            while True:
                try:
                    user_input = console.input("[bold blue]you>[/bold blue] ").strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not user_input:
                    continue
                if user_input.lower() in ("/quit", "/exit", "exit", "quit"):
                    break

                try:
                    reply = await self.step(user_input)
                    console.print()
                    console.print(Markdown(reply))
                    console.print()
                except Exception as exc:
                    console.print(f"[red]Error: {exc}[/red]")
        finally:
            if self._mcp_manager:
                await self._mcp_manager.close()
