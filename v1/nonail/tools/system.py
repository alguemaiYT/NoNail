"""System information tool — hardware, OS, network, environment."""

from __future__ import annotations

import os
import platform
import socket
from typing import Any

from .base import Tool, ToolResult


class SystemInfoTool(Tool):
    name = "system_info"
    description = (
        "Return system information: OS, architecture, hostname, "
        "user, environment variables, etc."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["all", "os", "env", "network"],
                    "description": "Which section to return (default: all).",
                    "default": "all",
                },
            },
        }

    async def run(self, *, section: str = "all", **_: Any) -> ToolResult:
        parts: list[str] = []

        if section in ("all", "os"):
            parts.append(
                f"OS: {platform.system()} {platform.release()}\n"
                f"Arch: {platform.machine()}\n"
                f"Python: {platform.python_version()}\n"
                f"Hostname: {socket.gethostname()}\n"
                f"User: {os.environ.get('USER', 'unknown')}\n"
                f"Home: {os.path.expanduser('~')}\n"
                f"CWD: {os.getcwd()}"
            )

        if section in ("all", "env"):
            safe_env = {
                k: v
                for k, v in sorted(os.environ.items())
                if "KEY" not in k.upper()
                and "SECRET" not in k.upper()
                and "TOKEN" not in k.upper()
                and "PASS" not in k.upper()
            }
            parts.append(
                "Environment (sensitive keys hidden):\n"
                + "\n".join(f"  {k}={v}" for k, v in list(safe_env.items())[:60])
            )

        if section in ("all", "network"):
            try:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                parts.append(f"Network: {hostname} → {ip}")
            except Exception:
                parts.append("Network: unable to resolve")

        return ToolResult.ok("\n\n".join(parts))
