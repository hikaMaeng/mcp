"""Independent stdio MCP server exposing explicit filesystem tools."""

import asyncio
import json
import logging
from typing import Any

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, ErrorData, ListToolsResult, TextContent, Tool, ToolAnnotations

from fileiomcp import __version__
from fileiomcp.operations import FileOperationError, OPERATIONS

logger = logging.getLogger(__name__)


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


STRING = {"type": "string"}
BOOL = {"type": "boolean", "default": False}
INT = {"type": "integer"}
LINE_LIST = {"type": "array", "items": STRING, "description": "Logical lines without newline characters."}
TEXT_CHUNK = {"type": "string"}

TOOL_DEFINITIONS = [
    ("file_read", "Read a text file with numbered lines and SHA-256. Defaults to at most 200 lines. Inspect existing files before overwriting them.", {"path": STRING, "start_line": INT, "end_line": INT, "encoding": STRING}, ["path"]),
    ("directory_create", "Create a directory. parents creates missing ancestors; exist_ok allows an existing directory.", {"path": STRING, "parents": BOOL, "exist_ok": BOOL}, ["path"]),
    ("directory_delete", "Delete an empty directory, or recursively delete it when recursive=true.", {"path": STRING, "recursive": BOOL}, ["path"]),
    ("directory_move", "Move a directory to the exact destination path. Existing destinations require overwrite=true.", {"source": STRING, "destination": STRING, "overwrite": BOOL}, ["source", "destination"]),
    ("directory_copy", "Copy a directory tree to the exact destination path. Existing destinations require overwrite=true.", {"source": STRING, "destination": STRING, "overwrite": BOOL}, ["source", "destination"]),
    ("file_create", "Create an empty file by omitting content, then write documents/code with consecutive file_append calls. Keep any inline content short (prefer at most 800 characters). Do not generate several complete files in one response. Wait for each tool result before the next call. Replacement requires overwrite=true; inspect existing files with file_read first.", {"path": STRING, "content": TEXT_CHUNK, "create_parents": BOOL, "overwrite": BOOL, "encoding": STRING}, ["path"]),
    ("file_append", "Append one small text chunk to an existing file (prefer at most 800 characters per call). Wait for success before appending the next chunk. Each append is committed immediately: if a call fails or disconnects, read the file before retrying to avoid duplicate text. Continue until the entire document is written.", {"path": STRING, "content": TEXT_CHUNK, "encoding": STRING}, ["path", "content"]),
    ("file_delete", "Delete a file.", {"path": STRING}, ["path"]),
    ("file_move", "Move a file to the exact destination path. Existing destinations require overwrite=true.", {"source": STRING, "destination": STRING, "overwrite": BOOL}, ["source", "destination"]),
    ("file_copy", "Copy a file to the exact destination path. Existing destinations require overwrite=true.", {"source": STRING, "destination": STRING, "overwrite": BOOL}, ["source", "destination"]),
    ("file_edit_lines", "Edit a text file by 1-based inclusive range deletion/replacement or insert_after. insert_after line 0 inserts at the beginning. Pass replacement/insertion as lines; newline characters inside each item are rejected.", {"path": STRING, "operation": {"type": "string", "enum": ["delete", "replace", "insert_after"]}, "start_line": INT, "end_line": INT, "lines": LINE_LIST, "encoding": STRING}, ["path", "operation", "start_line"]),
]

TOOLS = [
    Tool(
        name=name,
        description=description,
        input_schema=_schema(properties, required),
        annotations=ToolAnnotations(read_only_hint=name == "file_read", destructive_hint=name != "file_read", open_world_hint=True),
    )
    for name, description, properties, required in TOOL_DEFINITIONS
]


def validate_arguments(name: str, arguments: dict[str, Any]) -> None:
    schema = next(tool.input_schema for tool in TOOLS if tool.name == name)
    if not isinstance(arguments, dict):
        raise FileOperationError("Arguments must be a JSON object")
    unknown = set(arguments) - schema["properties"].keys()
    missing = set(schema["required"]) - arguments.keys()
    if unknown or missing:
        raise FileOperationError(f"Unknown fields: {sorted(unknown)}; missing fields: {sorted(missing)}")
    for key, value in arguments.items():
        spec = schema["properties"][key]
        kind = spec["type"]
        valid = {"string": isinstance(value, str), "boolean": type(value) is bool,
                 "integer": type(value) is int, "array": isinstance(value, list)}[kind]
        if not valid or ("enum" in spec and value not in spec["enum"]):
            raise FileOperationError(f"Invalid {key}: expected {kind}")
        if kind == "array" and any(not isinstance(item, str) for item in value):
            raise FileOperationError(f"Invalid {key}: expected strings")


def create_server() -> Server:
    async def list_tools(_context, _params) -> ListToolsResult:
        return ListToolsResult(tools=TOOLS)

    async def call_tool(_context, params) -> CallToolResult:
        operation = OPERATIONS.get(params.name)
        if operation is None:
            raise MCPError(ErrorData(code=-32602, message="Unknown file I/O tool"))
        try:
            arguments = params.arguments or {}
            validate_arguments(params.name, arguments)
            result = operation(**arguments)
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
                structured_content=result,
            )
        except (FileOperationError, OSError, UnicodeError, LookupError, TypeError) as exc:
            logger.info("File I/O operation failed: %s", exc)
            data = {"error": type(exc).__name__, "message": str(exc)}
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
                structured_content=data,
                is_error=True,
            )
        except Exception:
            logger.exception("Unexpected file I/O failure")
            data = {"error": "InternalError", "message": "An internal file I/O error occurred."}
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(data))], structured_content=data, is_error=True)

    return Server(
        "fileiomcp",
        version=__version__,
        instructions=(
            "These tools operate on local files. Existing files are protected: use file_read "
            "to inspect them and overwrite=true only when replacing them is intended. "
            "For documents and code, create an empty file by omitting content, then append "
            "small chunks (prefer at most 800 characters) sequentially with file_append. "
            "Generate one tool call at a time and wait for its result; do not emit multiple "
            "complete files in a single model response. After a disconnect, inspect file_read "
            "before retrying any append because an earlier write might already be committed. "
            "The client must allow enough output tokens to finish every JSON tool argument; "
            "the server cannot receive or repair a truncated tool call."
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(serve())
