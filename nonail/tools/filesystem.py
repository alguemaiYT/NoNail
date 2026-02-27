"""File-system tools — read, write, list, search files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import Tool, ToolResult


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file given its absolute or relative path."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file."},
            },
            "required": ["path"],
        }

    async def run(self, *, path: str, **_: Any) -> ToolResult:
        try:
            text = Path(path).expanduser().read_text(errors="replace")
            return ToolResult.ok(text)
        except Exception as exc:
            return ToolResult.fail(str(exc))


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write (create or overwrite) a file with the given content."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file."},
                "content": {"type": "string", "description": "Content to write."},
            },
            "required": ["path", "content"],
        }

    async def run(self, *, path: str, content: str, **_: Any) -> ToolResult:
        try:
            p = Path(path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return ToolResult.ok(f"Wrote {len(content)} bytes to {p}")
        except Exception as exc:
            return ToolResult.fail(str(exc))


class ListDirTool(Tool):
    name = "list_directory"
    description = "List files and directories at the given path."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (default: cwd).",
                    "default": ".",
                },
            },
        }

    async def run(self, *, path: str = ".", **_: Any) -> ToolResult:
        try:
            entries = sorted(os.listdir(Path(path).expanduser()))
            return ToolResult.ok("\n".join(entries) if entries else "(empty)")
        except Exception as exc:
            return ToolResult.fail(str(exc))


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Recursively search for files matching a glob pattern."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '**/*.py').",
                },
                "directory": {
                    "type": "string",
                    "description": "Root directory (default: cwd).",
                    "default": ".",
                },
            },
            "required": ["pattern"],
        }

    async def run(
        self, *, pattern: str, directory: str = ".", **_: Any
    ) -> ToolResult:
        try:
            matches = sorted(
                str(p) for p in Path(directory).expanduser().rglob(pattern)
            )
            return ToolResult.ok("\n".join(matches[:500]) if matches else "No matches.")
        except Exception as exc:
            return ToolResult.fail(str(exc))
