"""Tool registry — collects and exposes all built-in NoNail tools."""

from __future__ import annotations

from .base import Tool, ToolResult
from .bash import BashTool
from .filesystem import ListDirTool, ReadFileTool, SearchFilesTool, WriteFileTool
from .process import ProcessKillTool, ProcessListTool
from .system import SystemInfoTool

ALL_TOOLS: list[Tool] = [
    BashTool(),
    ReadFileTool(),
    WriteFileTool(),
    ListDirTool(),
    SearchFilesTool(),
    ProcessListTool(),
    ProcessKillTool(),
    SystemInfoTool(),
]

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in ALL_TOOLS}

__all__ = [
    "Tool",
    "ToolResult",
    "ALL_TOOLS",
    "TOOLS_BY_NAME",
    "BashTool",
    "ReadFileTool",
    "WriteFileTool",
    "ListDirTool",
    "SearchFilesTool",
    "ProcessListTool",
    "ProcessKillTool",
    "SystemInfoTool",
]
