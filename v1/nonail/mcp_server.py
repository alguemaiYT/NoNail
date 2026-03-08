"""MCP server — exposes all NoNail tools via Model Context Protocol.

Any MCP-compatible client (Claude Desktop, Cursor, VS Code, etc.)
can connect to NoNail and use its tools through the standard protocol.

All mcp/fastmcp imports are deferred to ``run_mcp_server()`` so the
module can be imported without pulling in the MCP SDK.
"""

from __future__ import annotations

from typing import Any


def run_mcp_server() -> None:
    """Entry point: start the MCP server (stdio transport by default)."""
    from mcp.server.fastmcp import FastMCP

    from .tools import ALL_TOOLS

    mcp = FastMCP(
        "NoNail",
        instructions=(
            "NoNail agent — full computer access via MCP. "
            "Execute shell commands, read/write files, manage processes, "
            "and query system information."
        ),
    )

    # Dynamically register every NoNail tool as an MCP tool
    for tool in ALL_TOOLS:

        def _make_handler(t):
            async def handler(**kwargs: Any) -> str:
                result = await t.run(**kwargs)
                if result.is_error:
                    return f"ERROR: {result.error}"
                return result.output

            handler.__name__ = t.name
            handler.__doc__ = t.description

            schema = t.parameters_schema()
            params = schema.get("properties", {})

            annotations: dict[str, Any] = {}
            for pname, pinfo in params.items():
                ptype = {"string": str, "integer": int, "boolean": bool}.get(
                    pinfo.get("type", "string"), str
                )
                annotations[pname] = ptype
            handler.__annotations__ = annotations

            return handler

        mcp.tool(name=tool.name, description=tool.description)(
            _make_handler(tool)
        )

    mcp.run()
