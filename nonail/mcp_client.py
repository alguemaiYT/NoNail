"""MCP Client — connects NoNail to external community MCP servers.

NoNail can act as an MCP *client*: it connects to external servers
(npm/npx packages, GitHub-hosted servers, HTTP/SSE remotes) and exposes
their tools to the local agent alongside the built-in tools.

Config is stored in ~/.nonail/mcp-clients.json, matching the format used
by GitHub Copilot CLI (~/.copilot/mcp-config.json) for easy copy-paste.
"""

from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from .tools.base import Tool, ToolResult

MCP_CLIENTS_PATH = Path.home() / ".nonail" / "mcp-clients.json"


# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------


@dataclass
class ExternalMCPServer:
    """Configuration for one external MCP server."""

    name: str
    type: str = "stdio"  # "stdio" | "http" | "sse"
    # STDIO params
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # HTTP / SSE params
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    # Filter which tools to expose; ["*"] means all
    tools: list[str] = field(default_factory=lambda: ["*"])
    enabled: bool = True

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "type": self.type,
            "enabled": self.enabled,
            "tools": self.tools,
        }
        if self.type == "stdio":
            d["command"] = self.command
            d["args"] = self.args
            if self.env:
                d["env"] = self.env
        else:
            d["url"] = self.url
            if self.headers:
                d["headers"] = self.headers
        return d

    @classmethod
    def from_dict(cls, name: str, data: dict) -> ExternalMCPServer:
        return cls(
            name=name,
            type=data.get("type", "stdio"),
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url", ""),
            headers=data.get("headers", {}),
            tools=data.get("tools", ["*"]),
            enabled=data.get("enabled", True),
        )


def load_servers() -> dict[str, ExternalMCPServer]:
    """Load external MCP server configs from disk."""
    if not MCP_CLIENTS_PATH.exists():
        return {}
    with open(MCP_CLIENTS_PATH) as f:
        data = json.load(f)
    return {
        name: ExternalMCPServer.from_dict(name, cfg)
        for name, cfg in data.get("mcpServers", {}).items()
    }


def save_servers(servers: dict[str, ExternalMCPServer]) -> None:
    """Persist external MCP server configs to disk."""
    MCP_CLIENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {"mcpServers": {name: s.to_dict() for name, s in servers.items()}}
    with open(MCP_CLIENTS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    # Restrict permissions — file may contain tokens/secrets
    MCP_CLIENTS_PATH.chmod(0o600)


# ---------------------------------------------------------------------------
# Tool proxy
# ---------------------------------------------------------------------------


class MCPClientTool(Tool):
    """Proxies a tool call to an external MCP server via a live session."""

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_schema: dict,
        session: ClientSession,
        server_name: str,
    ):
        self._name = tool_name
        self._description = f"[{server_name}] {tool_description}"
        self._schema = tool_schema
        self._session = session

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def parameters_schema(self) -> dict:
        return self._schema

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema(),
            },
        }

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            result = await self._session.call_tool(self.name, kwargs)
            output = "\n".join(
                c.text for c in result.content if hasattr(c, "text")
            )
            if result.isError:
                return ToolResult(error=output or "Unknown tool error", is_error=True)
            return ToolResult(output=output)
        except Exception as exc:
            return ToolResult(error=str(exc), is_error=True)


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


class MCPClientManager:
    """Opens and maintains connections to all configured external MCP servers."""

    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self._tools: list[MCPClientTool] = []

    @property
    def tools(self) -> list[MCPClientTool]:
        return self._tools

    async def connect_all(
        self, servers: dict[str, ExternalMCPServer]
    ) -> list[MCPClientTool]:
        """Connect to every enabled server and return discovered proxy tools."""
        from rich.console import Console

        console = Console()
        enabled = {n: s for n, s in servers.items() if s.enabled}
        for server in enabled.values():
            try:
                tools = await self._connect_server(server)
                self._tools.extend(tools)
                console.print(
                    f"  [dim]🔌 MCP '{server.name}': {len(tools)} tool(s) loaded[/dim]"
                )
            except Exception as exc:
                console.print(
                    f"  [yellow]⚠ MCP '{server.name}' failed: {exc}[/yellow]"
                )
        return self._tools

    async def _connect_server(
        self, server: ExternalMCPServer
    ) -> list[MCPClientTool]:
        if server.type == "stdio":
            return await self._connect_stdio(server)
        elif server.type in ("http", "sse"):
            return await self._connect_sse(server)
        else:
            raise ValueError(f"Unknown transport type: '{server.type}'")

    async def _connect_stdio(self, server: ExternalMCPServer) -> list[MCPClientTool]:
        # Inherit full environment so PATH is available for npx/node/python
        merged_env = {**os.environ, **server.env}
        params = StdioServerParameters(
            command=server.command,
            args=server.args,
            env=merged_env,
        )
        transport = await self._exit_stack.enter_async_context(stdio_client(params))
        stdio_read, stdio_write = transport
        session = await self._exit_stack.enter_async_context(
            ClientSession(stdio_read, stdio_write)
        )
        await session.initialize()
        return await self._discover_tools(session, server)

    async def _connect_sse(self, server: ExternalMCPServer) -> list[MCPClientTool]:
        transport = await self._exit_stack.enter_async_context(
            sse_client(server.url, headers=server.headers)
        )
        sse_read, sse_write = transport
        session = await self._exit_stack.enter_async_context(
            ClientSession(sse_read, sse_write)
        )
        await session.initialize()
        return await self._discover_tools(session, server)

    async def _discover_tools(
        self, session: ClientSession, server: ExternalMCPServer
    ) -> list[MCPClientTool]:
        response = await session.list_tools()
        filter_all = "*" in server.tools
        tools: list[MCPClientTool] = []
        for tool_def in response.tools:
            if not filter_all and tool_def.name not in server.tools:
                continue
            schema = (
                dict(tool_def.inputSchema)
                if hasattr(tool_def, "inputSchema") and tool_def.inputSchema
                else {"type": "object", "properties": {}}
            )
            tools.append(
                MCPClientTool(
                    tool_name=tool_def.name,
                    tool_description=tool_def.description or "",
                    tool_schema=schema,
                    session=session,
                    server_name=server.name,
                )
            )
        return tools

    async def close(self) -> None:
        await self._exit_stack.aclose()
