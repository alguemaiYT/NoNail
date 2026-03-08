"""CLI entry point for NoNail."""

from __future__ import annotations

import asyncio
import sys

import click

from .config import Config, DEFAULT_CONFIG_PATH
from .ui import cprint, print_table


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
        cprint(
            "No API key found. Set your provider API key env var or pass --api-key."
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
        cprint("No API key. Set your provider API key env var or use config.yaml.")
        sys.exit(1)

    agent = Agent(cfg)
    prompt = " ".join(message)
    result = asyncio.run(agent.step(prompt))
    cprint(result)


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
    from .tools import ALL_TOOLS

    print_table(
        "NoNail Tools",
        ["Name", "Description"],
        [[t.name, t.description] for t in ALL_TOOLS],
        col_widths=[28, 55],
    )


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
    cprint(f"Config saved to {DEFAULT_CONFIG_PATH}")
    cprint(f"Set your API key: export {selected_env}=...")


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
            cprint(f"  {icon} {label}")
        else:
            cprint(f"  ℹ️  {label}: {val}")

    servers = load_servers()
    if servers:
        cprint(f"  ℹ️  External MCP servers: {len(servers)} configured")
        for name, s in servers.items():
            status = "✅" if s.enabled else "⏸"
            cprint(f"     {status} {name} ({s.type})")
    else:
        cprint("  ℹ️  External MCP servers: none (see 'nonail mcp add')")


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
    from .mcp_client import load_servers

    servers = load_servers()
    if not servers:
        cprint("No external MCP servers configured. Run 'nonail mcp add' to add one.")
        return

    rows: list[list[str]] = []
    for name, s in servers.items():
        cmd = s.command + (" " + " ".join(s.args) if s.args else "") if s.type == "stdio" else s.url
        tools_str = ", ".join(s.tools) if s.tools != ["*"] else "*"
        status = "✅ enabled" if s.enabled else "⏸ disabled"
        rows.append([name, s.type, cmd, tools_str, status])

    print_table(
        "External MCP Servers",
        ["Name", "Type", "Command / URL", "Tools", "Status"],
        rows,
    )


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
        cprint(f"Server '{name}' already exists. Remove it first with 'nonail mcp remove {name}'.")
        sys.exit(1)

    env: dict = {}
    if env_str:
        try:
            env = _json.loads(env_str)
        except Exception:
            cprint("--env must be valid JSON, e.g. '{\"KEY\":\"val\"}'")
            sys.exit(1)

    headers: dict = {}
    if headers_str:
        try:
            headers = _json.loads(headers_str)
        except Exception:
            cprint("--headers must be valid JSON")
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
        cprint(f"✅ Added '{name}' (stdio): {cmd_display}")
    else:
        cprint(f"✅ Added '{name}' ({transport}): {url}")
    cprint(f"Run 'nonail mcp test {name}' to verify the connection.")


@mcp.command("remove")
@click.argument("name")
def mcp_remove(name):
    """Remove an external MCP server."""
    from .mcp_client import load_servers, save_servers

    servers = load_servers()
    if name not in servers:
        cprint(f"Server '{name}' not found.")
        sys.exit(1)
    del servers[name]
    save_servers(servers)
    cprint(f"Removed '{name}'.")


@mcp.command("enable")
@click.argument("name")
def mcp_enable(name):
    """Enable a previously disabled MCP server."""
    from .mcp_client import load_servers, save_servers

    servers = load_servers()
    if name not in servers:
        cprint(f"Server '{name}' not found.")
        sys.exit(1)
    servers[name].enabled = True
    save_servers(servers)
    cprint(f"Enabled '{name}'.")


@mcp.command("disable")
@click.argument("name")
def mcp_disable(name):
    """Disable an MCP server without removing it."""
    from .mcp_client import load_servers, save_servers

    servers = load_servers()
    if name not in servers:
        cprint(f"Server '{name}' not found.")
        sys.exit(1)
    servers[name].enabled = False
    save_servers(servers)
    cprint(f"Disabled '{name}'.")


@mcp.command("test")
@click.argument("name")
def mcp_test(name):
    """Test connection to an external MCP server and list its tools."""
    import asyncio

    from .mcp_client import MCPClientManager, load_servers

    servers = load_servers()
    if name not in servers:
        cprint(f"Server '{name}' not found.")
        sys.exit(1)

    server = servers[name]

    async def _test():
        manager = MCPClientManager()
        try:
            tools = await manager.connect_all({name: server})
            return tools
        finally:
            await manager.close()

    cprint(f"Connecting to '{name}'...")
    try:
        tools = asyncio.run(_test())
    except Exception as exc:
        cprint(f"❌ Connection failed: {exc}")
        sys.exit(1)

    if not tools:
        cprint("Connected but no tools were discovered.")
        return

    print_table(
        f"Tools from '{name}'",
        ["Tool name", "Description"],
        [[t.name, t.description] for t in tools],
    )
    cprint(f"✅ {len(tools)} tool(s) available.")


if __name__ == "__main__":
    cli()


# ---------------------------------------------------------------------------
# Zombie Mode sub-group (BETA / Experimental)
# ---------------------------------------------------------------------------


def _check_zombie_enabled(experimental: bool) -> None:
    """Gate: zombie mode must be explicitly enabled."""
    import os
    if experimental or os.environ.get("NONAIL_ZOMBIE") == "1":
        import nonail.zombie as zmod
        zmod.ZOMBIE_ENABLED = True
        return
    cprint(
        "⚠  Zombie Mode is an experimental (BETA) feature.\n"
        "   Enable it with one of:\n"
        "   • export NONAIL_ZOMBIE=1\n"
        "   • nonail zombie --experimental ...\n"
    )
    sys.exit(1)


@cli.group()
@click.option("--experimental", is_flag=True, hidden=True, help="Enable experimental zombie mode")
@click.pass_context
def zombie(ctx: click.Context, experimental: bool) -> None:
    """🧟 Zombie Mode — remote master/slave control (BETA).

    \b
    Master controls slaves remotely via WebSocket.
    User sends commands via Telegram, WhatsApp, or Discord.
    """
    _check_zombie_enabled(experimental)


# -- zombie master -----------------------------------------------------------


@zombie.group("master")
def zombie_master() -> None:
    """Manage the Zombie master server."""
    pass


@zombie_master.command("start")
@click.option("--host", default="0.0.0.0", help="Listen address")
@click.option("--port", default=8765, help="Listen port")
@click.option("--password", prompt=True, hide_input=True, help="Shared password for HMAC auth")
@click.option("--config", "-c", default=None, help="Path to master.yaml")
def zombie_master_start(host: str, port: int, password: str, config: str | None) -> None:
    """Start the zombie master WebSocket server."""
    import yaml
    from .zombie.master import ZombieMaster

    messaging_configs: dict = {}
    if config:
        with open(config) as f:
            data = yaml.safe_load(f) or {}
        messaging_configs = data.get("messaging", {})
        host = data.get("host", host)
        port = data.get("port", port)
        password = data.get("password", password)

    master = ZombieMaster(
        password=password,
        host=host,
        port=port,
        messaging_configs=messaging_configs,
    )
    try:
        asyncio.run(master.run())
    except KeyboardInterrupt:
        cprint("\nMaster stopped.")


@zombie_master.command("status")
def zombie_master_status() -> None:
    """Show master service status."""
    from .zombie.service.installer import service_status
    cprint(service_status("master"))


# -- zombie slave ------------------------------------------------------------


@zombie.group("slave")
def zombie_slave() -> None:
    """Manage zombie slave agents."""
    pass


@zombie_slave.command("start")
@click.option("--host", required=True, help="Master IP/hostname")
@click.option("--port", default=8765, help="Master port")
@click.option("--password", prompt=True, hide_input=True, help="Shared password")
@click.option("--id", "slave_id", default="", help="Slave identifier (default: hostname)")
def zombie_slave_start(host: str, port: int, password: str, slave_id: str) -> None:
    """Connect to a zombie master and wait for commands."""
    from .zombie.slave import ZombieSlave

    slave = ZombieSlave(
        master_host=host,
        master_port=port,
        password=password,
        slave_id=slave_id,
    )
    try:
        asyncio.run(slave.run())
    except KeyboardInterrupt:
        cprint("\nSlave stopped.")


# -- zombie slave service ----------------------------------------------------


@zombie_slave.group("service")
def zombie_slave_service() -> None:
    """Install/manage slave as a system service."""
    pass


@zombie_slave_service.command("install")
@click.option("--host", required=True, help="Master IP/hostname")
@click.option("--port", default=8765, help="Master port")
@click.option("--password", prompt=True, hide_input=True, help="Shared password")
def zombie_service_install(host: str, port: int, password: str) -> None:
    """Install the slave as a systemd/launchd service."""
    from .zombie.service.installer import install_service

    extra_args = f"--host {host} --port {port}"
    result = install_service("slave", extra_args, env_vars={"NONAIL_ZOMBIE": "1"})
    cprint(result)
    cprint(
        "Note: password must be set via config file for service mode."
    )


@zombie_slave_service.command("uninstall")
def zombie_service_uninstall() -> None:
    """Remove the slave system service."""
    from .zombie.service.installer import uninstall_service

    result = uninstall_service("slave")
    cprint(result)


@zombie_slave_service.command("status")
def zombie_service_status() -> None:
    """Show slave service status."""
    from .zombie.service.installer import service_status

    cprint(service_status("slave"))


# -- zombie config -----------------------------------------------------------


@zombie.command("config")
def zombie_config() -> None:
    """Interactive wizard to configure zombie master settings."""
    import yaml
    from pathlib import Path

    cfg_path = Path.home() / ".nonail" / "zombie" / "master.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if cfg_path.exists():
        with open(cfg_path) as f:
            data = yaml.safe_load(f) or {}

    cprint("\n🧟 Zombie Mode Configuration Wizard\n")

    data["port"] = click.prompt("Master port", default=data.get("port", 8765), type=int)
    data["password"] = click.prompt(
        "Shared password", default=data.get("password", ""), hide_input=True
    )

    # Telegram
    if click.confirm("\nConfigure Telegram bot?", default=bool(data.get("messaging", {}).get("telegram"))):
        tg = data.setdefault("messaging", {}).setdefault("telegram", {})
        tg["token"] = click.prompt("Telegram bot token", default=tg.get("token", ""))
        users = click.prompt(
            "Allowed Telegram user IDs (comma-separated, empty=all)",
            default=",".join(str(u) for u in tg.get("allowed_users", [])),
        )
        tg["allowed_users"] = [int(u.strip()) for u in users.split(",") if u.strip()]

    # WhatsApp
    if click.confirm("Configure WhatsApp (Twilio)?", default=bool(data.get("messaging", {}).get("whatsapp"))):
        wa = data.setdefault("messaging", {}).setdefault("whatsapp", {})
        wa["account_sid"] = click.prompt("Twilio Account SID", default=wa.get("account_sid", ""))
        wa["auth_token"] = click.prompt("Twilio Auth Token", default=wa.get("auth_token", ""), hide_input=True)
        wa["from_number"] = click.prompt("Twilio WhatsApp number", default=wa.get("from_number", ""))
        nums = click.prompt(
            "Allowed phone numbers (comma-separated, empty=all)",
            default=",".join(wa.get("allowed_numbers", [])),
        )
        wa["allowed_numbers"] = [n.strip() for n in nums.split(",") if n.strip()]

    # Discord
    if click.confirm("Configure Discord bot?", default=bool(data.get("messaging", {}).get("discord"))):
        dc = data.setdefault("messaging", {}).setdefault("discord", {})
        dc["token"] = click.prompt("Discord bot token", default=dc.get("token", ""), hide_input=True)
        dc["channel_id"] = click.prompt("Discord channel ID", default=dc.get("channel_id", 0), type=int)

    with open(cfg_path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)
    cfg_path.chmod(0o600)

    cprint(f"\n✅ Config saved to {cfg_path}")
    cprint("Start master with: nonail zombie --experimental master start --config " + str(cfg_path) + "\n")
