# Copilot Instructions

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run the active test suite
.venv/bin/pytest tests -q

# Run a single test file
.venv/bin/pytest tests/test_fallback.py -q

# Run a single test by name
.venv/bin/pytest tests -q -k "test_rate_limit_error_detection_patterns"

# Lint
.venv/bin/ruff check nonail tests
```

The optional C++ accelerator (`nonail/_fastcore.cpp`) is compiled by `setup.py` using `-O3 -march=native`. It has a pure-Python fallback in `nonail/fastpath.py`, so tests do not depend on the extension being present.

Target `tests/` explicitly when running pytest from the repo root. A bare `pytest` also collects archived `v1/tests`, which currently collides with the active suite because the files share the same module names.

## Architecture

NoNail is a provider-agnostic AI agent with three main runtime paths:

1. **`nonail chat`** — interactive readline REPL; calls `Agent.step()` per turn
2. **`nonail serve`** — MCP server via FastMCP; exposes all tools to MCP clients (Claude Desktop, Cursor, VS Code)
3. **`nonail zombie`** — experimental WebSocket master/slave control path, gated behind `NONAIL_ZOMBIE=1` or `--experimental`

The agent also acts as an **MCP client**, consuming external MCP servers whose tools are proxied as `MCPClientTool` instances alongside built-ins.

**Request flow (`agent.py`):**
```
Agent.step(user_input)
  → _query_llm_with_fallback()   # LLM call with cache + rate-limit fallback
  → parse tool_calls from response
  → for each tool_call:
      check tool cache → prompt approval (unless /yolo) → tool.run(**args)
  → append results to history → repeat until no tool_calls or max_iterations
```

**Module map:**

| Module | Role |
|---|---|
| `agent.py` | Core loop, slash command dispatch, fallback logic, cache integration |
| `config.py` | `Config` dataclass; loads `~/.nonail/config.yaml` → env vars → defaults |
| `cache.py` | SQLite-backed `CacheStore`; LLM responses + tool results + audit trail |
| `providers/` | One file per LLM provider, all implement `Provider` ABC (`chat()` method) |
| `tools/` | 21 built-in `Tool` subclasses + YAML dynamic tools + MCP proxy tools |
| `mcp_server.py` | Registers all tools with FastMCP for external MCP clients |
| `mcp_client.py` | `MCPClientManager`; loads `~/.nonail/mcp-clients.json`, connects to external servers, and wraps their tools as proxies |
| `__main__.py` | Click CLI (`chat`, `run`, `serve`, `tools`, `mcp`, `zombie`) |
| `fastpath.py` | Optional C++ string-matching accelerator with Python fallback |
| `zombie/` | Experimental WebSocket master/slave with Telegram/Discord/WhatsApp bots (BETA) |

Normal chat mode stays lightweight by deferring optional imports until the relevant entrypoints run: MCP SDK imports happen inside `run_mcp_server()` / `MCPClientManager`, zombie code is imported only when the experimental gate is enabled, and the native fast path falls back cleanly to Python.

## Key Conventions

### Adding a new built-in tool
1. Create a `Tool` subclass (in `tools/` or a new file) with `name`, `description`, `parameters_schema()`, and `async run(**kwargs) -> ToolResult`
2. Add an instance to the `ALL_TOOLS` list in `tools/__init__.py`
3. Keep the return type as `ToolResult`; both the agent loop and MCP server wrapper expect that contract
4. `to_openai_schema()` is inherited from the ABC — don't override unless needed

### Adding a new LLM provider
1. Subclass `Provider` from `providers/base.py`; implement `provider_name`, `chat()`, and optionally `list_models()`
2. Register it in the `PROVIDERS` dict in `agent.py` (or wherever provider lookup lives)
3. Add its rate-limit error patterns to `RATE_LIMIT_PATTERNS` in `agent.py` if different

### Adding a slash command
1. Add the command string to the `SLASH_COMMANDS` tuple
2. Implement `_cmd_<name>(self, args: str)` method on `Agent`
3. Register it in the `handlers` dict inside `_handle_slash()`
4. Add TAB-completion candidates to `_completion_candidates()` if the command takes arguments

### Provider fallback
Auto-triggers on rate-limit errors. Priority order (first available API key wins):
`GEMINI_API_KEY` → `ANTHROPIC_API_KEY` → `OPENAI_API_KEY` → `GROQ_API_KEY`

Cache is shared across the fallback chain — a cache hit on the original provider is used even if the active provider changed.

### Cache system
`CacheStore` in `cache.py` uses four SQLite tables:
- `llm_cache` — keyed by `llm_hash(provider, model, messages)`
- `tool_cache` — keyed by `tool_hash(tool_name, args, cwd)`
- `loop_runs` / `loop_events` — audit trail for sessions

Cache modes: `aggressive` (all tools), `safe` (read-only tools only), `off`. Controlled via `/cache mode <mode>` or config.

### Config loading
`Config.load()` priority: `~/.nonail/config.yaml` → environment variables → hardcoded defaults. API keys are resolved by checking `config.api_key`, then falling back to the env var named in `config.api_key_env`.

Config and MCP client files are written with `0600` permissions because they may reference API keys or tokens (`config.py`, `mcp_client.py`).

### Async throughout
All provider `chat()` calls, tool `run()` methods, and MCP operations are `async`. The agent loop runs under `asyncio.run()`. Never add blocking I/O to these paths.

### Optional features stay lazy
Keep optional dependencies behind runtime imports instead of module-level imports. This pattern is used for MCP SDK access, zombie messaging backends, and the native `_fastcore` accelerator so the default chat/run path does not require every extra to be installed.

### Custom YAML tools
Users place `.yaml` files in `~/.nonail/custom-tools/`. Each defines `name`, `description`, `type` (`shell` or `python`), `command_template`, and `parameters`. Loaded at startup via `load_custom_tools()` in `tools/dynamic.py`.
