"""Zombie Mode — Slave agent (WebSocket client with auto-reconnect)."""

from __future__ import annotations

import asyncio
import logging
import platform
import time
from typing import Any

import websockets

from .protocol import (
    MsgType,
    ZombieMessage,
    make_hello,
    make_pong,
    make_result,
)

logger = logging.getLogger("nonail.zombie.slave")


class ZombieSlave:
    def __init__(
        self,
        master_host: str,
        master_port: int = 8765,
        password: str = "",
        slave_id: str = "",
        reconnect_max: float = 60.0,
    ):
        self.master_host = master_host
        self.master_port = master_port
        self.password = password
        self.slave_id = slave_id or platform.node()
        self.reconnect_max = reconnect_max
        self._tools: dict[str, Any] = {}
        self._load_tools()

    # -- tools ---------------------------------------------------------------

    def _load_tools(self) -> None:
        from nonail.tools import ALL_TOOLS
        self._tools = {t.name: t for t in ALL_TOOLS}

    async def _execute(self, tool_name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Run a NoNail tool and return (output, is_error)."""
        tool = self._tools.get(tool_name)
        if not tool:
            return f"Unknown tool: {tool_name}", True
        try:
            result = await tool.run(**args)
            if result.is_error:
                return result.error, True
            return result.output, False
        except Exception as exc:
            return f"Execution error: {exc}", True

    # -- system info ---------------------------------------------------------

    def _sys_info(self) -> dict[str, Any]:
        import os
        return {
            "hostname": platform.node(),
            "os": platform.system(),
            "arch": platform.machine(),
            "python": platform.python_version(),
            "user": os.environ.get("USER", os.environ.get("USERNAME", "?")),
            "tools": len(self._tools),
        }

    # -- connection loop -----------------------------------------------------

    async def run(self) -> None:
        """Connect to master with exponential backoff reconnect."""
        backoff = 1.0
        uri = f"ws://{self.master_host}:{self.master_port}"

        while True:
            try:
                print(f"🧟 Connecting to master at {uri} ...")
                async with websockets.connect(uri) as ws:
                    backoff = 1.0  # reset on success
                    print(f"✅ Connected as '{self.slave_id}'")

                    # Send HELLO
                    hello = make_hello(self.slave_id, self._sys_info(), self.password)
                    await ws.send(hello)

                    # Message loop
                    async for raw in ws:
                        try:
                            msg = ZombieMessage.from_json(raw)
                        except Exception:
                            continue

                        if not msg.verify(self.password):
                            logger.warning("Invalid HMAC — ignoring message")
                            continue

                        await self._dispatch(ws, msg)

            except (
                websockets.exceptions.ConnectionClosed,
                ConnectionRefusedError,
                OSError,
            ) as exc:
                print(f"⚠ Disconnected: {exc}. Retrying in {backoff:.0f}s ...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.reconnect_max)
            except asyncio.CancelledError:
                print("Slave shutting down.")
                break

    async def _dispatch(self, ws: Any, msg: ZombieMessage) -> None:
        """Handle an incoming message from the master."""

        if msg.type == MsgType.PING:
            await ws.send(make_pong(self.password))
            return

        if msg.type == MsgType.EXEC:
            tool = msg.payload.get("tool", "")
            args = msg.payload.get("args", {})
            logger.info(f"EXEC: {tool}({args})")
            print(f"  ⚙ {tool}({args})")

            output, is_error = await self._execute(tool, args)

            reply = make_result(msg.id, output, is_error, self.password)
            await ws.send(reply)
            return

        if msg.type == MsgType.STATUS:
            info = self._sys_info()
            info["uptime"] = time.time()
            resp = ZombieMessage(type=MsgType.RESULT, payload=info)
            resp.sign(self.password)
            await ws.send(resp.to_json())
            return

        if msg.type == MsgType.ERROR:
            detail = msg.payload.get("detail", "unknown")
            print(f"  ❌ Master error: {detail}")
            return
