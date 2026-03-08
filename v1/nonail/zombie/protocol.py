"""Zombie Mode protocol — message types, HMAC auth, serialisation."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------


class MsgType(str, Enum):
    HELLO = "HELLO"
    PING = "PING"
    PONG = "PONG"
    EXEC = "EXEC"
    RESULT = "RESULT"
    STATUS = "STATUS"
    ERROR = "ERROR"
    BROADCAST = "BROADCAST"


@dataclass
class ZombieMessage:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    hmac_sig: str = ""

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ZombieMessage:
        return cls(
            type=d["type"],
            payload=d.get("payload", {}),
            id=d.get("id", uuid.uuid4().hex[:12]),
            timestamp=d.get("timestamp", time.time()),
            hmac_sig=d.get("hmac_sig", ""),
        )

    @classmethod
    def from_json(cls, raw: str) -> ZombieMessage:
        return cls.from_dict(json.loads(raw))

    # -- HMAC ----------------------------------------------------------------

    def _signing_blob(self) -> bytes:
        """Deterministic blob for HMAC: type + id + timestamp + payload JSON."""
        msg_type = self.type.value if isinstance(self.type, MsgType) else self.type
        payload_str = json.dumps(self.payload, sort_keys=True)
        blob = f"{msg_type}|{self.id}|{self.timestamp}|{payload_str}"
        return blob.encode()

    def sign(self, password: str) -> None:
        """Compute and attach HMAC-SHA256 signature."""
        self.hmac_sig = hmac.new(
            password.encode(), self._signing_blob(), hashlib.sha256
        ).hexdigest()

    def verify(self, password: str, max_age: float = 30.0) -> bool:
        """Verify HMAC and reject replays older than *max_age* seconds."""
        if abs(time.time() - self.timestamp) > max_age:
            return False
        expected = hmac.new(
            password.encode(), self._signing_blob(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(self.hmac_sig, expected)


# ---------------------------------------------------------------------------
# Convenience builders
# ---------------------------------------------------------------------------


def make_hello(slave_id: str, info: dict[str, Any], password: str) -> str:
    msg = ZombieMessage(
        type=MsgType.HELLO,
        payload={"slave_id": slave_id, **info},
    )
    msg.sign(password)
    return msg.to_json()


def make_exec(tool: str, args: dict[str, Any], password: str, target: str = "") -> str:
    msg = ZombieMessage(
        type=MsgType.EXEC,
        payload={"tool": tool, "args": args, "target": target},
    )
    msg.sign(password)
    return msg.to_json()


def make_result(
    exec_id: str, output: str, is_error: bool, password: str
) -> str:
    msg = ZombieMessage(
        type=MsgType.RESULT,
        payload={"exec_id": exec_id, "output": output, "is_error": is_error},
    )
    msg.sign(password)
    return msg.to_json()


def make_ping(password: str) -> str:
    msg = ZombieMessage(type=MsgType.PING)
    msg.sign(password)
    return msg.to_json()


def make_pong(password: str) -> str:
    msg = ZombieMessage(type=MsgType.PONG)
    msg.sign(password)
    return msg.to_json()


def make_error(detail: str, password: str) -> str:
    msg = ZombieMessage(type=MsgType.ERROR, payload={"detail": detail})
    msg.sign(password)
    return msg.to_json()
