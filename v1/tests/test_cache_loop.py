from __future__ import annotations

import sqlite3

from nonail.cache import CacheStore
from nonail.providers.base import Message


def test_loop_events_track_actor_separation(tmp_path):
    cache_path = tmp_path / "cache.db"
    cache = CacheStore(str(cache_path), max_entries=100, ttl_seconds=3600)

    run_id = cache.start_run(provider="openai", model="gpt-4o", cwd="/tmp")
    cache.add_event(
        run_id=run_id,
        iteration=0,
        actor="user",
        event_type="prompt",
        payload={"content": "install tree"},
    )
    cache.add_event(
        run_id=run_id,
        iteration=0,
        actor="assistant",
        event_type="decision",
        payload={"tool_calls": [{"name": "bash"}]},
    )
    cache.add_event(
        run_id=run_id,
        iteration=0,
        actor="tool",
        event_type="observation",
        payload={"content": "ok"},
    )
    cache.complete_run(run_id)
    cache.close()

    conn = sqlite3.connect(cache_path)
    rows = conn.execute(
        "SELECT actor, event_type FROM loop_events WHERE run_id = ? ORDER BY id",
        (run_id,),
    ).fetchall()
    conn.close()

    assert rows == [
        ("user", "prompt"),
        ("assistant", "decision"),
        ("tool", "observation"),
    ]


def test_llm_cache_hit_and_tool_cache_hit(tmp_path):
    cache = CacheStore(str(tmp_path / "cache.db"), max_entries=100, ttl_seconds=3600)

    msgs = [Message(role="system", content="s"), Message(role="user", content="u")]
    req_hash = cache.llm_hash(provider="openai", model="gpt-4o", messages=msgs)
    tool_calls = [{"id": "tc1", "type": "function", "function": {"name": "bash", "arguments": "{}"}}]

    cache.put_llm(
        request_hash=req_hash,
        provider="openai",
        model="gpt-4o",
        content="done",
        tool_calls=tool_calls,
    )
    llm_entry = cache.get_llm(req_hash)

    assert llm_entry is not None
    assert llm_entry[0] == "done"
    assert llm_entry[1] == tool_calls

    th = cache.tool_hash(tool_name="bash", args={"command": "echo ok"}, cwd="/tmp")
    cache.put_tool(
        tool_hash=th,
        tool_name="bash",
        args={"command": "echo ok"},
        cwd="/tmp",
        output="ok",
        error=None,
        is_error=False,
    )
    tool_entry = cache.get_tool(th)
    assert tool_entry is not None
    assert tool_entry.cache_hit is True
    assert tool_entry.output == "ok"
    assert tool_entry.is_error is False

    stats = cache.stats()
    assert stats["llm_hits"] == 1
    assert stats["tool_hits"] == 1

    cache.close()
