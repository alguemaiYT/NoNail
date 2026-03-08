# NoNail — OpenWrt Packaging Strategies

This document compares packaging strategies for deploying NoNail on OpenWrt
devices with constrained flash (≤ 32 MB) and RAM (≤ 64 MB).

---

## 1. Pure Python (pip install)

Install NoNail and its dependencies directly via `pip` on the device.

**Pros:**
- Simplest approach — no build toolchain needed
- Easy to update (`pip install --upgrade`)
- Works on any architecture with Python 3.10+

**Cons:**
- Largest flash footprint (~14 MB minimal, ~20 MB full)
- Requires Python runtime on device (~15 MB)
- Slow cold-start on weak CPUs (2–5 s on MIPS)

**Commands:**
```bash
opkg install python3 python3-pip
pip3 install nonail
# Or minimal:
pip3 install nonail --no-deps
pip3 install click pyyaml openai
```

**Estimated footprint:**

| Metric | Value |
|--------|-------|
| Flash | ~30 MB (Python + deps + nonail) |
| RAM peak | ~25–40 MB |
| Cold start | 2–5 s |
| Build complexity | None |

---

## 2. Nuitka (compiled binary)

Compile NoNail to a standalone binary using Nuitka.

**Pros:**
- Single binary, no Python runtime needed on device
- ~20–30% faster startup
- Smaller than Python + deps

**Cons:**
- Requires cross-compilation toolchain for target arch (MIPS, ARM)
- C compilation is slow (~5–15 min)
- Binary size still ~15–25 MB (includes libpython)
- C extensions (pydantic-core) may cause issues

**Commands:**
```bash
pip install nuitka
python -m nuitka --standalone --onefile \
    --include-package=nonail \
    --include-package=click \
    --include-package=yaml \
    --include-package=openai \
    --output-filename=nonail-bin \
    nonail/__main__.py
```

**Cross-compilation for OpenWrt:**
```bash
# Requires OpenWrt SDK with Python headers
export CC=mips-openwrt-linux-gcc
python -m nuitka --standalone --onefile \
    --cross-compilation \
    nonail/__main__.py
```

**Estimated footprint:**

| Metric | Value |
|--------|-------|
| Flash | ~15–25 MB |
| RAM peak | ~20–35 MB |
| Cold start | 1–3 s |
| Build complexity | Medium-High |

---

## 3. PyOxidizer (bundled Python)

Bundle Python interpreter + NoNail into a single distributable.

**Pros:**
- Self-contained — no system Python needed
- Can strip unused stdlib modules
- Reproducible builds

**Cons:**
- Complex configuration (`pyoxidizer.bzl`)
- Cross-compilation support is limited
- Binary size ~20–30 MB
- Less mature than Nuitka for embedded targets

**Commands:**
```bash
pip install pyoxidizer
pyoxidizer init-config-file nonail-oxide
# Edit pyoxidizer.bzl to configure
pyoxidizer build --release
```

**Example `pyoxidizer.bzl` snippet:**
```python
def make_exe():
    dist = default_python_distribution()
    policy = dist.make_python_packaging_policy()
    policy.resources_location = "in-memory"
    
    exe = dist.to_python_executable(
        name="nonail",
        packaging_policy=policy,
    )
    exe.add_python_resources(exe.pip_install(["."]))
    return exe
```

**Estimated footprint:**

| Metric | Value |
|--------|-------|
| Flash | ~20–30 MB |
| RAM peak | ~20–35 MB |
| Cold start | 1–2 s |
| Build complexity | High |

---

## 4. Partial rewrite (Go / Rust / C)

Rewrite performance-critical or memory-heavy components in a compiled language.

**When to consider:** Only if profiling shows > 50% of memory/startup is spent
in Python overhead rather than actual LLM API calls.

**Candidates for rewrite:**
- CLI entry point + config loading (replace Click with a compiled CLI)
- Tool execution engine (subprocess management)
- WebSocket handling (zombie mode)

**Pros:**
- Smallest possible footprint (~2–5 MB binary)
- Near-instant startup
- No Python runtime dependency

**Cons:**
- Major engineering effort
- Loses Python ecosystem (openai SDK, mcp SDK, etc.)
- Must re-implement or FFI-call all provider APIs

**Recommendation:** Not justified unless the Python runtime itself is the
bottleneck. Current lazy-import optimizations already minimize what gets loaded.

---

## Comparison table

| Strategy | Flash | RAM peak | Cold start | Build complexity | Maintenance |
|----------|-------|----------|------------|-----------------|-------------|
| Pure Python | ~30 MB | ~25-40 MB | 2–5 s | None | Easy |
| Nuitka | ~15–25 MB | ~20-35 MB | 1–3 s | Medium-High | Medium |
| PyOxidizer | ~20–30 MB | ~20-35 MB | 1–2 s | High | Medium |
| Partial rewrite | ~2–5 MB | ~5-15 MB | <0.5 s | Very High | Hard |

---

## Recommendation

For OpenWrt ≤ 64 MB RAM:

1. **Start with Pure Python** + the lazy-import optimizations already
   implemented (providers, MCP, zombie loaded on demand; rich removed).

2. **If flash is tight**, consider Nuitka for a single-binary deployment that
   eliminates the need for a full Python installation.

3. **Partial rewrite** should only be considered if measurements show Python
   overhead is the dominant cost (unlikely — most time/memory goes to LLM API
   calls and their SDK dependencies).

Run `scripts/bench.py` to get actual measurements on your target hardware.
