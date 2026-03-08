#!/usr/bin/env python3
"""
Zombie Organizer — testa o modo zombie do NoNail localmente.

Fluxo:
  1. Este script age como o "Zombie Master" (servidor TCP)
  2. Inicia o zombie slave (v2/build/nonail zombie slave) como subprocesso
  3. Slave conecta, autentica via HMAC-SHA256, aguarda comandos
  4. Usa Groq AI para analisar /home/kali e gerar plano de organização
  5. Executa os comandos de organização via zombie slave
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Zombie Master (Python implementation of the C++ ZombieMaster protocol)
# ---------------------------------------------------------------------------

PASSWORD = "testpass123"
MASTER_PORT = 8765
END_MARKER = "\n---END---\n"


def generate_token(password: str) -> str:
    """Generate HMAC-SHA256 auth token matching the C++ slave implementation."""
    ts = str(int(time.time()))
    h = hmac.new(password.encode(), ts.encode(), hashlib.sha256).hexdigest()
    return f"{ts}:{h}"


def verify_token(password: str, token: str) -> bool:
    ts_str, provided = token.split(":", 1)
    ts = int(ts_str)
    if abs(int(time.time()) - ts) > 60:
        return False
    expected = hmac.new(password.encode(), ts_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


class ZombieMasterPy:
    """Python zombie master that accepts one slave connection."""

    def __init__(self, port: int, password: str):
        self.port = port
        self.password = password
        self.slave_fd: socket.socket | None = None
        self.slave_id: str = ""
        self._buf: bytes = b""

    def start_server(self) -> socket.socket:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self.port))
        srv.listen(1)
        print(f"🧟 Zombie Master listening on port {self.port}")
        return srv

    def accept_slave(self, srv: socket.socket, timeout: float = 10.0) -> bool:
        srv.settimeout(timeout)
        try:
            conn, addr = srv.accept()
        except TimeoutError:
            print("❌ Timeout waiting for slave")
            return False

        conn.settimeout(10.0)
        print(f"🔌 Slave connecting from {addr[0]}")

        # 1. Read auth token from slave
        raw = self._recv_line(conn)
        if not raw or not verify_token(self.password, raw):
            print("❌ Auth failed")
            conn.send(b"AUTH_FAIL\n")
            conn.close()
            return False

        # 2. Send AUTH_OK
        conn.send(b"AUTH_OK\n")

        # 3. Read slave ID
        slave_id = self._recv_line(conn)
        self.slave_id = slave_id or "unknown"
        self.slave_fd = conn
        print(f"✅ Slave authenticated: '{self.slave_id}'")
        return True

    def send_command(self, command: str) -> str:
        """Send command to slave, wait for ---END--- marker."""
        if not self.slave_fd:
            return "No slave connected"
        try:
            self.slave_fd.send((command + "\n").encode())
            return self._recv_until(self.slave_fd, END_MARKER)
        except Exception as e:
            return f"Error: {e}"

    def _recv_line(self, conn: socket.socket) -> str:
        buf = b""
        while True:
            c = conn.recv(1)
            if not c or c == b"\n":
                break
            if c != b"\r":
                buf += c
        return buf.decode(errors="replace").strip()

    def _recv_until(self, conn: socket.socket, marker: str) -> str:
        buf = ""
        m = marker
        while True:
            try:
                chunk = conn.recv(4096).decode(errors="replace")
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            if m in buf:
                idx = buf.find(m)
                return buf[:idx].strip()
        return buf.strip()

    def close(self) -> None:
        if self.slave_fd:
            self.slave_fd.close()
            self.slave_fd = None


# ---------------------------------------------------------------------------
# AI Planner using Groq
# ---------------------------------------------------------------------------

def get_home_tree() -> str:
    """Get a summary of /home/kali structure for AI analysis."""
    lines = []

    # Loose files at root
    lines.append("=== Loose files at /home/kali ===")
    for p in sorted(Path("/home/kali").iterdir()):
        if p.name.startswith(".") or p.name in ("NoNail",):
            continue
        if p.is_file():
            lines.append(f"  FILE: {p.name}")

    # Top-level directories
    lines.append("\n=== Directories at /home/kali ===")
    for p in sorted(Path("/home/kali").iterdir()):
        if p.name.startswith(".") or not p.is_dir():
            continue
        # Skip large dirs
        if p.name in ("node_modules", "__pycache__", "snap", "Qt", "qtcreator-18.0.2"):
            lines.append(f"  DIR: {p.name}  [skipped - large/system]")
            continue
        children = [c.name for c in p.iterdir() if not c.name.startswith(".")][:8]
        lines.append(f"  DIR: {p.name}  [{', '.join(children[:5])}{'...' if len(children)>5 else ''}]")

    return "\n".join(lines)


async def plan_organization_with_ai(tree: str, api_key: str) -> list[dict]:
    """Use Groq/LLaMA to generate a file organization plan."""
    import sys
    sys.path.insert(0, "/home/kali/NoNail")
    from nonail.providers.groq_provider import GroqProvider
    from nonail.providers.base import Message

    prompt = f"""You are organizing the /home/kali directory. Here is the current structure:

{tree}

Rules:
- Group loose files into project folders or standard categories
- Use EXISTING directories when a file clearly belongs there (e.g. cone images → Coneslayer)
- Create new directories only when needed: Screenshots/, Audio/, Archives/, Misc/
- Do NOT move: NoNail/, Documents/, Downloads/ (keep as-is)
- Do NOT touch dotfiles or system dirs
- Output ONLY a JSON array of move operations, no explanations

JSON format:
[
  {{"from": "/home/kali/filename.ext", "to": "/home/kali/TargetDir/filename.ext", "reason": "why"}},
  ...
]

Only include files that should actually move. Be conservative — if unsure, skip."""

    provider = GroqProvider(api_key=api_key, model="llama-3.3-70b-versatile")
    resp = await provider.chat([Message(role="user", content=prompt)])

    # Extract JSON from response
    content = resp.content or ""
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if not match:
        print(f"⚠️  AI response didn't contain JSON:\n{content[:500]}")
        return []

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}\n{match.group(0)[:300]}")
        return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def start_slave_subprocess(password: str, port: int) -> subprocess.Popen:
    """Start the v2 zombie slave connecting to our local master."""
    slave_bin = Path("/home/kali/NoNail/v2/build/nonail")
    if not slave_bin.exists():
        raise FileNotFoundError(f"Slave binary not found: {slave_bin}")

    cmd = [
        str(slave_bin), "zombie", "slave",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--password", password,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(f"🚀 Started slave subprocess (PID {proc.pid})")
    return proc


def check_slave_args() -> None:
    """Verify the slave CLI accepts --master --password --id args."""
    result = subprocess.run(
        ["/home/kali/NoNail/v2/build/nonail", "zombie", "--help"],
        capture_output=True, text=True, timeout=3
    )
    output = result.stdout + result.stderr
    if "--master" not in output and "--password" not in output:
        # Check if slave takes positional args
        pass  # Will handle below


async def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("❌ GROQ_API_KEY not set")
        sys.exit(1)

    print("=" * 60)
    print("  NoNail Zombie Mode — Home Directory Organizer")
    print("=" * 60)
    print()

    # 1. Start master server
    master = ZombieMasterPy(MASTER_PORT, PASSWORD)
    srv = master.start_server()

    # 2. Start slave subprocess
    print("🚀 Starting zombie slave...")
    slave_proc = start_slave_subprocess(PASSWORD, MASTER_PORT)

    # Give it 1s to connect
    time.sleep(1)

    # 3. Accept slave connection
    if not master.accept_slave(srv, timeout=8.0):
        slave_proc.terminate()
        print("❌ Failed to connect slave")
        sys.exit(1)

    srv.close()

    # 4. Verify slave can execute commands
    print("\n🔬 Testing zombie command execution...")
    result = master.send_command("echo 'ZOMBIE_TEST_OK'")
    if "ZOMBIE_TEST_OK" not in result:
        print(f"⚠️  Unexpected response: {result!r}")
    else:
        print(f"✅ Command execution works: {result!r}")

    result = master.send_command("whoami")
    print(f"✅ Running as: {result.strip()}")

    result = master.send_command("uname -m")
    print(f"✅ Architecture: {result.strip()}")

    print()

    # 5. Scan /home/kali via zombie
    print("📂 Scanning /home/kali via zombie slave...")
    tree_output = master.send_command(
        "find /home/kali -maxdepth 1 -not -name '.*' -not -name 'kali' "
        r"-type f | sort | head -50"
    )
    print(f"Found files:\n{tree_output[:400]}...")
    print()

    # 6. Use AI to plan organization
    print("🤖 Consulting Groq AI for organization plan...")
    tree = get_home_tree()
    moves = await plan_organization_with_ai(tree, api_key)

    if not moves:
        print("ℹ️  AI has no moves to suggest — home may already be organized!")
        master.close()
        slave_proc.terminate()
        return

    print(f"\n📋 Organization plan ({len(moves)} moves):")
    print("-" * 60)
    for m in moves:
        src = Path(m.get("from", "?")).name
        dst = m.get("to", "?")
        reason = m.get("reason", "")
        print(f"  {src} → {dst}")
        if reason:
            print(f"    └─ {reason}")
    print("-" * 60)

    # 7. Execute moves via zombie
    print(f"\n⚡ Executing {len(moves)} moves via zombie slave...\n")
    ok = 0
    fail = 0
    for move in moves:
        src = move.get("from", "")
        dst = move.get("to", "")
        if not src or not dst:
            continue

        # Create destination dir if needed
        dst_dir = str(Path(dst).parent)
        master.send_command(f"mkdir -p '{dst_dir}'")

        # Execute move
        cmd = f"mv '{src}' '{dst}'"
        result = master.send_command(cmd)

        if "exit code" in result or "No such file" in result or "cannot" in result:
            print(f"  ❌ {Path(src).name} → FAILED: {result[:60]}")
            fail += 1
        else:
            print(f"  ✅ {Path(src).name} → {dst_dir}/")
            ok += 1

    print(f"\n{'=' * 60}")
    print(f"  Done! {ok} moved, {fail} failed")
    print(f"{'=' * 60}\n")

    # 8. Show final structure via zombie
    print("📂 Final /home/kali structure:")
    final = master.send_command("ls -la /home/kali/ | grep -v '^total' | head -40")
    print(final)

    master.close()
    slave_proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
