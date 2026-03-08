"""Advanced tools for network, automation, scheduling, and richer file control."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from .base import Tool, ToolResult


class SearchTextTool(Tool):
    name = "search_text"
    description = "Search text/regex content recursively inside files with line numbers."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex or plain pattern."},
                "directory": {
                    "type": "string",
                    "description": "Root directory for recursive search.",
                    "default": ".",
                },
                "file_glob": {
                    "type": "string",
                    "description": "Glob filter for files (e.g. '*.py').",
                    "default": "*",
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "Case-insensitive search.",
                    "default": False,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matches returned.",
                    "default": 200,
                },
            },
            "required": ["pattern"],
        }

    async def run(
        self,
        *,
        pattern: str,
        directory: str = ".",
        file_glob: str = "*",
        ignore_case: bool = False,
        max_results: int = 200,
        **_: Any,
    ) -> ToolResult:
        try:
            root = Path(directory).expanduser()
            flags = re.IGNORECASE if ignore_case else 0
            regex = re.compile(pattern, flags)
            matches: list[str] = []

            for path in root.rglob(file_glob):
                if not path.is_file():
                    continue
                try:
                    with path.open("r", errors="replace") as handle:
                        for line_no, line in enumerate(handle, start=1):
                            if regex.search(line):
                                matches.append(
                                    f"{path}:{line_no}:{line.rstrip()}"
                                )
                                if len(matches) >= max_results:
                                    return ToolResult.ok(
                                        "\n".join(matches)
                                        + f"\n... truncated at {max_results} results"
                                    )
                except Exception:
                    continue

            if not matches:
                return ToolResult.ok("No matches found.")
            return ToolResult.ok("\n".join(matches))
        except Exception as exc:
            return ToolResult.fail(str(exc))


class CopyPathTool(Tool):
    name = "copy_path"
    description = "Copy file or directory to another path."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source path."},
                "destination": {"type": "string", "description": "Destination path."},
                "recursive": {
                    "type": "boolean",
                    "description": "Required for directory copy.",
                    "default": False,
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite destination if possible.",
                    "default": False,
                },
            },
            "required": ["source", "destination"],
        }

    async def run(
        self,
        *,
        source: str,
        destination: str,
        recursive: bool = False,
        overwrite: bool = False,
        **_: Any,
    ) -> ToolResult:
        try:
            src = Path(source).expanduser()
            dst = Path(destination).expanduser()

            if not src.exists():
                return ToolResult.fail(f"Source not found: {src}")

            if dst.exists() and not overwrite:
                return ToolResult.fail(f"Destination already exists: {dst}")

            dst.parent.mkdir(parents=True, exist_ok=True)

            if src.is_dir():
                if not recursive:
                    return ToolResult.fail(
                        "Source is a directory. Set recursive=true to copy directories."
                    )
                shutil.copytree(src, dst, dirs_exist_ok=overwrite)
            else:
                if dst.is_dir():
                    shutil.copy2(src, dst / src.name)
                else:
                    shutil.copy2(src, dst)
            return ToolResult.ok(f"Copied {src} -> {dst}")
        except Exception as exc:
            return ToolResult.fail(str(exc))


class MovePathTool(Tool):
    name = "move_path"
    description = "Move or rename file/directory."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source path."},
                "destination": {"type": "string", "description": "Destination path."},
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite destination if it exists.",
                    "default": False,
                },
            },
            "required": ["source", "destination"],
        }

    async def run(
        self, *, source: str, destination: str, overwrite: bool = False, **_: Any
    ) -> ToolResult:
        try:
            src = Path(source).expanduser()
            dst = Path(destination).expanduser()
            if not src.exists():
                return ToolResult.fail(f"Source not found: {src}")
            if dst.exists() and not overwrite:
                return ToolResult.fail(f"Destination already exists: {dst}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return ToolResult.ok(f"Moved {src} -> {dst}")
        except Exception as exc:
            return ToolResult.fail(str(exc))


class DeletePathTool(Tool):
    name = "delete_path"
    description = "Delete file or directory."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to delete."},
                "recursive": {
                    "type": "boolean",
                    "description": "Required for non-empty directories.",
                    "default": False,
                },
            },
            "required": ["path"],
        }

    async def run(self, *, path: str, recursive: bool = False, **_: Any) -> ToolResult:
        try:
            target = Path(path).expanduser()
            if not target.exists():
                return ToolResult.fail(f"Path not found: {target}")
            if target.is_dir():
                if recursive:
                    shutil.rmtree(target)
                else:
                    target.rmdir()
            else:
                target.unlink()
            return ToolResult.ok(f"Deleted {target}")
        except Exception as exc:
            return ToolResult.fail(str(exc))


class MakeDirectoryTool(Tool):
    name = "make_directory"
    description = "Create directories (mkdir -p behavior by default)."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to create."},
                "parents": {
                    "type": "boolean",
                    "description": "Create parent directories.",
                    "default": True,
                },
                "exist_ok": {
                    "type": "boolean",
                    "description": "Do not fail if directory exists.",
                    "default": True,
                },
            },
            "required": ["path"],
        }

    async def run(
        self, *, path: str, parents: bool = True, exist_ok: bool = True, **_: Any
    ) -> ToolResult:
        try:
            target = Path(path).expanduser()
            target.mkdir(parents=parents, exist_ok=exist_ok)
            return ToolResult.ok(f"Directory ready: {target}")
        except Exception as exc:
            return ToolResult.fail(str(exc))


class HttpRequestTool(Tool):
    name = "http_request"
    description = "Make HTTP requests (GET, POST, PUT, PATCH, DELETE) to external APIs."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Request URL."},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
                    "default": "GET",
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers map.",
                    "additionalProperties": {"type": "string"},
                },
                "body": {
                    "type": "string",
                    "description": "Raw request body for POST/PUT/PATCH.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds.",
                    "default": 30,
                },
            },
            "required": ["url"],
        }

    async def run(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout: int = 30,
        **_: Any,
    ) -> ToolResult:
        try:
            return await asyncio.to_thread(
                self._sync_request, url, method, headers or {}, body, timeout
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))

    def _sync_request(
        self,
        url: str,
        method: str,
        headers: dict[str, str],
        body: str | None,
        timeout: int,
    ) -> ToolResult:
        data = body.encode() if body is not None else None
        req = urlrequest.Request(url=url, method=method.upper(), data=data, headers=headers)
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                text = raw.decode(errors="replace")
                if len(text) > 12000:
                    text = text[:12000] + "\n... response truncated ..."
                header_lines = "\n".join(f"{k}: {v}" for k, v in resp.headers.items())
                return ToolResult.ok(
                    f"Status: {resp.status}\nURL: {resp.geturl()}\nHeaders:\n{header_lines}\n\nBody:\n{text}"
                )
        except urlerror.HTTPError as exc:
            err_body = exc.read().decode(errors="replace")
            return ToolResult.fail(
                f"HTTP {exc.code} {exc.reason}\nURL: {url}\nBody:\n{err_body}"
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))


class DownloadFileTool(Tool):
    name = "download_file"
    description = "Download a URL to a local file path."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Source URL."},
                "path": {"type": "string", "description": "Destination file path."},
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite destination file.",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds.",
                    "default": 60,
                },
            },
            "required": ["url", "path"],
        }

    async def run(
        self,
        *,
        url: str,
        path: str,
        overwrite: bool = False,
        timeout: int = 60,
        **_: Any,
    ) -> ToolResult:
        try:
            return await asyncio.to_thread(self._sync_download, url, path, overwrite, timeout)
        except Exception as exc:
            return ToolResult.fail(str(exc))

    def _sync_download(
        self, url: str, path: str, overwrite: bool, timeout: int
    ) -> ToolResult:
        target = Path(path).expanduser()
        if target.exists() and not overwrite:
            return ToolResult.fail(f"Destination exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with urlrequest.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
        target.write_bytes(data)
        return ToolResult.ok(f"Downloaded {len(data)} bytes to {target}")


class RunPythonTool(Tool):
    name = "run_python"
    description = "Execute Python code snippet using local interpreter."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute."},
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds.",
                    "default": 120,
                },
            },
            "required": ["code"],
        }

    async def run(self, *, code: str, timeout: int = 120, **_: Any) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out_text = stdout.decode(errors="replace")
            err_text = stderr.decode(errors="replace")
            if proc.returncode != 0:
                return ToolResult.fail(
                    f"exit code {proc.returncode}\n{err_text.strip() or out_text.strip()}"
                )
            combined = out_text + ("\n" + err_text if err_text else "")
            return ToolResult.ok(combined.strip())
        except asyncio.TimeoutError:
            return ToolResult.fail(f"Python execution timed out after {timeout}s")
        except Exception as exc:
            return ToolResult.fail(str(exc))


class StartBackgroundCommandTool(Tool):
    name = "start_background_command"
    description = "Start long-running shell command detached and return PID/log paths."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to execute."},
                "cwd": {
                    "type": "string",
                    "description": "Working directory for command.",
                },
                "stdout_path": {
                    "type": "string",
                    "description": "Optional stdout log file path.",
                },
                "stderr_path": {
                    "type": "string",
                    "description": "Optional stderr log file path.",
                },
            },
            "required": ["command"],
        }

    async def run(
        self,
        *,
        command: str,
        cwd: str | None = None,
        stdout_path: str | None = None,
        stderr_path: str | None = None,
        **_: Any,
    ) -> ToolResult:
        try:
            log_dir = Path.home() / ".nonail" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = int(time.time())
            stdout_file = Path(stdout_path).expanduser() if stdout_path else log_dir / f"bg-{stamp}.out.log"
            stderr_file = Path(stderr_path).expanduser() if stderr_path else log_dir / f"bg-{stamp}.err.log"
            stdout_file.parent.mkdir(parents=True, exist_ok=True)
            stderr_file.parent.mkdir(parents=True, exist_ok=True)

            out_handle = stdout_file.open("ab")
            err_handle = stderr_file.open("ab")
            try:
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=str(Path(cwd).expanduser()) if cwd else None,
                    stdout=out_handle,
                    stderr=err_handle,
                    start_new_session=True,
                )
            finally:
                out_handle.close()
                err_handle.close()

            return ToolResult.ok(
                f"Started PID {proc.pid}\nstdout: {stdout_file}\nstderr: {stderr_file}"
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))


class CronManageTool(Tool):
    name = "cron_manage"
    description = "List, add, or remove user crontab jobs (supports tagged entries)."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "add", "remove"],
                    "description": "Operation on user crontab.",
                },
                "expression": {
                    "type": "string",
                    "description": "Cron expression (required for add).",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to schedule (required for add).",
                },
                "tag": {
                    "type": "string",
                    "description": "Tag marker for job management.",
                    "default": "default",
                },
            },
            "required": ["action"],
        }

    async def run(
        self,
        *,
        action: str,
        expression: str | None = None,
        command: str | None = None,
        tag: str = "default",
        **_: Any,
    ) -> ToolResult:
        try:
            if action == "list":
                current = await self._read_crontab()
                return ToolResult.ok(current if current.strip() else "(empty)")

            if action == "add":
                if not expression or not command:
                    return ToolResult.fail("expression and command are required for action=add")
                current = await self._read_crontab()
                lines = [line for line in current.splitlines() if line.strip()]
                new_line = f"{expression} {command} # nonail:{tag}"
                if new_line in lines:
                    return ToolResult.ok("Cron job already exists.")
                lines.append(new_line)
                await self._write_crontab(lines)
                return ToolResult.ok(f"Cron job added: {new_line}")

            if action == "remove":
                marker = f"# nonail:{tag}"
                current = await self._read_crontab()
                lines = [line for line in current.splitlines() if line.strip()]
                keep = [line for line in lines if marker not in line]
                removed = len(lines) - len(keep)
                await self._write_crontab(keep)
                return ToolResult.ok(f"Removed {removed} cron job(s) with tag {tag}.")

            return ToolResult.fail(f"Unsupported action: {action}")
        except FileNotFoundError:
            return ToolResult.fail("crontab command not found on this system.")
        except Exception as exc:
            return ToolResult.fail(str(exc))

    async def _read_crontab(self) -> str:
        proc = await asyncio.create_subprocess_exec(
            "crontab",
            "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        if "no crontab for" in err.lower():
            return ""
        raise RuntimeError(err.strip() or "Unable to read crontab.")

    async def _write_crontab(self, lines: list[str]) -> None:
        payload = ("\n".join(lines) + "\n") if lines else ""
        proc = await asyncio.create_subprocess_exec(
            "crontab",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(payload.encode())
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode(errors="replace").strip() or "Unable to write crontab.")
