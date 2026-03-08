"""Persistent cache store for autonomous loop execution."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class ToolCacheEntry:
    output: str
    error: str | None
    is_error: bool
    cache_hit: bool = True


class CacheStore:
    """SQLite-backed cache for loop events, LLM decisions, and tool outputs."""

    def __init__(
        self,
        path: str,
        *,
        max_entries: int = 5000,
        ttl_seconds: int = 86400,
    ) -> None:
        self.path = str(Path(path).expanduser())
        self.max_entries = max(100, max_entries)
        self.ttl_seconds = max(60, ttl_seconds)

        db_path = Path(self.path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._init_schema()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _stable_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def _init_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS loop_runs (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                cwd TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS loop_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                iteration INTEGER NOT NULL,
                actor TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES loop_runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_loop_events_run_iter
                ON loop_events(run_id, iteration, id);

            CREATE TABLE IF NOT EXISTS llm_cache (
                request_hash TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                response_content TEXT,
                response_tool_calls_json TEXT,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_llm_cache_last_used
                ON llm_cache(last_used_at);

            CREATE TABLE IF NOT EXISTS tool_cache (
                tool_hash TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                cwd TEXT NOT NULL,
                output TEXT,
                error TEXT,
                is_error INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_tool_cache_last_used
                ON tool_cache(last_used_at);
            """
        )
        self._db.commit()

    def start_run(self, *, provider: str, model: str, cwd: str) -> str:
        run_id = f"run_{uuid.uuid4().hex}"
        now = self._now_iso()
        self._db.execute(
            """
            INSERT INTO loop_runs(id, provider, model, cwd, status, started_at)
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (run_id, provider, model, cwd, now),
        )
        self._db.commit()
        return run_id

    def complete_run(self, run_id: str, *, status: str = "completed") -> None:
        self._db.execute(
            "UPDATE loop_runs SET status = ?, completed_at = ? WHERE id = ?",
            (status, self._now_iso(), run_id),
        )
        self._db.commit()

    def add_event(
        self,
        *,
        run_id: str,
        iteration: int,
        actor: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self._db.execute(
            """
            INSERT INTO loop_events(run_id, iteration, actor, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, iteration, actor, event_type, self._stable_json(payload), self._now_iso()),
        )
        self._db.commit()

    def llm_hash(self, *, provider: str, model: str, messages: list[Any]) -> str:
        normalised: list[dict[str, Any]] = []
        for m in messages:
            normalised.append(
                {
                    "role": getattr(m, "role", None),
                    "content": getattr(m, "content", None),
                    "name": getattr(m, "name", None),
                    "tool_call_id": getattr(m, "tool_call_id", None),
                    "tool_calls": getattr(m, "tool_calls", None),
                }
            )
        payload = {"provider": provider, "model": model, "messages": normalised}
        return hashlib.sha256(self._stable_json(payload).encode("utf-8")).hexdigest()

    def tool_hash(self, *, tool_name: str, args: dict[str, Any], cwd: str) -> str:
        env_signature = {
            "user": os.environ.get("USER", ""),
            "shell": os.environ.get("SHELL", ""),
            "hostname": os.environ.get("HOSTNAME", ""),
        }
        payload = {
            "tool": tool_name,
            "args": args,
            "cwd": cwd,
            "env_signature": env_signature,
        }
        return hashlib.sha256(self._stable_json(payload).encode("utf-8")).hexdigest()

    def get_llm(self, request_hash: str) -> tuple[str | None, list[dict] | None] | None:
        row = self._db.execute(
            "SELECT response_content, response_tool_calls_json FROM llm_cache WHERE request_hash = ?",
            (request_hash,),
        ).fetchone()
        if row is None:
            return None

        self._db.execute(
            "UPDATE llm_cache SET hit_count = hit_count + 1, last_used_at = ? WHERE request_hash = ?",
            (self._now_iso(), request_hash),
        )
        self._db.commit()

        tool_calls = json.loads(row["response_tool_calls_json"]) if row["response_tool_calls_json"] else None
        return row["response_content"], tool_calls

    def put_llm(
        self,
        *,
        request_hash: str,
        provider: str,
        model: str,
        content: str | None,
        tool_calls: list[dict] | None,
    ) -> None:
        now = self._now_iso()
        self._db.execute(
            """
            INSERT INTO llm_cache(
                request_hash, provider, model, response_content, response_tool_calls_json,
                created_at, last_used_at, hit_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(request_hash) DO UPDATE SET
                response_content=excluded.response_content,
                response_tool_calls_json=excluded.response_tool_calls_json,
                last_used_at=excluded.last_used_at
            """,
            (
                request_hash,
                provider,
                model,
                content,
                self._stable_json(tool_calls) if tool_calls is not None else None,
                now,
                now,
            ),
        )
        self._db.commit()
        self._prune()

    def get_tool(self, tool_hash: str) -> ToolCacheEntry | None:
        row = self._db.execute(
            "SELECT output, error, is_error FROM tool_cache WHERE tool_hash = ?",
            (tool_hash,),
        ).fetchone()
        if row is None:
            return None

        self._db.execute(
            "UPDATE tool_cache SET hit_count = hit_count + 1, last_used_at = ? WHERE tool_hash = ?",
            (self._now_iso(), tool_hash),
        )
        self._db.commit()

        return ToolCacheEntry(
            output=row["output"] or "",
            error=row["error"],
            is_error=bool(row["is_error"]),
            cache_hit=True,
        )

    def put_tool(
        self,
        *,
        tool_hash: str,
        tool_name: str,
        args: dict[str, Any],
        cwd: str,
        output: str,
        error: str | None,
        is_error: bool,
    ) -> None:
        now = self._now_iso()
        self._db.execute(
            """
            INSERT INTO tool_cache(
                tool_hash, tool_name, args_json, cwd, output, error, is_error,
                created_at, last_used_at, hit_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(tool_hash) DO UPDATE SET
                output=excluded.output,
                error=excluded.error,
                is_error=excluded.is_error,
                last_used_at=excluded.last_used_at
            """,
            (
                tool_hash,
                tool_name,
                self._stable_json(args),
                cwd,
                output,
                error,
                1 if is_error else 0,
                now,
                now,
            ),
        )
        self._db.commit()
        self._prune()

    def stats(self) -> dict[str, Any]:
        llm_entries = self._db.execute("SELECT COUNT(*) AS c FROM llm_cache").fetchone()["c"]
        tool_entries = self._db.execute("SELECT COUNT(*) AS c FROM tool_cache").fetchone()["c"]
        run_entries = self._db.execute("SELECT COUNT(*) AS c FROM loop_runs").fetchone()["c"]
        event_entries = self._db.execute("SELECT COUNT(*) AS c FROM loop_events").fetchone()["c"]
        llm_hits = self._db.execute("SELECT COALESCE(SUM(hit_count), 0) AS h FROM llm_cache").fetchone()["h"]
        tool_hits = self._db.execute("SELECT COALESCE(SUM(hit_count), 0) AS h FROM tool_cache").fetchone()["h"]
        return {
            "path": self.path,
            "llm_entries": int(llm_entries),
            "tool_entries": int(tool_entries),
            "runs": int(run_entries),
            "events": int(event_entries),
            "llm_hits": int(llm_hits),
            "tool_hits": int(tool_hits),
        }

    def clear(self) -> None:
        self._db.execute("DELETE FROM llm_cache")
        self._db.execute("DELETE FROM tool_cache")
        self._db.commit()

    def set_limits(
        self,
        *,
        max_entries: int | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        if max_entries is not None:
            self.max_entries = max(100, int(max_entries))
        if ttl_seconds is not None:
            self.ttl_seconds = max(60, int(ttl_seconds))
        self._prune()

    def _prune(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=self.ttl_seconds)).isoformat()
        self._db.execute("DELETE FROM llm_cache WHERE last_used_at < ?", (cutoff,))
        self._db.execute("DELETE FROM tool_cache WHERE last_used_at < ?", (cutoff,))

        self._db.execute(
            """
            DELETE FROM llm_cache
            WHERE request_hash IN (
                SELECT request_hash FROM llm_cache
                ORDER BY last_used_at DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self.max_entries,),
        )
        self._db.execute(
            """
            DELETE FROM tool_cache
            WHERE tool_hash IN (
                SELECT tool_hash FROM tool_cache
                ORDER BY last_used_at DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (self.max_entries,),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
