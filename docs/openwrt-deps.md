# NoNail — Dependency Audit for OpenWrt

This document audits every dependency of NoNail, evaluating size, purpose, and
whether it is required for a minimal OpenWrt deployment (≤ 64 MB RAM).

## Core dependencies (`[project.dependencies]`)

| Package | Installed size¹ | Subsystem | Required? | Notes |
|---------|----------------|-----------|-----------|-------|
| `mcp>=1.0.0` | ~1.5 MB | MCP server/client | **Yes** (if MCP used) | Needed for `nonail serve` and external MCP servers. Could be made optional if MCP is not needed. Pulls in `pydantic`, `httpx`, `anyio`, etc. |
| `openai>=1.0.0` | ~3 MB | Providers | **Lazy** | Only loaded when provider=openai. Brings `httpx`, `pydantic`. Largest single dep. |
| `anthropic>=0.30.0` | ~2 MB | Providers | **Lazy** | Only loaded when provider=anthropic. Brings `httpx`, `pydantic`. |
| `pyyaml>=6.0` | ~600 KB | Config | **Yes** | Small, C-accelerated. Used for config loading. |
| `click>=8.0` | ~400 KB | CLI | **Yes** | CLI framework, no heavy deps. |

> ¹ Approximate installed sizes on x86_64 Linux with Python 3.12. Actual sizes
> on OpenWrt (MIPS/ARM) may vary.

## Transitive dependencies (heaviest)

| Package | Pulled by | Installed size | Notes |
|---------|-----------|----------------|-------|
| `pydantic` + `pydantic-core` | `mcp`, `openai`, `anthropic` | ~8 MB | Rust-compiled core. Largest transitive dep. |
| `httpx` + `httpcore` | `openai`, `anthropic`, `mcp` | ~1 MB | HTTP client. |
| `anyio` | `httpx`, `mcp` | ~300 KB | Async compatibility layer. |
| `certifi` | `httpx` | ~300 KB | CA bundle. |
| `idna` | `httpx` | ~300 KB | Internationalized domain names. |
| `sniffio` | `anyio` | ~20 KB | Async library detection. |

## Optional dependencies (`[project.optional-dependencies]`)

| Extra | Packages | Subsystem | Notes |
|-------|----------|-----------|-------|
| `dev` | `pytest`, `ruff` | Development | Not installed in production |
| `telegram` | `aiogram>=3.0` | Zombie messaging | Only for zombie mode Telegram bot |
| `whatsapp` | `twilio>=8.0`, `aiohttp>=3.9` | Zombie messaging | Only for zombie mode WhatsApp |
| `discord` | `discord.py>=2.3` | Zombie messaging | Only for zombie mode Discord |
| `zombie` | All messaging + `websockets>=13.0` | Zombie mode | Full zombie feature set |

## Removed dependencies

| Package | Previous role | Replacement |
|---------|-------------|-------------|
| `rich>=13.0` | Terminal UI (tables, panels, colors) | `nonail/ui.py` — plain `print()` helpers |
| `websockets>=13.0` (from core) | Moved to `zombie` extra | Lazy import inside `zombie/master.py` and `zombie/slave.py` |

## Size budget estimate (minimal install)

For a **minimal** OpenWrt deployment (chat mode only, single provider):

| Component | Estimated size |
|-----------|---------------|
| NoNail source | ~150 KB |
| `click` | ~400 KB |
| `pyyaml` (C ext) | ~600 KB |
| `openai` | ~3 MB |
| `pydantic` + core | ~8 MB |
| `httpx` + deps | ~2 MB |
| **Total** | **~14 MB** |

With `mcp` support add ~1.5 MB. With `anthropic` add ~2 MB.

## Recommendations for further reduction

1. **Replace `openai`/`anthropic` SDKs with raw `httpx`**: The provider SDKs
   wrap simple REST APIs. A thin `httpx`-based provider could eliminate ~5 MB
   and the `pydantic` dependency entirely.

2. **Make `mcp` optional**: If MCP isn't needed, skip the `mcp` SDK and save
   ~1.5 MB + shared `pydantic` savings.

3. **Use `ujson` or stdlib `json`**: Already using stdlib. No action needed.

4. **Strip `.pyc` and `__pycache__`**: Save ~30% of Python file sizes by
   shipping only `.py` files (or only `.pyc` with `compileall`).

5. **Vendor minimal deps**: For extreme size constraints, vendor only the
   specific modules used from each package.
