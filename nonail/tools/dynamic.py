"""Dynamic tools — YAML-defined custom tools + LLM tool suggestion system."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import yaml

from .base import Tool, ToolResult

CUSTOM_TOOLS_DIR = Path.home() / ".nonail" / "custom-tools"


# ---------------------------------------------------------------------------
# DynamicTool — wraps a shell command or Python snippet
# ---------------------------------------------------------------------------


class DynamicTool(Tool):
    """A tool defined by a YAML spec file."""

    def __init__(self, spec: dict[str, Any], source_path: Path | None = None):
        self._name = spec["name"]
        self._description = spec.get("description", "")
        self._type = spec.get("type", "shell")  # "shell" or "python"
        self._command_template = spec.get("command_template", "")
        self._python_code = spec.get("python_code", "")
        self._params = spec.get("parameters", {})
        self._requires = spec.get("requires", [])
        self._source_path = source_path

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def parameters_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for pname, pdef in self._params.items():
            properties[pname] = {
                "type": pdef.get("type", "string"),
                "description": pdef.get("description", ""),
            }
            if pdef.get("required", False):
                required.append(pname)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def check_requirements(self) -> list[str]:
        """Return list of missing required system commands."""
        return [r for r in self._requires if not shutil.which(r)]

    async def run(self, **kwargs: Any) -> ToolResult:
        missing = self.check_requirements()
        if missing:
            return ToolResult.fail(
                f"Missing dependencies: {', '.join(missing)}. "
                f"Install them with package_manager(action='install', packages='{' '.join(missing)}')."
            )

        if self._type == "shell":
            return await self._run_shell(kwargs)
        elif self._type == "python":
            return await self._run_python(kwargs)
        return ToolResult.fail(f"Unknown tool type: {self._type}")

    async def _run_shell(self, args: dict[str, Any]) -> ToolResult:
        try:
            cmd = self._command_template.format(**args)
        except KeyError as exc:
            return ToolResult.fail(f"Missing parameter: {exc}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode(errors="replace")
            if proc.returncode != 0:
                err = stderr.decode(errors="replace")
                return ToolResult.fail(f"Exit {proc.returncode}\n{output}\n{err}")
            return ToolResult.ok(output[:8000])
        except asyncio.TimeoutError:
            return ToolResult.fail("Command timed out after 60s.")

    async def _run_python(self, args: dict[str, Any]) -> ToolResult:
        try:
            local_vars: dict[str, Any] = {"args": args, "result": ""}
            exec(self._python_code, {}, local_vars)
            return ToolResult.ok(str(local_vars.get("result", "")))
        except Exception as exc:
            return ToolResult.fail(f"Python error: {exc}")

    def to_yaml(self) -> str:
        spec: dict[str, Any] = {
            "name": self._name,
            "description": self._description,
            "type": self._type,
        }
        if self._type == "shell":
            spec["command_template"] = self._command_template
        elif self._type == "python":
            spec["python_code"] = self._python_code
        if self._params:
            spec["parameters"] = self._params
        if self._requires:
            spec["requires"] = self._requires
        return yaml.safe_dump(spec, default_flow_style=False)


# ---------------------------------------------------------------------------
# Loader — scan ~/.nonail/custom-tools/ for YAML specs
# ---------------------------------------------------------------------------


def load_custom_tools() -> list[DynamicTool]:
    """Load all custom tools from the user's custom-tools directory."""
    tools: list[DynamicTool] = []
    if not CUSTOM_TOOLS_DIR.exists():
        return tools

    for path in sorted(CUSTOM_TOOLS_DIR.glob("*.yaml")):
        try:
            with open(path) as f:
                spec = yaml.safe_load(f)
            if spec and isinstance(spec, dict) and "name" in spec:
                tools.append(DynamicTool(spec, source_path=path))
        except Exception:
            pass  # skip invalid files

    for path in sorted(CUSTOM_TOOLS_DIR.glob("*.yml")):
        try:
            with open(path) as f:
                spec = yaml.safe_load(f)
            if spec and isinstance(spec, dict) and "name" in spec:
                tools.append(DynamicTool(spec, source_path=path))
        except Exception:
            pass

    return tools


def save_custom_tool(spec: dict[str, Any]) -> Path:
    """Save a tool spec to YAML in the custom-tools directory."""
    CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    filename = spec["name"].replace(" ", "_").replace("/", "_") + ".yaml"
    path = CUSTOM_TOOLS_DIR / filename
    with open(path, "w") as f:
        yaml.safe_dump(spec, f, default_flow_style=False)
    return path


def remove_custom_tool(name: str) -> bool:
    """Remove a custom tool by name. Returns True if found and deleted."""
    if not CUSTOM_TOOLS_DIR.exists():
        return False
    for path in CUSTOM_TOOLS_DIR.glob("*.yaml"):
        try:
            with open(path) as f:
                spec = yaml.safe_load(f)
            if spec and spec.get("name") == name:
                path.unlink()
                return True
        except Exception:
            pass
    for path in CUSTOM_TOOLS_DIR.glob("*.yml"):
        try:
            with open(path) as f:
                spec = yaml.safe_load(f)
            if spec and spec.get("name") == name:
                path.unlink()
                return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# SuggestToolTool — LLM proposes new tools for user approval
# ---------------------------------------------------------------------------


class SuggestToolTool(Tool):
    """Meta-tool: the LLM calls this to propose a new custom tool.

    The agent intercepts this call and shows a rich approval prompt.
    """

    name = "suggest_tool"
    description = (
        "Propose a new custom tool for the user to approve. "
        "If approved, the tool is saved and immediately available. "
        "Use this when you need a capability that doesn't exist yet."
    )

    # Set by agent — async callback(spec: dict) -> bool
    approval_callback: Any = None

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short snake_case tool name.",
                },
                "description": {
                    "type": "string",
                    "description": "What the tool does (shown to LLM).",
                },
                "type": {
                    "type": "string",
                    "enum": ["shell", "python"],
                    "description": "Tool type: 'shell' for command templates, 'python' for code snippets.",
                },
                "command_template": {
                    "type": "string",
                    "description": "Shell command with {param} placeholders (for type=shell).",
                },
                "python_code": {
                    "type": "string",
                    "description": "Python code with 'args' dict and 'result' variable (for type=python).",
                },
                "parameters": {
                    "type": "object",
                    "description": "Parameter definitions: {name: {type, description, required}}.",
                },
                "requires": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "System commands this tool depends on (e.g. ['ffmpeg', 'curl']).",
                },
            },
            "required": ["name", "description", "type"],
        }

    async def run(
        self,
        *,
        name: str,
        description: str,
        type: str = "shell",
        command_template: str = "",
        python_code: str = "",
        parameters: dict | None = None,
        requires: list[str] | None = None,
        **_: Any,
    ) -> ToolResult:
        spec: dict[str, Any] = {
            "name": name,
            "description": description,
            "type": type,
        }
        if type == "shell":
            spec["command_template"] = command_template
        elif type == "python":
            spec["python_code"] = python_code
        if parameters:
            spec["parameters"] = parameters
        if requires:
            spec["requires"] = requires

        # The approval callback is set by the agent and handles:
        # 1. Displaying the proposal
        # 2. Getting user input (approve/edit/reject)
        # 3. Saving and hot-loading if approved
        if self.approval_callback:
            approved = await self.approval_callback(spec)
            if approved:
                return ToolResult.ok(
                    f"Tool '{name}' approved and loaded. You can now use it."
                )
            return ToolResult.fail(
                f"Tool '{name}' was rejected by the user. "
                "Try a different approach or use existing tools."
            )

        # Fallback if no callback (shouldn't happen in normal usage)
        path = save_custom_tool(spec)
        return ToolResult.ok(f"Tool '{name}' saved to {path}. Restart to load it.")
