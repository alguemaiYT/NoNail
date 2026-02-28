"""Tool registry — collects and exposes all built-in NoNail tools."""

from __future__ import annotations

from .advanced import (
    CopyPathTool,
    CronManageTool,
    DeletePathTool,
    DownloadFileTool,
    HttpRequestTool,
    MakeDirectoryTool,
    MovePathTool,
    RunPythonTool,
    SearchTextTool,
    StartBackgroundCommandTool,
)
from .base import Tool, ToolResult
from .bash import BashTool
from .dynamic import DynamicTool, SuggestToolTool, load_custom_tools, save_custom_tool, remove_custom_tool
from .filesystem import ListDirTool, ReadFileTool, SearchFilesTool, WriteFileTool
from .packages import PackageManagerTool
from .process import ProcessKillTool, ProcessListTool
from .system import SystemInfoTool

ALL_TOOLS: list[Tool] = [
    BashTool(),
    ReadFileTool(),
    WriteFileTool(),
    ListDirTool(),
    SearchFilesTool(),
    SearchTextTool(),
    MakeDirectoryTool(),
    CopyPathTool(),
    MovePathTool(),
    DeletePathTool(),
    RunPythonTool(),
    StartBackgroundCommandTool(),
    HttpRequestTool(),
    DownloadFileTool(),
    CronManageTool(),
    ProcessListTool(),
    ProcessKillTool(),
    SystemInfoTool(),
    PackageManagerTool(),
    SuggestToolTool(),
]

TOOLS_BY_NAME: dict[str, Tool] = {t.name: t for t in ALL_TOOLS}

__all__ = [
    "Tool",
    "ToolResult",
    "ALL_TOOLS",
    "TOOLS_BY_NAME",
    "DynamicTool",
    "SuggestToolTool",
    "PackageManagerTool",
    "load_custom_tools",
    "save_custom_tool",
    "remove_custom_tool",
    "BashTool",
    "ReadFileTool",
    "WriteFileTool",
    "ListDirTool",
    "SearchFilesTool",
    "SearchTextTool",
    "MakeDirectoryTool",
    "CopyPathTool",
    "MovePathTool",
    "DeletePathTool",
    "RunPythonTool",
    "StartBackgroundCommandTool",
    "HttpRequestTool",
    "DownloadFileTool",
    "CronManageTool",
    "ProcessListTool",
    "ProcessKillTool",
    "SystemInfoTool",
]
