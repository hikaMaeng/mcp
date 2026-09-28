"""Exercise the real stdio server with the loaded LM Studio model in a temporary directory."""

import asyncio
import argparse
import json
import os
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path

from mcp import Client, StdioServerParameters


def predict(messages, tools):
    body = {"model": "mimo-lmstudio-dflash", "messages": messages, "tools": tools,
            "max_tokens": 8192, "temperature": 1, "presence_penalty": 1.5, "stream": True}
    request = urllib.request.Request("http://127.0.0.1:12345/v1/chat/completions",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    calls, content, finish = {}, "", None
    started = last_progress = time.monotonic()
    with urllib.request.urlopen(request, timeout=600) as response:
        for line in response:
            if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
                continue
            event = json.loads(line[6:])
            for choice in event.get("choices", []):
                delta = choice.get("delta", {})
                content += delta.get("content") or ""
                for call in delta.get("tool_calls", []):
                    item = calls.setdefault(call["index"], {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if call.get("id"):
                        item["id"] = call["id"]
                    function = call.get("function", {})
                    item["function"]["name"] += function.get("name") or ""
                    item["function"]["arguments"] += function.get("arguments") or ""
                finish = choice.get("finish_reason") or finish
            if time.monotonic() - last_progress > 25:
                print(f"generation_seconds={time.monotonic()-started:.0f}; argument_chars={sum(len(x['function']['arguments']) for x in calls.values())}", flush=True)
                last_progress = time.monotonic()
    return {"role": "assistant", "content": content or None, "tool_calls": list(calls.values())}, finish


async def main(files, output):
    report = {"max_tokens": 8192, "requested_files": files, "rounds": []}
    output.parent.mkdir(exist_ok=True)
    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "fileiomcp"], env=dict(os.environ))
    try:
        with tempfile.TemporaryDirectory(prefix="fileiomcp-live-") as folder:
            root = Path(folder).resolve()
            async with Client(parameters, read_timeout_seconds=30) as client:
                listing = await client.list_tools()
                allowed = {"directory_create", "file_create", "file_append", "file_read"}
                tools = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
                         for t in listing.tools if t.name in allowed]
                descriptions = {"cal.html": "간단한 계산기", "fluppy.html": "플러피 게임", "tetris.html": "테트리스 게임"}
                tasks = ', '.join(f"{name} ({descriptions[name]})" for name in files)
                messages = [{"role": "user", "content": f"{root.as_posix()} 폴더 안에 {tasks}을 HTML 파일로 생성해줘."}]
                report["messages"] = messages
                for index in range(5):
                    message, finish = await asyncio.to_thread(predict, messages, tools)
                    record = {"round": index, "finish_reason": finish, "calls": []}
                    report["rounds"].append(record)
                    print(f"round={index}; finish_reason={finish}; calls={len(message['tool_calls'])}", flush=True)
                    messages.append(message)
                    if not message["tool_calls"]:
                        break
                    for call in message["tool_calls"]:
                        fn = call["function"]
                        arguments = json.loads(fn["arguments"])
                        path = Path(arguments["path"]).resolve()
                        if fn["name"] not in allowed or (path != root and root not in path.parents):
                            raise RuntimeError("Live test rejected a tool call outside its temporary directory")
                        result = await client.call_tool(fn["name"], arguments)
                        record["calls"].append({"name": fn["name"], "argument_chars": len(fn["arguments"]), "is_error": result.is_error})
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result.content[0].text})
                        report["files"] = {p.name: p.stat().st_size for p in root.glob("*.html")}
                        save()
                report["files"] = {p.name: p.stat().st_size for p in root.glob("*.html")}
                report["passed"] = all((root / name).is_file() and (root / name).stat().st_size > 100 for name in files)
                report["messages"] = messages
    except Exception as exc:
        report["passed"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["error_traceback"] = traceback.format_exc()
    finally:
        save()
        print(json.dumps({k: v for k, v in report.items() if k not in {"messages", "error_traceback"}}, ensure_ascii=False), flush=True)
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", choices=["cal.html", "fluppy.html", "tetris.html"], default=["cal.html", "fluppy.html", "tetris.html"])
    parser.add_argument("--output", type=Path, default=Path("artifacts/fileio-live-check.json"))
    options = parser.parse_args()
    asyncio.run(main(options.files, options.output))
