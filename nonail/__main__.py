"""CLI entry point for NoNail."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console

from .config import Config, DEFAULT_CONFIG_PATH

console = Console()


@click.group()
def cli():
    """🔨 NoNail — Simplified AI agent with full computer access & MCP support."""
    pass


@cli.command()
@click.option("--config", "-c", default=None, help="Path to config.yaml")
@click.option("--provider", "-p", default=None, help="LLM provider (openai, anthropic, groq)")
@click.option("--model", "-m", default=None, help="Model name")
@click.option("--api-key", "-k", default=None, help="API key")
@click.option("--api-base", default=None, help="Custom API base URL")
def chat(config, provider, model, api_key, api_base):
    """Start an interactive chat session with the NoNail agent."""
    from .agent import Agent

    cfg = Config.load(config)
    if provider:
        cfg.provider = provider
    if model:
        cfg.model = model
    if api_key:
        cfg.api_key = api_key
    if api_base:
        cfg.api_base = api_base

    if not cfg.api_key:
        console.print(
            "[red]No API key found.[/red] Set your provider API key env var or pass --api-key."
        )
        sys.exit(1)

    agent = Agent(cfg)
    asyncio.run(agent.chat_loop())


@cli.command()
@click.option("--config", "-c", default=None, help="Path to config.yaml")
@click.argument("message", nargs=-1, required=True)
def run(config, message):
    """Run a single prompt and print the response."""
    from .agent import Agent

    cfg = Config.load(config)
    if not cfg.api_key:
        console.print("[red]No API key. Set your provider API key env var or use config.yaml.[/red]")
        sys.exit(1)

    agent = Agent(cfg)
    prompt = " ".join(message)
    result = asyncio.run(agent.step(prompt))
    console.print(result)


@cli.command()
def serve():
    """Start the NoNail MCP server (stdio transport).

    Connect from Claude Desktop, Cursor, VS Code, or any MCP client.
    """
    from .mcp_server import run_mcp_server

    run_mcp_server()


@cli.command()
def tools():
    """List all available tools exposed to the LLM."""
    from rich.table import Table

    from .tools import ALL_TOOLS

    table = Table(title="NoNail Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    for t in ALL_TOOLS:
        table.add_row(t.name, t.description)
    console.print(table)


@cli.command()
@click.option("--provider", "-p", default="openai", help="LLM provider")
@click.option("--model", "-m", default=None, help="Model name")
@click.option("--api-key", "-k", default=None, help="API key")
def init(provider, model, api_key):
    """Create a default ~/.nonail/config.yaml."""
    default_models = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-20250514",
        "groq": "llama-3.3-70b-versatile",
    }
    default_env = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
    }

    selected_model = model or default_models.get(provider, "gpt-4o")
    selected_env = default_env.get(provider, "NONAIL_API_KEY")

    cfg = Config(
        provider=provider,
        model=selected_model,
        api_key=api_key or "",
        api_key_env=selected_env,
    )
    cfg.save()
    console.print(f"[green]Config saved to {DEFAULT_CONFIG_PATH}[/green]")
    console.print(f"Set your API key: [cyan]export {selected_env}=...[/cyan]")


@cli.command()
def doctor():
    """Check if NoNail is configured correctly."""
    from .mcp_client import load_servers

    cfg = Config.load()
    checks = {
        "Config file": cfg.extra != {},
        "API key set": bool(cfg.api_key),
        "Provider": cfg.provider,
        "Model": cfg.model,
        "MCP enabled": cfg.mcp_enabled,
    }
    for label, val in checks.items():
        if isinstance(val, bool):
            icon = "✅" if val else "❌"
            console.print(f"  {icon} {label}")
        else:
            console.print(f"  ℹ️  {label}: [cyan]{val}[/cyan]")

    servers = load_servers()
    if servers:
        console.print(f"  ℹ️  External MCP servers: [cyan]{len(servers)}[/cyan] configured")
        for name, s in servers.items():
            status = "✅" if s.enabled else "⏸"
            console.print(f"     {status} {name} ({s.type})")
    else:
        console.print("  ℹ️  External MCP servers: [dim]none (see 'nonail mcp add')[/dim]")


# ---------------------------------------------------------------------------
# MCP management sub-group
# ---------------------------------------------------------------------------


@cli.group()
def mcp():
    """Manage external community MCP server connections."""
    pass


@mcp.command("list")
def mcp_list():
    """List all configured external MCP servers and their status."""

    from rich.table import Table

    from .mcp_client import load_servers

    servers = load_servers()
    if not servers:
        console.print("[dim]No external MCP servers configured. Run 'nonail mcp add' to add one.[/dim]")
        return

    table = Table(title="External MCP Servers", show_lines=True)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="white")
    table.add_column("Command / URL", style="white")
    table.add_column("Tools", style="dim")
    table.add_column("Status", justify="center")

    for name, s in servers.items():
        cmd = s.command + (" " + " ".join(s.args) if s.args else "") if s.type == "stdio" else s.url
        tools_str = ", ".join(s.tools) if s.tools != ["*"] else "*"
        status = "✅ enabled" if s.enabled else "⏸ disabled"
        table.add_row(name, s.type, cmd, tools_str, status)

    console.print(table)


@mcp.command("add")
@click.argument("name")
@click.option("--type", "transport", default="stdio", help="Transport: stdio | http | sse")
@click.option("--command", default="", help="Command to launch (stdio only, e.g. npx)")
@click.option("--args", "args_str", default="", help="Space-separated args (stdio only)")
@click.option("--env", "env_str", default="", help="JSON env vars, e.g. '{\"KEY\":\"val\"}'")
@click.option("--url", default="", help="Server URL (http/sse only)")
@click.option("--headers", "headers_str", default="", help="JSON headers (http/sse only)")
@click.option("--tools", default="*", help="Comma-separated tool names, or * for all")
def mcp_add(name, transport, command, args_str, env_str, url, headers_str, tools):
    """Add an external MCP server.

    \b
    Examples:
      # npm/npx server
      nonail mcp add fetch --command npx --args "@modelcontextprotocol/server-fetch"
      nonail mcp add playwright --command npx --args "@playwright/mcp@latest"

      # Remote HTTP server
      nonail mcp add context7 --type http --url https://mcp.context7.com/mcp

      # GitHub-hosted server via npx
      nonail mcp add github --command npx --args "@modelcontextprotocol/server-github" --env '{"GITHUB_TOKEN":"ghp_..."}'
    """
    import json as _json

    from .mcp_client import ExternalMCPServer, load_servers, save_servers

    servers = load_servers()
    if name in servers:
        console.print(f"[yellow]Server '{name}' already exists. Remove it first with 'nonail mcp remove {name}'.[/yellow]")
        sys.exit(1)

    env: dict = {}
    if env_str:
        try:
            env = _json.loads(env_str)
        except Exception:
            console.print("[red]--env must be valid JSON, e.g. '{\"KEY\":\"val\"}'[/red]")
            sys.exit(1)

    headers: dict = {}
    if headers_str:
        try:
            headers = _json.loads(headers_str)
        except Exception:
            console.print("[red]--headers must be valid JSON[/red]")
            sys.exit(1)

    args_list = args_str.split() if args_str else []
    tools_list = [t.strip() for t in tools.split(",")] if tools != "*" else ["*"]

    server = ExternalMCPServer(
        name=name,
        type=transport,
        command=command,
        args=args_list,
        env=env,
        url=url,
        headers=headers,
        tools=tools_list,
        enabled=True,
    )
    servers[name] = server
    save_servers(servers)

    if transport == "stdio":
        cmd_display = command + (" " + " ".join(args_list) if args_list else "")
        console.print(f"[green]✅ Added '{name}' (stdio): {cmd_display}[/green]")
    else:
        console.print(f"[green]✅ Added '{name}' ({transport}): {url}[/green]")
    console.print(f"[dim]Run 'nonail mcp test {name}' to verify the connection.[/dim]")


@mcp.command("remove")
@click.argument("name")
def mcp_remove(name):
    """Remove an external MCP server."""
    from .mcp_client import load_servers, save_servers

    servers = load_servers()
    if name not in servers:
        console.print(f"[red]Server '{name}' not found.[/red]")
        sys.exit(1)
    del servers[name]
    save_servers(servers)
    console.print(f"[green]Removed '{name}'.[/green]")


@mcp.command("enable")
@click.argument("name")
def mcp_enable(name):
    """Enable a previously disabled MCP server."""
    from .mcp_client import load_servers, save_servers

    servers = load_servers()
    if name not in servers:
        console.print(f"[red]Server '{name}' not found.[/red]")
        sys.exit(1)
    servers[name].enabled = True
    save_servers(servers)
    console.print(f"[green]Enabled '{name}'.[/green]")


@mcp.command("disable")
@click.argument("name")
def mcp_disable(name):
    """Disable an MCP server without removing it."""
    from .mcp_client import load_servers, save_servers

    servers = load_servers()
    if name not in servers:
        console.print(f"[red]Server '{name}' not found.[/red]")
        sys.exit(1)
    servers[name].enabled = False
    save_servers(servers)
    console.print(f"[yellow]Disabled '{name}'.[/yellow]")


@mcp.command("test")
@click.argument("name")
def mcp_test(name):
    """Test connection to an external MCP server and list its tools."""
    import asyncio

    from rich.table import Table

    from .mcp_client import MCPClientManager, load_servers

    servers = load_servers()
    if name not in servers:
        console.print(f"[red]Server '{name}' not found.[/red]")
        sys.exit(1)

    server = servers[name]

    async def _test():
        manager = MCPClientManager()
        try:
            tools = await manager.connect_all({name: server})
            return tools
        finally:
            await manager.close()

    console.print(f"[dim]Connecting to '{name}'...[/dim]")
    try:
        tools = asyncio.run(_test())
    except Exception as exc:
        console.print(f"[red]❌ Connection failed: {exc}[/red]")
        sys.exit(1)

    if not tools:
        console.print("[yellow]Connected but no tools were discovered.[/yellow]")
        return

    table = Table(title=f"Tools from '{name}'")
    table.add_column("Tool name", style="cyan")
    table.add_column("Description", style="white")
    for t in tools:
        table.add_row(t.name, t.description)
    console.print(table)
    console.print(f"[green]✅ {len(tools)} tool(s) available.[/green]")


if __name__ == "__main__":
    cli()
