"""Stdio entry point and the single versioned websearch response contract."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, ErrorData, ListToolsResult, TextContent, Tool, ToolAnnotations
from pydantic import ValidationError

from websearch import __version__
from websearch.models import (
    MODEL, REASONING_EFFORT, SearchFailure, SearchRequest, SearchResponse, SearchResult,
)
from websearch.runner import CodexRunner, SearchError, Settings

logger = logging.getLogger(__name__)


def error_response(query: str | None, error: SearchFailure) -> SearchResponse:
    return SearchResponse(
        schema_version="1.0", status="error", query=query, provider="codex-cli",
        model=MODEL, reasoning_effort=REASONING_EFFORT, searched_at=None,
        search_queries=[], results=[], count=0, error=error,
    )


async def websearch(arguments: dict[str, Any], runner: CodexRunner) -> SearchResponse:
    """Validate input and return exactly one success/error envelope."""
    query = None
    try:
        request = SearchRequest.model_validate(arguments)
        query = request.query
    except ValidationError:
        return error_response(None, SearchFailure(
            code="INVALID_ARGUMENT", message="Expected query (1..2000 nonblank characters) and max_results (integer 1..10); no extra fields.",
        ))
    try:
        raw, queries = await runner.search(request)
        results: list[SearchResult] = []
        seen: set[str] = set()
        for item in raw.results:
            if item.url not in seen:
                seen.add(item.url)
                results.append(SearchResult(rank=len(results) + 1, **item.model_dump()))
            if len(results) >= request.max_results:
                break
        return SearchResponse(
            schema_version="1.0", status="ok", query=query, provider="codex-cli",
            model=MODEL, reasoning_effort=REASONING_EFFORT, searched_at=datetime.now(timezone.utc),
            search_queries=queries, results=results, count=len(results), error=None,
        )
    except SearchError as exc:
        return error_response(query, SearchFailure(code=exc.code, message=str(exc)))
    except Exception:
        logger.exception("Unexpected websearch failure")
        return error_response(query, SearchFailure(code="INTERNAL_ERROR", message="An internal search error occurred."))


def encode_response(response: SearchResponse) -> CallToolResult:
    # Revalidate the serialized object at the final protocol boundary.
    response = SearchResponse.model_validate_json(response.model_dump_json())
    data = response.model_dump(mode="json")
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
        structured_content=data, is_error=response.status == "error",
    )


def create_server(settings: Settings | None = None) -> Server:
    runner = CodexRunner(settings or Settings.from_env())
    tool = Tool(
        name="websearch",
        description="Search the live web using Codex CLI, fixed to gpt-6-luna with low reasoning. Returns a validated schema_version 1.0 JSON envelope for both success and execution errors. Snippets are grounded model paraphrases, not verbatim search-engine results.",
        input_schema=SearchRequest.model_json_schema(),
        output_schema=SearchResponse.model_json_schema(),
        annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True),
    )

    async def list_tools(_context, _params) -> ListToolsResult:
        return ListToolsResult(tools=[tool])

    async def call_tool(_context, params) -> CallToolResult:
        if params.name != "websearch":
            raise MCPError(ErrorData(code=-32602, message="Unknown tool; only websearch is available."))
        return encode_response(await websearch(params.arguments or {}, runner))

    return Server("websearch", version=__version__, on_list_tools=list_tools, on_call_tool=call_tool)


async def serve() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(serve())
