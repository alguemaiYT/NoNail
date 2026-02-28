"""Package manager tool — auto-detects and wraps system package manager."""

from __future__ import annotations

import asyncio
import platform
import shutil
from typing import Any

from .base import Tool, ToolResult


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

_PM_COMMANDS: dict[str, dict[str, str]] = {
    "apt": {
        "search": "apt-cache search {pkg}",
        "install": "sudo apt install -y {pkg}",
        "remove": "sudo apt remove -y {pkg}",
        "update": "sudo apt update",
        "list_installed": "dpkg --get-selections | grep -v deinstall",
        "info": "apt-cache show {pkg}",
    },
    "dnf": {
        "search": "dnf search {pkg}",
        "install": "sudo dnf install -y {pkg}",
        "remove": "sudo dnf remove -y {pkg}",
        "update": "sudo dnf check-update",
        "list_installed": "dnf list installed",
        "info": "dnf info {pkg}",
    },
    "yum": {
        "search": "yum search {pkg}",
        "install": "sudo yum install -y {pkg}",
        "remove": "sudo yum remove -y {pkg}",
        "update": "sudo yum check-update",
        "list_installed": "yum list installed",
        "info": "yum info {pkg}",
    },
    "pacman": {
        "search": "pacman -Ss {pkg}",
        "install": "sudo pacman -S --noconfirm {pkg}",
        "remove": "sudo pacman -R --noconfirm {pkg}",
        "update": "sudo pacman -Sy",
        "list_installed": "pacman -Q",
        "info": "pacman -Si {pkg}",
    },
    "zypper": {
        "search": "zypper search {pkg}",
        "install": "sudo zypper install -y {pkg}",
        "remove": "sudo zypper remove -y {pkg}",
        "update": "sudo zypper refresh",
        "list_installed": "zypper packages --installed-only",
        "info": "zypper info {pkg}",
    },
    "apk": {
        "search": "apk search {pkg}",
        "install": "sudo apk add {pkg}",
        "remove": "sudo apk del {pkg}",
        "update": "sudo apk update",
        "list_installed": "apk list --installed",
        "info": "apk info {pkg}",
    },
    "brew": {
        "search": "brew search {pkg}",
        "install": "brew install {pkg}",
        "remove": "brew uninstall {pkg}",
        "update": "brew update",
        "list_installed": "brew list",
        "info": "brew info {pkg}",
    },
    "pkg": {
        "search": "pkg search {pkg}",
        "install": "sudo pkg install -y {pkg}",
        "remove": "sudo pkg remove -y {pkg}",
        "update": "sudo pkg update",
        "list_installed": "pkg info",
        "info": "pkg info {pkg}",
    },
}

# Actions that require user approval before running
APPROVAL_REQUIRED = {"install", "remove"}


def detect_package_manager() -> str | None:
    """Return the name of the first available package manager."""
    # Prefer platform-appropriate order
    order = list(_PM_COMMANDS.keys())
    if platform.system() == "Darwin":
        order = ["brew"] + [k for k in order if k != "brew"]
    for cmd in order:
        if shutil.which(cmd):
            return cmd
    return None


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class PackageManagerTool(Tool):
    name = "package_manager"
    description = (
        "Manage system packages via the detected package manager "
        "(apt, dnf, pacman, brew, etc.). "
        "Actions: search, install, remove, update, list_installed, info. "
        "install/remove require user approval."
    )

    # This callback is set by the agent to prompt the user
    approval_callback: Any = None

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "install", "remove", "update", "list_installed", "info"],
                    "description": "The package manager operation to perform.",
                },
                "packages": {
                    "type": "string",
                    "description": "Space-separated package names (required for search/install/remove/info).",
                },
            },
            "required": ["action"],
        }

    async def run(self, *, action: str, packages: str = "", **_: Any) -> ToolResult:
        pm = detect_package_manager()
        if not pm:
            return ToolResult.fail("No supported package manager found on this system.")

        templates = _PM_COMMANDS[pm]
        if action not in templates:
            return ToolResult.fail(f"Unknown action '{action}'. Use: {', '.join(templates.keys())}")

        cmd_template = templates[action]
        if "{pkg}" in cmd_template and not packages:
            return ToolResult.fail(f"Action '{action}' requires 'packages' parameter.")

        cmd = cmd_template.format(pkg=packages)

        # User approval for destructive actions
        if action in APPROVAL_REQUIRED and self.approval_callback:
            approved = await self.approval_callback(
                f"The agent wants to {action} package(s):\n"
                f"   • {packages}\n"
                f"   Command: {cmd}\n"
                f"   Package manager: {pm}"
            )
            if not approved:
                return ToolResult.fail(f"User rejected the {action} request.")

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode(errors="replace")
            if proc.returncode != 0:
                err = stderr.decode(errors="replace")
                return ToolResult.fail(f"Exit code {proc.returncode}\n{output}\n{err}")
            return ToolResult.ok(output[:8000] if len(output) > 8000 else output)
        except asyncio.TimeoutError:
            return ToolResult.fail("Command timed out after 120s.")
        except Exception as exc:
            return ToolResult.fail(str(exc))
