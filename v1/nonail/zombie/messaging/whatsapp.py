"""WhatsApp integration for Zombie Mode master (requires twilio + aiohttp)."""

from __future__ import annotations

from typing import Any

from .base import CommandCallback, MessagingBot


class WhatsAppBot(MessagingBot):
    name = "whatsapp"

    def __init__(self, config: dict[str, Any], on_command: CommandCallback):
        super().__init__(config, on_command)
        from twilio.rest import Client as TwilioClient

        self._account_sid = config["account_sid"]
        self._auth_token = config["auth_token"]
        self._from_number = config.get("from_number", "")
        self._webhook_port = config.get("webhook_port", 5005)
        self._allowed = [str(n) for n in (config.get("allowed_numbers") or [])]
        self._twilio = TwilioClient(self._account_sid, self._auth_token)
        self._runner = None

    async def start(self) -> None:
        from aiohttp import web

        app = web.Application()
        app.router.add_post("/webhook/whatsapp", self._handle_webhook)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._webhook_port)
        await site.start()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _handle_webhook(self, request: Any) -> Any:
        from aiohttp import web

        data = await request.post()
        sender = data.get("From", "")
        body = data.get("Body", "").strip()
        if not body:
            return web.Response(text="ok")

        # Security check
        sender_number = sender.replace("whatsapp:", "")
        if self._allowed and sender_number not in self._allowed:
            return web.Response(text="ok")

        reply = await self.on_command(sender, body)
        # Send reply via Twilio
        self._twilio.messages.create(
            from_=f"whatsapp:{self._from_number}" if not self._from_number.startswith("whatsapp:") else self._from_number,
            to=sender,
            body=reply[:1600],
        )
        return web.Response(text="ok")

    async def send(self, recipient: str, text: str) -> None:
        to = recipient if recipient.startswith("whatsapp:") else f"whatsapp:{recipient}"
        self._twilio.messages.create(
            from_=f"whatsapp:{self._from_number}" if not self._from_number.startswith("whatsapp:") else self._from_number,
            to=to,
            body=text[:1600],
        )
