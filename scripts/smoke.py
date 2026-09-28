"""Run a real stdio MCP request and save the normalized response."""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from mcp import Client, StdioServerParameters
from jsonschema import Draft202012Validator


async def run(query: str, max_results: int, output: Path) -> None:
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "websearch"], env=dict(os.environ),
    )
    started = time.monotonic()
    async with Client(parameters, read_timeout_seconds=210) as client:
        tools = await client.list_tools()
        names = [tool.name for tool in tools.tools]
        assert names == ["websearch"], names
        validator = Draft202012Validator(tools.tools[0].output_schema)
        invalid = await client.call_tool("websearch", {"query": " ", "model": "another-model"})
        assert invalid.is_error
        validator.validate(invalid.structured_content)
        assert invalid.structured_content["error"]["code"] == "INVALID_ARGUMENT"
        result = await client.call_tool("websearch", {"query": query, "max_results": max_results})
        payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        record = {"elapsed_seconds": round(time.monotonic() - started, 3), "tools": names, "result": payload}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False, indent=2))
        data = result.structured_content
        validator.validate(data)
        assert data == json.loads(result.content[0].text)
        assert not result.is_error, data
        assert data and data["model"] == "gpt-6-luna" and data["reasoning_effort"] == "low"
        assert data["count"] == len(data["results"]) <= max_results


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="Python 공식 asyncio 문서")
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("artifacts/live-smoke.json"))
    args = parser.parse_args()
    asyncio.run(run(args.query, args.max_results, args.output))
