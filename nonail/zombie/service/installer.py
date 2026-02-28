"""Zombie Mode — systemd / launchd service installer."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Templates (inline to avoid jinja2 hard dependency)
# ---------------------------------------------------------------------------

_SYSTEMD_TEMPLATE = """\
[Unit]
Description=NoNail Zombie {role}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
WorkingDirectory={home}
ExecStart={exec_start}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment="PATH={path}"
{env_lines}

[Install]
WantedBy=multi-user.target
"""

_LAUNCHD_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nonail.zombie.{role_lower}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/zombie-{role_lower}.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/zombie-{role_lower}.stderr.log</string>
</dict>
</plist>
"""


def _find_nonail_bin() -> str:
    """Find the nonail binary path."""
    which = shutil.which("nonail")
    if which:
        return which
    # Fallback: try the venv
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        candidate = Path(venv) / "bin" / "nonail"
        if candidate.exists():
            return str(candidate)
    return sys.executable + " -m nonail"


# ---------------------------------------------------------------------------
# Systemd (Linux)
# ---------------------------------------------------------------------------


def systemd_install(
    role: str,
    extra_args: str = "",
    env_vars: dict[str, str] | None = None,
) -> str:
    """Generate and install a systemd unit file.  Returns status message."""
    user = os.environ.get("USER", "root")
    home = str(Path.home())
    nonail = _find_nonail_bin()
    exec_start = f"{nonail} zombie {role} start {extra_args}".strip()

    env_lines = ""
    if env_vars:
        env_lines = "\n".join(
            f'Environment="{k}={v}"' for k, v in env_vars.items()
        )

    unit = _SYSTEMD_TEMPLATE.format(
        role=role.capitalize(),
        user=user,
        home=home,
        exec_start=exec_start,
        path=os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
        env_lines=env_lines,
    )

    service_name = f"nonail-zombie-{role}.service"
    service_path = Path(f"/etc/systemd/system/{service_name}")

    try:
        service_path.write_text(unit)
    except PermissionError:
        # Try with sudo
        import tempfile
        tmp = Path(tempfile.mktemp(suffix=".service"))
        tmp.write_text(unit)
        subprocess.run(["sudo", "cp", str(tmp), str(service_path)], check=True)
        tmp.unlink()

    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
    subprocess.run(["sudo", "systemctl", "enable", "--now", service_name], check=True)

    return f"✅ Installed and started: {service_name}\n   Config: {service_path}"


def systemd_uninstall(role: str) -> str:
    service_name = f"nonail-zombie-{role}.service"
    service_path = Path(f"/etc/systemd/system/{service_name}")
    subprocess.run(["sudo", "systemctl", "disable", "--now", service_name], check=False)
    if service_path.exists():
        subprocess.run(["sudo", "rm", str(service_path)], check=True)
    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
    return f"✅ Uninstalled: {service_name}"


def systemd_status(role: str) -> str:
    service_name = f"nonail-zombie-{role}.service"
    result = subprocess.run(
        ["systemctl", "status", service_name],
        capture_output=True, text=True,
    )
    return result.stdout or result.stderr


# ---------------------------------------------------------------------------
# launchd (macOS)
# ---------------------------------------------------------------------------


def launchd_install(
    role: str,
    extra_args: str = "",
) -> str:
    nonail = _find_nonail_bin()
    parts = nonail.split() + ["zombie", role, "start"] + extra_args.split()
    args_xml = "\n".join(f"        <string>{p}</string>" for p in parts if p)

    log_dir = Path.home() / ".nonail" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    plist = _LAUNCHD_TEMPLATE.format(
        role_lower=role.lower(),
        args_xml=args_xml,
        log_dir=str(log_dir),
    )

    plist_name = f"com.nonail.zombie.{role.lower()}.plist"
    plist_path = Path.home() / "Library" / "LaunchAgents" / plist_name
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist)

    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return f"✅ Installed and loaded: {plist_path}"


def launchd_uninstall(role: str) -> str:
    plist_name = f"com.nonail.zombie.{role.lower()}.plist"
    plist_path = Path.home() / "Library" / "LaunchAgents" / plist_name
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    if plist_path.exists():
        plist_path.unlink()
    return f"✅ Uninstalled: {plist_path}"


def launchd_status(role: str) -> str:
    label = f"com.nonail.zombie.{role.lower()}"
    result = subprocess.run(
        ["launchctl", "list", label],
        capture_output=True, text=True,
    )
    return result.stdout or result.stderr or f"Service '{label}' not found."


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def install_service(role: str, extra_args: str = "", env_vars: dict | None = None) -> str:
    if platform.system() == "Linux":
        return systemd_install(role, extra_args, env_vars)
    if platform.system() == "Darwin":
        return launchd_install(role, extra_args)
    return "⚠ Service installation only supported on Linux (systemd) and macOS (launchd)."


def uninstall_service(role: str) -> str:
    if platform.system() == "Linux":
        return systemd_uninstall(role)
    if platform.system() == "Darwin":
        return launchd_uninstall(role)
    return "⚠ Not supported on this platform."


def service_status(role: str) -> str:
    if platform.system() == "Linux":
        return systemd_status(role)
    if platform.system() == "Darwin":
        return launchd_status(role)
    return "⚠ Not supported on this platform."
