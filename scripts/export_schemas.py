"""Export the same schemas used by the runtime and tools/list."""

import json
from pathlib import Path

from websearch.models import RawResponse, SearchRequest, SearchResponse


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "schemas"
    destination.mkdir(exist_ok=True)
    for name, model in [
        ("websearch.input", SearchRequest),
        ("websearch.output", SearchResponse),
        ("codex.output", RawResponse),
    ]:
        (destination / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
