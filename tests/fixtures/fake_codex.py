"""A subprocess fixture: validates the real CLI arguments and emits JSONL."""

import json
import sys
from pathlib import Path

assert sys.argv[1] == "exec"
assert sys.argv[sys.argv.index("--model") + 1] == "gpt-6-luna"
assert 'model_reasoning_effort="low"' in sys.argv
assert 'web_search="live"' in sys.argv
assert "--ignore-user-config" in sys.argv
schema = Path(sys.argv[sys.argv.index("--output-schema") + 1])
assert json.loads(schema.read_text(encoding="utf-8"))["additionalProperties"] is False
prompt = sys.stdin.buffer.read().decode("utf-8")
request = json.loads(prompt.split("Search request JSON:\n", 1)[1])
assert request["query"]
print("mock diagnostic on stderr", file=sys.stderr)

for event in [
    {"type": "item.completed", "item": {"type": "web_search", "query": request["query"]}},
    {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps({"results": [
        {"title": "Python", "url": "https://www.python.org/", "snippet": "Official Python website", "published_at": None},
    ]})}},
    {"type": "turn.completed", "usage": {}},
]:
    print(json.dumps(event))
