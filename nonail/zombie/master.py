"""Zombie Mode — Master server (WebSocket + messaging bots)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import websockets
from websockets.asyncio.server import ServerConnection

from .protocol import MsgType, ZombieMessage, make_error, make_ping

logger = logging.getLogger("nonail.zombie.master")

ZOMBIE_DIR = Path.home() / ".nonail" / "zombie"
AUDIT_LOG = ZOMBIE_DIR / "master.log"


# ---------------------------------------------------------------------------
# Slave record
# ---------------------------------------------------------------------------


class SlaveInfo:
    def __init__(self, ws: ServerConnection, slave_id: str, meta: dict[str, Any]):
        self.ws = ws
        self.slave_id = slave_id
        self.meta = meta
        self.last_seen = time.time()


# ---------------------------------------------------------------------------
# Master
# ---------------------------------------------------------------------------


class ZombieMaster:
    def __init__(
        self,
        password: str,
        host: str = "0.0.0.0",
        port: int = 8765,
        timeout: float = 30.0,
        messaging_configs: dict[str, dict] | None = None,
    ):
        self.password = password
        self.host = host
        self.port = port
        self.timeout = timeout
        self.slaves: dict[str, SlaveInfo] = {}
        self._pending: dict[str, asyncio.Future] = {}
        self._bots: list[Any] = []
        self._messaging_configs = messaging_configs or {}
        self._setup_logging()

    # -- logging -------------------------------------------------------------

    def _setup_logging(self) -> None:
        ZOMBIE_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(AUDIT_LOG)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def _audit(self, msg: str) -> None:
        logger.info(msg)

    # -- slave management ----------------------------------------------------

    def list_slaves(self) -> list[dict[str, Any]]:
        return [
            {
                "id": s.slave_id,
                "last_seen": s.last_seen,
                "meta": s.meta,
            }
            for s in self.slaves.values()
        ]

    async def send_to_slave(
        self, slave_id: str, tool: str, args: dict[str, Any]
    ) -> str:
        """Send EXEC to a slave and wait for RESULT (with timeout)."""
        slave = self.slaves.get(slave_id)
        if not slave:
            return f"[error] Slave '{slave_id}' not connected."

        from .protocol import make_exec

        raw = make_exec(tool, args, self.password, target=slave_id)
        msg_id = json.loads(raw)["id"]

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut

        try:
            await slave.ws.send(raw)
            self._audit(f"EXEC → {slave_id}: {tool}({args})")
            result = await asyncio.wait_for(fut, timeout=self.timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            return f"[timeout] Slave '{slave_id}' did not respond in {self.timeout}s."
        except Exception as exc:
            self._pending.pop(msg_id, None)
            return f"[error] {exc}"

    # -- command handler (from messaging bots) --------------------------------

    async def handle_user_command(self, sender_id: str, text: str) -> str:
        """Parse user text and route to the right slave."""
        text = text.strip()
        if not text:
            return "Empty command."

        # /slaves  — list connected slaves
        if text.lower() in ("/slaves", "!slaves", "/list"):
            slaves = self.list_slaves()
            if not slaves:
                return "No slaves connected."
            lines = [f"🖥 Connected slaves ({len(slaves)}):"]
            for s in slaves:
                ago = int(time.time() - s["last_seen"])
                lines.append(f"  • {s['id']}  (seen {ago}s ago)")
            return "\n".join(lines)

        # @slave-id command  — send to specific slave
        if text.startswith("@"):
            parts = text.split(None, 1)
            target = parts[0][1:]
            cmd = parts[1] if len(parts) > 1 else ""
            if not cmd:
                return f"Usage: @{target} <command>"
            return await self.send_to_slave(target, "bash", {"command": cmd})

        # Default: send to first connected slave
        if not self.slaves:
            return "No slaves connected."
        default_slave = next(iter(self.slaves))
        return await self.send_to_slave(default_slave, "bash", {"command": text})

    # -- WebSocket handler ----------------------------------------------------

    async def _ws_handler(self, ws: ServerConnection) -> None:
        remote = ws.remote_address
        self._audit(f"Connection from {remote}")
        slave_id: str | None = None

        try:
            async for raw in ws:
                try:
                    msg = ZombieMessage.from_json(raw)
                except Exception:
                    await ws.send(make_error("Invalid message format.", self.password))
                    continue

                if not msg.verify(self.password):
                    await ws.send(make_error("Authentication failed.", self.password))
                    continue

                # --- HELLO ---
                if msg.type == MsgType.HELLO:
                    slave_id = msg.payload.get("slave_id", str(remote))
                    self.slaves[slave_id] = SlaveInfo(ws, slave_id, msg.payload)
                    self._audit(f"HELLO from {slave_id} ({msg.payload})")
                    continue

                # --- PONG ---
                if msg.type == MsgType.PONG:
                    if slave_id and slave_id in self.slaves:
                        self.slaves[slave_id].last_seen = time.time()
                    continue

                # --- RESULT ---
                if msg.type == MsgType.RESULT:
                    exec_id = msg.payload.get("exec_id", "")
                    fut = self._pending.pop(exec_id, None)
                    output = msg.payload.get("output", "")
                    is_error = msg.payload.get("is_error", False)
                    result_text = f"{'⚠ ERROR: ' if is_error else ''}{output}"
                    if fut and not fut.done():
                        fut.set_result(result_text)
                    self._audit(f"RESULT from {slave_id}: {result_text[:200]}")
                    continue

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if slave_id and slave_id in self.slaves:
                del self.slaves[slave_id]
                self._audit(f"Slave disconnected: {slave_id}")

    # -- ping loop -----------------------------------------------------------

    async def _ping_loop(self) -> None:
        while True:
            await asyncio.sleep(15)
            dead = []
            for sid, info in list(self.slaves.items()):
                try:
                    await info.ws.send(make_ping(self.password))
                except Exception:
                    dead.append(sid)
            for sid in dead:
                self.slaves.pop(sid, None)
                self._audit(f"Slave lost (ping failed): {sid}")

    # -- messaging bots -------------------------------------------------------

    async def _start_bots(self) -> None:
        for name, cfg in self._messaging_configs.items():
            try:
                bot = self._create_bot(name, cfg)
                if bot:
                    self._bots.append(bot)
                    asyncio.create_task(bot.start())
                    self._audit(f"Bot started: {name}")
            except Exception as exc:
                self._audit(f"Bot {name} failed to start: {exc}")

    def _create_bot(self, name: str, cfg: dict) -> Any:
        if name == "telegram":
            try:
                from .messaging.telegram_bot import TelegramBot
                return TelegramBot(cfg, self.handle_user_command)
            except ImportError:
                logger.warning("aiogram not installed — skip Telegram bot")
                return None
        if name == "whatsapp":
            try:
                from .messaging.whatsapp import WhatsAppBot
                return WhatsAppBot(cfg, self.handle_user_command)
            except ImportError:
                logger.warning("twilio/aiohttp not installed — skip WhatsApp bot")
                return None
        if name == "discord":
            try:
                from .messaging.discord_bot import DiscordBot
                return DiscordBot(cfg, self.handle_user_command)
            except ImportError:
                logger.warning("discord.py not installed — skip Discord bot")
                return None
        return None

    # -- main entry ----------------------------------------------------------

    async def run(self) -> None:
        """Start the master: WebSocket server + bots + ping loop."""
        self._audit(f"Master starting on {self.host}:{self.port}")

        async with websockets.serve(self._ws_handler, self.host, self.port):
            self._audit("WebSocket server ready.")
            ping_task = asyncio.create_task(self._ping_loop())
            await self._start_bots()

            print(
                f"🧟 Zombie Master running on ws://{self.host}:{self.port}  "
                f"(password protected, HMAC-SHA256)"
            )
            print(f"   Audit log: {AUDIT_LOG}")
            if self._bots:
                print(f"   Messaging bots: {', '.join(b.name for b in self._bots)}")
            print("   Press Ctrl+C to stop.\n")

            try:
                await asyncio.Future()  # run forever
            except asyncio.CancelledError:
                pass
            finally:
                ping_task.cancel()
                for bot in self._bots:
                    try:
                        await bot.stop()
                    except Exception:
                        pass
                self._audit("Master stopped.")
