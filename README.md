웹 검색(`websearch`)과 파일시스템(`fileiomcp`)을 제공하는 독립 stdio MCP 서버 프로젝트.

| Goal | File |
|---|---|
| Understand purpose | [Overview](docs/overview.md) |
| API reference | [API](docs/api.md) |
| Constraints | [Constraints](docs/constraints.md) |
| Testing | [Testing](docs/testing.md) |
| Run and connect | [Usage](docs/usage.md) |
| Separate filesystem MCP | [File I/O MCP](docs/file-io-mcp.md) |
| Architecture | [Architecture](docs/architecture.md) |
| CLI internals | [Internals](docs/internals.md) |

모델은 **`gpt-6-luna`**, 추론 강도는 **`low`**로 고정됩니다.

```powershell
codex login
uv sync --locked
uv run --frozen websearch
```

The filesystem tool server is an independent stdio process and command:

```powershell
uv sync --locked
uv run --frozen fileiomcp
```

웹 검색 서버 제공 도구: `websearch(query, max_results=5)`. 파일 I/O 서버 도구 및 연결 방법은 [File I/O MCP](docs/file-io-mcp.md)를 참고하세요. 두 서버 모두 표준 출력은 MCP 통신 전용입니다.
