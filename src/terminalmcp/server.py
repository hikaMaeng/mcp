"""Run each terminal request in a fresh, bounded OS process."""

import asyncio
import locale
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, ErrorData, ListToolsResult, TextContent, Tool, ToolAnnotations

from terminalmcp import __version__

MAX_TIMEOUT_SECONDS = 600
MAX_OUTPUT_BYTES = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_OUTPUT_BYTES = 200_000

TOOL = Tool(
    name="terminal_run",
    description=(
        "Run one shell command in a fresh OS process (Windows PowerShell, macOS/Linux /bin/sh) and return its "
        "stdout, stderr, exit code, and timeout status. On Windows, use PowerShell commands such as Get-Process "
        "and Get-CimInstance; Linux commands such as cat /proc/meminfo are not available. "
        "Every call starts a new process; shell state, variables, and working-directory changes do not persist "
        "between calls. Sends periodic progress notifications with recent output when the client supplies a "
        "progress token; MCP cancellation terminates the process tree. If a command fails, report the error and "
        "do not repeat the identical command. The command can access anything permitted to this server's OS user."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "minLength": 1, "maxLength": 20000},
            "cwd": {"type": "string", "description": "Working directory; defaults to the server's current directory."},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": MAX_TIMEOUT_SECONDS, "default": DEFAULT_TIMEOUT_SECONDS},
            "max_output_bytes": {"type": "integer", "minimum": 1, "maximum": MAX_OUTPUT_BYTES, "default": DEFAULT_MAX_OUTPUT_BYTES},
        },
        "required": ["command"],
        "additionalProperties": False,
    },
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=True),
)


def _validate(arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("Arguments must be an object")
    if set(arguments) - {"command", "cwd", "timeout_seconds", "max_output_bytes"}:
        raise ValueError("Unknown argument")
    command = arguments.get("command")
    if not isinstance(command, str) or not command.strip() or len(command) > 20000 or "\x00" in command:
        raise ValueError("command must contain 1 to 20000 non-NUL characters")
    cwd = arguments.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not cwd or "\x00" in cwd):
        raise ValueError("cwd must be a non-empty path string")
    timeout = arguments.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    limit = arguments.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES)
    if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be an integer from 1 to {MAX_TIMEOUT_SECONDS}")
    if type(limit) is not int or not 1 <= limit <= MAX_OUTPUT_BYTES:
        raise ValueError(f"max_output_bytes must be an integer from 1 to {MAX_OUTPUT_BYTES}")
    return {"command": command, "cwd": cwd, "timeout_seconds": timeout, "max_output_bytes": limit}


def _shell_command(command: str) -> list[str]:
    if os.name == "nt":
        powershell = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        utf8_setup = (
            "$utf8 = [System.Text.UTF8Encoding]::new($false); "
            "$OutputEncoding = $utf8; [Console]::InputEncoding = $utf8; "
            "[Console]::OutputEncoding = $utf8; "
        )
        return [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", utf8_setup + command]
    return ["/bin/sh", "-c", command]


def _decode_output(data: bytes) -> tuple[str, str]:
    """Decode captured terminal bytes without corrupting Windows OEM/ANSI output."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass

    encodings: list[str] = []
    if os.name == "nt":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            encodings.extend(f"cp{code_page}" for code_page in (kernel.GetOEMCP(), kernel.GetACP()))
        except (AttributeError, OSError):
            pass
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)
    for encoding in dict.fromkeys(encodings):
        try:
            return data.decode(encoding), encoding
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-with-replacements"


async def _kill_tree(process: asyncio.subprocess.Process) -> None:
    try:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(process.pid), "/T", "/F",
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            await killer.wait()
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def _read_capped(
    stream: asyncio.StreamReader,
    cap: int,
    on_output: Callable[[str, bytes], Awaitable[None]],
    stream_name: str,
) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    exceeded = False
    while chunk := await stream.read(65536):
        await on_output(stream_name, chunk)
        remaining = cap - size
        if remaining > 0:
            chunks.append(chunk[:remaining])
            size += min(len(chunk), remaining)
        if len(chunk) > remaining:
            exceeded = True
            break
    return b"".join(chunks), exceeded


async def run_terminal(
    arguments: dict[str, Any],
    report_progress: Callable[[float, str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Execute the validated request in a fresh process, never a shared shell."""
    try:
        request = _validate(arguments)
        cwd = Path(request["cwd"]).expanduser() if request["cwd"] else None
        if cwd is not None and not cwd.is_dir():
            raise ValueError("cwd must be an existing directory")
    except (ValueError, OSError) as exc:
        return {"status": "error", "error": "INVALID_ARGUMENT", "message": str(exc)}

    options: dict[str, Any] = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {"start_new_session": True}
    try:
        process = await asyncio.create_subprocess_exec(
            *_shell_command(request["command"]), cwd=cwd,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options,
        )
    except (OSError, ValueError) as exc:
        return {"status": "error", "error": "START_FAILED", "message": str(exc)}

    started = time.monotonic()
    output_tail = {"stdout": bytearray(), "stderr": bytearray()}
    progress_lock = asyncio.Lock()
    last_progress_at = 0.0
    progress_number = 0

    async def report(message: str, *, force: bool = False) -> None:
        nonlocal last_progress_at, progress_number
        if report_progress is None:
            return
        async with progress_lock:
            now = time.monotonic()
            if not force and now - last_progress_at < 0.5:
                return
            last_progress_at = now
            progress_number += 1
            try:
                await report_progress(progress_number, f"{message}\nElapsed: {now - started:.1f}s")
            except Exception:
                # Progress is best-effort; it must not interrupt the command.
                pass

    async def on_output(stream_name: str, chunk: bytes) -> None:
        tail = output_tail[stream_name]
        tail.extend(chunk)
        if len(tail) > 2400:
            del tail[:-2400]
        rendered = bytes(tail).decode("utf-8", errors="replace").strip()
        await report(f"{stream_name}:\n{rendered}" if rendered else f"{stream_name}: output received")

    def recent_output() -> str:
        parts = []
        for stream_name, tail in output_tail.items():
            rendered = bytes(tail).decode("utf-8", errors="replace").strip()
            if rendered:
                parts.append(f"{stream_name}:\n{rendered}")
        return "\n".join(parts) or "No output yet."

    stdout_reader = asyncio.create_task(_read_capped(
        process.stdout, request["max_output_bytes"], on_output, "stdout",
    ))
    stderr_reader = asyncio.create_task(_read_capped(
        process.stderr, request["max_output_bytes"], on_output, "stderr",
    ))
    readers = (stdout_reader, stderr_reader)
    process_wait = asyncio.create_task(process.wait())
    timed_out = False
    output_limited = False
    try:
        async with asyncio.timeout(request["timeout_seconds"]):
            await report("Process started; waiting for output.", force=True)
            pending = set(readers) | {process_wait}
            while pending:
                done, pending = await asyncio.wait(pending, timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
                if any(task in done and task is not process_wait and task.result()[1] for task in readers):
                    output_limited = True
                    break
                if not pending:
                    break
                if not done:
                    await report(f"Process is still running.\n{recent_output()}", force=True)
    except TimeoutError:
        timed_out = True
    except asyncio.CancelledError:
        await _kill_tree(process)
        for task in readers:
            task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        raise
    if timed_out or output_limited:
        await _kill_tree(process)
    await process_wait
    if timed_out or output_limited:
        try:
            await asyncio.wait_for(asyncio.gather(*readers), timeout=5)
        except asyncio.TimeoutError:
            for task in readers:
                task.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
    stdout = stdout_reader.result()[0] if stdout_reader.done() and not stdout_reader.cancelled() else b""
    stderr = stderr_reader.result()[0] if stderr_reader.done() and not stderr_reader.cancelled() else b""
    stdout_text, stdout_encoding = _decode_output(stdout)
    stderr_text, stderr_encoding = _decode_output(stderr)
    failure_code = "TIMEOUT" if timed_out else "OUTPUT_LIMIT" if output_limited else "COMMAND_FAILED" if process.returncode else None
    result = {
        "status": "error" if failure_code else "ok", "error": failure_code,
        "exit_code": process.returncode, "timed_out": timed_out,
        "output_limited": output_limited, "stdout": stdout_text,
        "stderr": stderr_text, "output_encoding": {"stdout": stdout_encoding, "stderr": stderr_encoding},
    }
    end_state = "timed out" if timed_out else "output limit reached" if output_limited else f"process exited with code {process.returncode}"
    await report(f"{end_state}.", force=True)
    return result


def create_server() -> Server:
    async def list_tools(_context, _params) -> ListToolsResult:
        return ListToolsResult(tools=[TOOL])

    async def call_tool(context, params) -> CallToolResult:
        if params.name != TOOL.name:
            raise MCPError(ErrorData(code=-32602, message="Unknown terminal tool"))
        result = await run_terminal(
            params.arguments or {},
            report_progress=lambda progress, message: context.session.report_progress(
                progress=progress, message=message,
            ),
        )
        lines = [f"Status: {result['status']}"]
        if result.get("error"):
            lines.append(f"Error: {result['error']}")
        if result.get("message"):
            lines.append(result["message"])
        if "exit_code" in result:
            lines.append(f"Exit code: {result['exit_code']}")
        encodings = result.get("output_encoding", {})
        if encodings and any(name != "utf-8" for name in encodings.values()):
            lines.append(f"Output encoding: stdout={encodings.get('stdout')}, stderr={encodings.get('stderr')}")
        for stream_name in ("stdout", "stderr"):
            output = result.get(stream_name, "")
            if output:
                lines.extend((f"{stream_name}:", output.rstrip()))
        if result.get("timed_out"):
            lines.append("The command timed out and was terminated.")
        if result.get("output_limited"):
            lines.append("Output limit reached; the process was terminated.")
        if not result.get("stdout") and not result.get("stderr") and result["status"] == "ok":
            lines.append("The command completed without output.")
        failed = result["status"] == "error"
        return CallToolResult(
            content=[TextContent(type="text", text="\n".join(lines))],
            structured_content=result, is_error=failed,
        )

    return Server(
        "terminalmcp", version=__version__,
        instructions=(
            "terminal_run starts a fresh, one-shot shell process for every call (Windows PowerShell; /bin/sh on "
            "macOS/Linux). On Windows, use native PowerShell commands, not Linux /proc commands. No interactive session or process "
            "state is retained. Commands run with the MCP server user's OS permissions; inspect commands and paths "
            "carefully. Progress notifications require a client progress token. MCP cancellation terminates the "
            "active command process tree. Command failures include exit status and decoded stderr; do not repeat "
            "an identical failed command. Each call has a 600-second maximum and bounded captured output."
        ),
        on_list_tools=list_tools, on_call_tool=call_tool,
    )


async def serve() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(serve())
