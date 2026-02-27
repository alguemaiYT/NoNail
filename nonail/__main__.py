"""CLI entry point for NoNail."""

from __future__ import annotations

import asyncio
import sys

import click
from rich.console import Console

from .config import Config

console = Console()


@click.group()
def cli():
    """🔨 NoNail — Simplified AI agent with full computer access & MCP support."""
    pass


@cli.command()
@click.option("--config", "-c", default=None, help="Path to config.yaml")
@click.option("--provider", "-p", default=None, help="LLM provider (openai, anthropic)")
@click.option("--model", "-m", default=None, help="Model name")
@click.option("--api-key", "-k", default=None, help="API key (or set NONAIL_API_KEY)")
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
            "[red]No API key found.[/red] Set NONAIL_API_KEY or pass --api-key."
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
        console.print("[red]No API key. Set NONAIL_API_KEY or use config.yaml.[/red]")
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
@click.option("--model", "-m", default="gpt-4o", help="Model name")
@click.option("--api-key", "-k", default=None, help="API key")
def init(provider, model, api_key):
    """Create a default ~/.nonail/config.yaml."""
    cfg = Config(provider=provider, model=model, api_key=api_key or "")
    cfg.save()
    console.print(f"[green]Config saved to {Config.DEFAULT_CONFIG_PATH if hasattr(Config, 'DEFAULT_CONFIG_PATH') else '~/.nonail/config.yaml'}[/green]")
    console.print("Set your API key: [cyan]export NONAIL_API_KEY=sk-...[/cyan]")


@cli.command()
def doctor():
    """Check if NoNail is configured correctly."""
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


if __name__ == "__main__":
    cli()
