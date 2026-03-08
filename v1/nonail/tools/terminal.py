"""Tool to open interactive/TUI commands in a new terminal window."""

from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

from .base import Tool, ToolResult


class ExecTerminalTool(Tool):
    name = "exec_terminal"
    description = (
        "Open an interactive or TUI command (e.g. btop, htop, vim, nano, python) "
        "in a NEW terminal window/pane so it doesn't block the agent. "
        "Use this instead of bash for any command that needs a TTY or would take "
        "over the current terminal."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to run in a new terminal window.",
                },
                "title": {
                    "type": "string",
                    "description": "Optional window title.",
                    "default": "",
                },
            },
            "required": ["command"],
        }

    async def run(self, *, command: str, title: str = "", **_: Any) -> ToolResult:
        win_title = title or command.split()[0]

        # 1. tmux — open a new window in the current session
        if os.environ.get("TMUX"):
            tmux_cmd = f"tmux new-window -n {win_title!r} {command!r}"
            try:
                proc = await asyncio.create_subprocess_shell(
                    tmux_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, err = await proc.communicate()
                if proc.returncode == 0:
                    return ToolResult.ok(
                        f"Opened '{command}' in a new tmux window '{win_title}'."
                    )
                # fall through if tmux cmd failed
            except Exception:
                pass

        # 2. Try common terminal emulators
        pause = "; echo; read -p '[Press Enter to close]'"
        candidates: list[tuple[str, list[str]]] = [
            ("xterm", ["xterm", "-title", win_title, "-e", "sh", "-c", command + pause]),
            (
                "gnome-terminal",
                ["gnome-terminal", f"--title={win_title}", "--", "sh", "-c", command + pause],
            ),
            (
                "konsole",
                ["konsole", f"-p tabtitle={win_title}", "-e", "sh", "-c", command + pause],
            ),
            (
                "xfce4-terminal",
                ["xfce4-terminal", f"--title={win_title}", "-e", f"sh -c {command + pause!r}"],
            ),
            (
                "lxterminal",
                ["lxterminal", f"--title={win_title}", "-e", "sh", "-c", command + pause],
            ),
            (
                "tilix",
                ["tilix", "-t", win_title, "-e", "sh", "-c", command + pause],
            ),
        ]

        for term_bin, argv in candidates:
            if shutil.which(term_bin):
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *argv,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    return ToolResult.ok(
                        f"Opened '{command}' in {term_bin} (PID {proc.pid})."
                    )
                except Exception as exc:
                    return ToolResult.fail(f"Failed to launch {term_bin}: {exc}")

        return ToolResult.fail(
            "No supported terminal emulator found. "
            "Install xterm with: sudo apt install xterm"
        )
