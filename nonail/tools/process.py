"""Process management tool — list, kill, inspect running processes."""

from __future__ import annotations

import asyncio
from typing import Any

from .base import Tool, ToolResult


class ProcessListTool(Tool):
    name = "process_list"
    description = "List running processes (like ps aux)."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Optional grep filter for process names.",
                },
            },
        }

    async def run(self, *, filter: str | None = None, **_: Any) -> ToolResult:
        cmd = "ps aux"
        if filter:
            cmd += f" | grep -i {filter!r} | grep -v grep"
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return ToolResult.ok(stdout.decode(errors="replace").strip())


class ProcessKillTool(Tool):
    name = "process_kill"
    description = "Send a signal to a process by PID."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "Process ID."},
                "signal": {
                    "type": "integer",
                    "description": "Signal number (default 15 = SIGTERM).",
                    "default": 15,
                },
            },
            "required": ["pid"],
        }

    async def run(self, *, pid: int, signal: int = 15, **_: Any) -> ToolResult:
        import os as _os
        import signal as _sig

        try:
            _os.kill(pid, signal)
            return ToolResult.ok(f"Sent signal {signal} to PID {pid}")
        except ProcessLookupError:
            return ToolResult.fail(f"PID {pid} not found")
        except PermissionError:
            return ToolResult.fail(f"Permission denied for PID {pid}")
        except Exception as exc:
            return ToolResult.fail(str(exc))
