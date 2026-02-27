"""Bash / shell execution tool — gives the LLM full command-line access."""

from __future__ import annotations

import asyncio
from typing import Any

from .base import Tool, ToolResult


class BashTool(Tool):
    name = "bash"
    description = (
        "Execute an arbitrary shell command on the host machine and return "
        "stdout/stderr. Use this for any OS-level operation."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to wait (default 120).",
                    "default": 120,
                },
            },
            "required": ["command"],
        }

    async def run(self, *, command: str, timeout: int = 120, **_: Any) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            output = stdout.decode(errors="replace")
            err = stderr.decode(errors="replace")
            if proc.returncode != 0:
                return ToolResult(
                    output=output,
                    error=f"exit code {proc.returncode}\n{err}",
                    is_error=True,
                )
            combined = output + ("\n" + err if err else "")
            return ToolResult.ok(combined.strip())
        except asyncio.TimeoutError:
            return ToolResult.fail(f"Command timed out after {timeout}s")
        except Exception as exc:
            return ToolResult.fail(str(exc))
