# 실행

Python 3.11+, uv, PATH에 있는 Codex CLI와 `codex login`이 필요하다.

```powershell
cd F:\dev\codexmcp
codex login status
uv sync --locked
uv run --frozen websearch
```

마지막 명령은 stdio MCP 서버로 대기한다. 직접 검색 결과를 보려면 `uv run --frozen python scripts/smoke.py "검색어"`를 사용한다.

## MCP 클라이언트 연결

JSON 설정 예시는 [mcp.json](../examples/mcp.json), Codex 설정 예시는 [codex.config.toml](../examples/codex.config.toml)에 있다. 프로젝트 위치에 맞춰 절대 경로를 변경한다.

```json
{
  "mcpServers": {
    "websearch": {
      "command": "uv",
      "args": ["run", "--frozen", "--directory", "F:/dev/codexmcp", "websearch"]
    }
  }
}
```

GUI 클라이언트가 PATH를 찾지 못하면 `command`를 uv 실행 파일의 절대 경로로 지정한다. 또는 `uv sync --locked` 실행 후 `F:/dev/codexmcp/.venv/Scripts/python.exe`와 `args: ["-m", "websearch"]`를 사용한다.

클라이언트 도구 시간 제한은 서버 제한보다 길게 설정한다. 기본 서버 제한은 180초, 클라이언트 권장값은 210초다.

| 환경변수 | 기본값 | 범위/용도 |
|---|---|---|
| `CODEX_MCP_CODEX_BIN` | `codex` | Codex 실행 파일 경로 또는 PATH 이름 |
| `CODEX_MCP_TIMEOUT_SECONDS` | `180` | 대기열 포함 1~600초 |
| `CODEX_MCP_MAX_CONCURRENCY` | `2` | 서버 프로세스당 동시 CLI 1~8개 |

모델과 추론 강도를 바꾸는 설정은 없다. 호출 인자로 넘기면 `INVALID_ARGUMENT`이다.

Windows npm의 `codex.cmd` / `codex.ps1`은 인접한 공식 `codex.js`를 Node로 직접 실행한다. 임의 `.cmd` 래퍼는 지원하지 않는다. 비표준 설치는 실제 `codex.exe` 경로를 지정한다.
