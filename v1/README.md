<p align="center"><strong>🔨 NoNail</strong></p>
<p align="center">
  <em>Simplified, MCP-compatible AI agent with full computer access.</em><br>
  Inspired by <a href="https://github.com/zeroclaw-labs/zeroclaw">ZeroClaw</a> · Built with Python · Works with any LLM provider.
</p>

---

## What is NoNail?

NoNail is a **lightweight AI agent** that gives any LLM **full access to your computer** — shell commands, file system, process management, and system information — through a clean tool interface.

It runs in two modes:

| Mode | Description |
|------|-------------|
| **Interactive CLI** | Chat directly with the agent in your terminal |
| **MCP Server** | Expose tools via [Model Context Protocol](https://modelcontextprotocol.io) so any MCP client (Claude Desktop, Cursor, VS Code, etc.) can use them |

### Key features

- 🔌 **MCP-compatible** — plug into any MCP client as a standard tool server
- 🔄 **Provider-agnostic** — swap between OpenAI, Anthropic, OpenRouter, or local LLMs via config
- 🖥️ **Full computer access** — bash, files, processes, system info — all exposed to the LLM
- 🧩 **Extensible** — add new tools by implementing `Tool` ABC, YAML specs, or let the LLM suggest them
- 🔧 **Package Manager** — auto-detects apt/dnf/pacman/brew and lets the LLM install dependencies with user approval
- ⌨️ **CLI UX** — `/model` supports arrow-key selection and TAB completion is focused on slash commands/model IDs
- 🚀 **Native acceleration** — performance-sensitive string matching paths use an optional C++ extension
- ⚡ **Minimal** — no bloat, no frameworks, just Python + the MCP SDK

---

## Quick Start

### 1. Install

```bash
cd NoNail
pip install -e .
```

> During installation, NoNail builds the native C++ accelerator for your current device/CPU (when a C++ compiler is available).

### 2. Configure

```bash
# Option A: set your provider API key (example: Groq)
export GROQ_API_KEY="gsk-your-key-here"

# Option B: generate config file for your provider
nonail init --provider groq --model llama-3.3-70b-versatile
# → creates ~/.nonail/config.yaml
```

### 3. Use

#### Interactive chat

```bash
nonail chat
```

```
🔨 NoNail
Provider: openai | Model: gpt-4o
Type /quit to exit.

you> list all Python files in the current directory
  ⚙ bash(command='find . -name "*.py"')

./nonail/__init__.py
./nonail/agent.py
...
```

#### Single command

```bash
nonail run "what OS am I running?"
```

#### MCP server (for Claude Desktop, Cursor, etc.)

```bash
nonail serve
```

---

## Connecting as MCP Server

Add NoNail to your MCP client configuration:

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "nonail": {
      "command": "nonail",
      "args": ["serve"]
    }
  }
}
```

### Cursor / VS Code

```json
{
  "mcp": {
    "servers": {
      "nonail": {
        "command": "nonail",
        "args": ["serve"]
      }
    }
  }
}
```

After connecting, the MCP client will discover all NoNail tools automatically.

---

## Integrating community MCP servers

NoNail works **both ways** with MCP:

- **As a server** — expose its 18+ built-in tools to any MCP client (Claude Desktop, VS Code Copilot, Cursor…)
- **As a client** — connect to external community MCP servers (npm/npx, GitHub, HTTP) and use their tools inside the NoNail agent

### NoNail as MCP client (consuming external servers)

External MCP servers are managed with the `nonail mcp` command group. Their tools are automatically loaded when you start `nonail chat`.

```bash
# Add an npm/npx-based server (Node.js required)
nonail mcp add playwright --command npx --args "@playwright/mcp@latest"
nonail mcp add github --command npx \
    --args "-y @modelcontextprotocol/server-github" \
    --env '{"GITHUB_PERSONAL_ACCESS_TOKEN":"ghp_..."}'

# Add a remote HTTP/SSE server
nonail mcp add context7 --type http --url https://mcp.context7.com/mcp

# List, test, enable/disable, remove
nonail mcp list
nonail mcp test playwright      # connects and shows available tools
nonail mcp disable playwright   # keep configured but skip loading
nonail mcp remove playwright    # delete entry
```

Config is stored in `~/.nonail/mcp-clients.json` (same format as `~/.copilot/mcp-config.json`):

```json
{
  "mcpServers": {
    "playwright": {
      "type": "stdio",
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "tools": ["*"],
      "enabled": true
    },
    "context7": {
      "type": "http",
      "url": "https://mcp.context7.com/mcp",
      "tools": ["*"],
      "enabled": true
    }
  }
}
```

Once added, launch `nonail chat` — external tools appear alongside built-in ones, prefixed with the server name (e.g. `[playwright] browser_navigate`).

### NoNail as MCP server (being consumed by clients)

Add NoNail to any MCP client by pointing it at `nonail serve`:

**GitHub Copilot CLI** — run `/mcp add`, choose **STDIO**, command `nonail`, args `serve`:

```json
// ~/.copilot/mcp-config.json
{
  "mcpServers": {
    "nonail": {
      "type": "stdio",
      "command": "nonail",
      "args": ["serve"],
      "env": { "GROQ_API_KEY": "your-key" },
      "tools": ["*"]
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`) and **Cursor / VS Code** use the same `command`/`args` pattern.


## Available Tools

| Tool | Description |
|------|-------------|
| `bash` | Execute any shell command |
| `read_file` | Read file contents |
| `write_file` | Create or overwrite a file |
| `list_directory` | List directory contents |
| `search_files` | Recursive glob search |
| `search_text` | Recursive text/regex search with line numbers |
| `make_directory` | Create directories (`mkdir -p`) |
| `copy_path` | Copy files/directories |
| `move_path` | Move or rename files/directories |
| `delete_path` | Delete files/directories |
| `run_python` | Execute Python snippets locally |
| `start_background_command` | Start detached long-running commands |
| `http_request` | Call APIs via HTTP methods |
| `download_file` | Download URL to local path |
| `cron_manage` | List/add/remove scheduled cron jobs |
| `process_list` | List running processes |
| `process_kill` | Send signals to processes |
| `system_info` | OS, arch, env, network info |
| `package_manager` | Install/remove/search system packages (auto-detects apt/dnf/pacman/brew/etc) |
| `suggest_tool` | LLM proposes a new custom tool for user approval |

Run `nonail tools` or `/tools` inside chat to see all available tools (including custom ones).

### Daily automation ideas

- **Morning ops check:** use `cron_manage` to schedule periodic checks and `http_request` to query service/health endpoints.
- **Workspace hygiene:** combine `search_text`, `copy_path`, `move_path`, and `delete_path` for file cleanup/refactors.
- **Background jobs:** start long tasks with `start_background_command` and inspect with `process_list`.
- **Scripting on demand:** use `run_python` for quick local data transformations and automation helpers.

### Custom Tools & Dynamic Tool Creation

NoNail supports user-defined custom tools stored as YAML files in `~/.nonail/custom-tools/`. These are loaded automatically at startup.

#### Creating custom tools manually

```yaml
# ~/.nonail/custom-tools/screenshot.yaml
name: screenshot
description: "Capture a screenshot of the current desktop"
type: shell
command_template: "scrot {output}"
parameters:
  output:
    type: string
    required: true
    description: "Output file path"
requires:
  - scrot
```

Or via the interactive CLI:

```
/tools add screenshot
  Description: Capture a screenshot
  Type (shell/python) [shell]: shell
  Command template: scrot {output}
  Requires (comma-sep): scrot
✓ Tool 'screenshot' created and loaded.
```

#### LLM-suggested tools

The LLM can dynamically propose new tools using the `suggest_tool` capability. When it does, you'll see:

```
╭─ 🧩 Tool Suggestion ──────────────────────────╮
│ Name:    screenshot                            │
│ Desc:    Capture desktop screenshot            │
│ Type:    shell                                 │
│ Command: scrot {output}                        │
│ Requires: scrot                                │
│                                                │
│ [A]pprove  [E]dit  [R]eject                    │
╰────────────────────────────────────────────────╯
```

Approved tools are saved as YAML and immediately available in the session.

#### Package Manager

The `package_manager` tool auto-detects your system's package manager and provides unified operations. The LLM can use it to install missing dependencies:

```
🔧 Package Manager
   The agent wants to install package(s):
   • ffmpeg
   Command: sudo apt install -y ffmpeg
   Package manager: apt
   Proceed? [Y/n] ›
```

Supported: apt, dnf, yum, pacman, zypper, brew, apk, pkg.

---

## Configuration

NoNail reads from `~/.nonail/config.yaml` (create with `nonail init`):

```yaml
provider: openai          # openai | anthropic | groq | gemini
model: gpt-4o             # any model supported by the provider
# api_base: https://openrouter.ai/api/v1  # for OpenRouter / local LLMs
api_key_env: OPENAI_API_KEY
max_iterations: 25

mcp_server:
  enabled: true
  transport: stdio

cache:
  enabled: true
  path: ~/.nonail/cache.db
  mode: aggressive      # aggressive | safe | off
  max_entries: 5000
  ttl_seconds: 86400
```

When a provider/model hits rate limits, NoNail can auto-fallback to another available provider key
(priority: `GEMINI_API_KEY` → `ANTHROPIC_API_KEY` → `OPENAI_API_KEY` → `GROQ_API_KEY`) while
continuing to use the same SQLite cache.

### Using with OpenRouter

```yaml
provider: openai
model: anthropic/claude-sonnet-4-20250514
api_base: https://openrouter.ai/api/v1
api_key_env: OPENROUTER_API_KEY
```

### Using with Anthropic

```yaml
provider: anthropic
model: claude-sonnet-4-20250514
api_key_env: ANTHROPIC_API_KEY
```

### Using with Groq (fast, free tier available)

```yaml
provider: groq
model: llama-3.3-70b-versatile
api_key_env: GROQ_API_KEY
```

List available Groq models: https://console.groq.com/docs/models

### Using with local LLMs (Ollama, LM Studio, etc.)

```yaml
provider: openai
model: llama3
api_base: http://localhost:11434/v1
api_key_env: NONAIL_API_KEY  # set to any non-empty string
```

---

## CLI Reference

```
nonail chat       Interactive chat session (with /slash commands)
nonail run MSG    Run a single prompt
nonail serve      Start MCP server (stdio)
nonail tools      List available tools
nonail init       Generate default config
nonail doctor     Check configuration health
nonail mcp        Manage external community MCP servers
nonail zombie     🧟 Remote master/slave control (BETA)
```

### Slash Commands (inside `nonail chat`)

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/tools [add\|remove]` | List, add, or remove tools (built-in + custom + external) |
| `/model [name\|list\|select]` | List models, select with arrows, or switch directly |
| `/provider [name]` | Show/switch provider |
| `/config [key=value\|save]` | Show/update/save config |
| `/history` | Conversation summary |
| `/clear` | Reset conversation |
| `/compact` | Trim old context |
| `/status` | Session stats |
| `/mcp` | Show external MCP servers |
| `/cache [status\|clear\|mode\|bypass]` | Manage execution cache |
| `/cache-limit <max_entries> [ttl_seconds]` | Tune SQLite cache limits |
| `/quit` | Exit |

---

## 🧟 Zombie Mode (Experimental / BETA)

Remote master/slave system: a central master controls multiple machines (slaves) via WebSocket. Users send commands through **Telegram**, **WhatsApp**, or **Discord** — the master routes them to slaves and returns results.

> **This is an experimental feature.** Enable it with `export NONAIL_ZOMBIE=1` or the `--experimental` flag.

### Architecture

```
  [User]
     │ Telegram / WhatsApp / Discord
     ▼
  [MASTER]  ◄── nonail zombie master start
  WebSocket Server (asyncio)
  Slave Registry + Bot Layer
     │ WebSocket (HMAC-SHA256 auth)
     ├──► [SLAVE-1] — runs NoNail tools
     ├──► [SLAVE-2]
     └──► [SLAVE-N]
```

### Quick Start

```bash
# 1. On the control machine — start master
export NONAIL_ZOMBIE=1
nonail zombie master start --port 8765 --password my-secret

# 2. On each target machine — start slave
export NONAIL_ZOMBIE=1
nonail zombie slave start --host 192.168.1.100 --port 8765 --password my-secret

# 3. (Optional) Configure messaging bots
nonail zombie config   # interactive wizard for Telegram/WhatsApp/Discord
nonail zombie master start --config ~/.nonail/zombie/master.yaml
```

### Messaging Setup

| Platform | Library | Config Key | Auth |
|----------|---------|------------|------|
| **Telegram** | aiogram 3.x | `messaging.telegram.token` | `allowed_users` (Telegram user IDs) |
| **WhatsApp** | Twilio | `messaging.whatsapp.account_sid` | `allowed_numbers` (phone numbers) |
| **Discord** | discord.py | `messaging.discord.token` | `allowed_guild_ids` + `channel_id` |

Install messaging dependencies:
```bash
pip install nonail[telegram]   # or [whatsapp] [discord] [zombie] for all
```

### Sending Commands via Messaging

```
# Telegram / WhatsApp / Discord:
uptime                        # → runs on first connected slave
@slave-2 ls /var/log          # → runs on specific slave
/slaves                       # → list connected slaves
```

### Install as System Service

```bash
# Linux (systemd)
nonail zombie slave service install --host 192.168.1.100 --password my-secret

# Check status / remove
nonail zombie slave service status
nonail zombie slave service uninstall
```

### Security

- HMAC-SHA256 on every message (password never sent in plaintext)
- Replay protection: timestamp ±30s tolerance
- Per-platform user whitelists
- Audit log at `~/.nonail/zombie/master.log`

---

## Adding Custom Tools

Create a new file in `nonail/tools/` implementing the `Tool` base class:

```python
from nonail.tools.base import Tool, ToolResult

class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful."

    def parameters_schema(self):
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "..."},
            },
            "required": ["input"],
        }

    async def run(self, *, input: str, **_):
        return ToolResult.ok(f"Result: {input}")
```

Then register it in `nonail/tools/__init__.py` by adding it to `ALL_TOOLS`.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    NoNail Agent                     │
│                                                     │
│  ┌──────────┐   ┌───────────┐   ┌───────────────┐  │
│  │ Provider  │   │   Agent   │   │  MCP Server   │  │
│  │ (OpenAI,  │◄─►│   Loop    │◄─►│  (FastMCP)    │  │
│  │ Anthropic,│   │           │   │               │  │
│  │ Local)    │   └─────┬─────┘   └───────────────┘  │
│  └──────────┘         │                             │
│                 ┌─────▼─────┐                       │
│                 │   Tools   │                       │
│                 ├───────────┤                       │
│                 │ bash      │                       │
│                 │ read_file │                       │
│                 │ write_file│                       │
│                 │ list_dir  │                       │
│                 │ search    │                       │
│                 │ processes │                       │
│                 │ sysinfo   │                       │
│                 └───────────┘                       │
└─────────────────────────────────────────────────────┘
```

Inspired by [ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw)'s trait-based, swappable architecture — simplified for Python and MCP.

---

## License

MIT
