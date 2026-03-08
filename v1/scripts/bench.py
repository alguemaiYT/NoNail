#!/usr/bin/env python3
"""Benchmark NoNail startup footprint (RSS, peak memory, time).

Usage:
    python scripts/bench.py            # Run all benchmarks
    python scripts/bench.py --mode chat # Run only 'chat' import benchmark
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
import time


def _measure_import(snippet: str, label: str) -> dict:
    """Spawn a subprocess that runs *snippet* and report RSS + wall time."""
    code = textwrap.dedent(f"""\
        import resource, time, os, json
        t0 = time.perf_counter()
        {snippet}
        t1 = time.perf_counter()
        ru = resource.getrusage(resource.RUSAGE_SELF)
        # maxrss is in KB on Linux
        print(json.dumps({{
            "label": {label!r},
            "wall_s": round(t1 - t0, 4),
            "maxrss_kb": ru.ru_maxrss,
        }}))
    """)

    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "NONAIL_ZOMBIE": "0"},
    )
    if proc.returncode != 0:
        return {"label": label, "wall_s": -1, "maxrss_kb": -1, "error": proc.stderr.strip()}

    import json
    return json.loads(proc.stdout.strip())


BENCHMARKS: dict[str, tuple[str, str]] = {
    "baseline": (
        "pass",
        "Python baseline (no imports)",
    ),
    "chat": (
        "from nonail.agent import Agent",
        "Import Agent (chat mode)",
    ),
    "config": (
        "from nonail.config import Config; Config.load()",
        "Load config",
    ),
    "providers": (
        "from nonail.providers import create_provider",
        "Import provider registry",
    ),
    "mcp-server": (
        "from nonail.mcp_server import run_mcp_server",
        "Import MCP server",
    ),
    "mcp-client": (
        "from nonail.mcp_client import MCPClientManager",
        "Import MCP client",
    ),
    "tools": (
        "from nonail.tools import ALL_TOOLS",
        "Import all tools",
    ),
    "cache": (
        "from nonail.cache import CacheStore; CacheStore('/tmp/nonail-bench-cache.db')",
        "Init CacheStore",
    ),
}


def run_benchmarks(modes: list[str] | None = None) -> list[dict]:
    """Run selected (or all) benchmarks and return results."""
    results: list[dict] = []
    targets = {k: v for k, v in BENCHMARKS.items() if not modes or k in modes}

    for key, (snippet, label) in targets.items():
        result = _measure_import(snippet, label)
        results.append(result)
    return results


def print_results(results: list[dict]) -> None:
    """Print results as a simple text table."""
    hdr_label = "Benchmark"
    hdr_time = "Wall (s)"
    hdr_mem = "Peak RSS (KB)"
    w_label = max(len(hdr_label), *(len(r["label"]) for r in results))
    w_time = max(len(hdr_time), 10)
    w_mem = max(len(hdr_mem), 12)

    sep = f"+-{'-' * w_label}-+-{'-' * w_time}-+-{'-' * w_mem}-+"
    row_fmt = f"| {{:<{w_label}}} | {{:>{w_time}}} | {{:>{w_mem}}} |"

    print()
    print(sep)
    print(row_fmt.format(hdr_label, hdr_time, hdr_mem))
    print(sep)

    baseline_rss = None
    for r in results:
        if r.get("error"):
            print(row_fmt.format(r["label"], "ERROR", r.get("error", "")[:w_mem]))
            continue
        rss = r["maxrss_kb"]
        if baseline_rss is None:
            baseline_rss = rss
        delta = f"(+{rss - baseline_rss})" if baseline_rss and rss != baseline_rss else ""
        print(row_fmt.format(r["label"], f"{r['wall_s']:.4f}", f"{rss} {delta}"))
    print(sep)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark NoNail startup footprint")
    parser.add_argument(
        "--mode",
        choices=list(BENCHMARKS.keys()),
        nargs="*",
        default=None,
        help="Run specific benchmarks (default: all)",
    )
    args = parser.parse_args()
    results = run_benchmarks(args.mode)
    print_results(results)


if __name__ == "__main__":
    main()
