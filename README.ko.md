Codex CLI 웹검색과 파일시스템 작업을 제공하는 독립 로컬 stdio MCP 서버 두 개입니다.

# Web Search & Filesystem MCP

[English](README.md) | [한국어](README.ko.md)

필요한 서버만 등록하거나 두 서버를 각각 별도의 프로세스로 연결할 수 있습니다.

| 서버 | 제공 기능 | Codex CLI 로그인 |
| --- | --- | --- |
| `websearch` | 출처 URL과 구조화된 요약을 포함하는 실시간 웹검색 | 필요 |
| `fileiomcp` | 파일·폴더 생성, 읽기, 수정, 삭제, 이동, 복사 | 불필요 |

## 사전 준비

- Python **3.11 이상**, [uv](https://docs.astral.sh/uv/getting-started/installation/), Git.
- LM Studio 등 **stdio** 서버 실행을 지원하는 MCP 클라이언트.
- 웹검색: 로컬 [Codex CLI](https://developers.openai.com/codex/cli)가 설치되어 있고, **MCP 클라이언트를 실행하는 OS 사용자로 CLI 로그인이 완료되어 있어야 합니다.**

웹검색은 로컬 CLI의 인증 정보와 계정 사용량을 사용합니다. 서버가 대화형 로그인을 수행하거나 도구 인자로 인증 정보를 받지는 않습니다. 계정에서 `gpt-6-luna`와 실시간 웹검색을 사용할 수 있어야 합니다. 구현의 모델은 **`gpt-6-luna`**, 추론 강도는 **`low`**로 고정됩니다.

파일시스템 서버에는 Codex CLI나 OpenAI 계정이 필요하지 않습니다.

## 빠른 시작

### 1. 설치

```sh
git clone https://github.com/hikaMaeng/mcp.git
cd mcp
uv sync --locked
```

클라이언트가 이 위치에서 실행하므로 저장소와 `.venv`를 유지하세요.

### 2. Codex CLI 인증 — 웹검색만 해당

CLI는 [공식 설치 안내](https://developers.openai.com/codex/cli)를 따릅니다. npm 설치에는 Node.js가 필요합니다.

```sh
npm install -g @openai/codex
codex --version
codex login
codex login status
```

이미 로그인했다면 `codex login status`로 확인하고 진행하세요. **CLI 인증 상태**를 확인해야 하며, MCP 프로세스가 같은 사용자의 인증 정보와 실행 파일에 접근할 수 있어야 합니다.

### 3. MCP 클라이언트 설정

기존 `mcp.json`의 **`mcpServers` 객체 안에** 아래 항목을 추가하세요. 다른 서버를 유지하고 `mcpServers` 키를 중복 생성하지 마세요. 한 서버만 필요하면 다른 항목을 생략할 수 있습니다.

`C:/path/to/mcp`를 **실제 저장소 절대 경로**로 바꾸세요. Windows에서는 가상환경 Python을 직접 실행하면 GUI가 `uv`를 찾을 필요가 없습니다.

```json
{
  "mcpServers": {
    "websearch": {
      "command": "C:/path/to/mcp/.venv/Scripts/python.exe",
      "args": ["-m", "websearch"]
    },
    "fileiomcp": {
      "command": "C:/path/to/mcp/.venv/Scripts/python.exe",
      "args": ["-m", "fileiomcp"]
    }
  }
}
```

macOS/Linux에서는 두 `command`를 `/absolute/path/to/mcp/.venv/bin/python`으로 바꾸고 `args`는 유지하세요. Windows JSON 경로는 `/`를 사용하거나 역슬래시를 `\\`로 이스케이프해야 합니다.

`uv`를 통해 실행하는 설정도 가능합니다.

```json
{
  "mcpServers": {
    "websearch": {
      "command": "uv",
      "args": ["run", "--frozen", "--directory", "/absolute/path/to/mcp", "websearch"]
    },
    "fileiomcp": {
      "command": "uv",
      "args": ["run", "--frozen", "--directory", "/absolute/path/to/mcp", "fileiomcp"]
    }
  }
}
```

저장소 경로를 교체하세요. GUI가 `uv`를 찾지 못하면 실행 파일 절대 경로를 지정하거나 앞의 Python 직접 실행 설정을 사용하세요. 다른 설정 형식의 클라이언트는 해당 형식에 맞춰 `command`, `args`, `env`를 넣어야 합니다.

### LM Studio

MCP 설정 편집기를 열어 위 항목을 추가하세요. 이 Windows 설치에서는 `%USERPROFILE%/.lmstudio/mcp.json`에 있습니다. 저장 후 통합을 다시 연결·활성화하여 서버 정의를 불러오세요.

터미널에서는 Codex가 실행되지만 GUI가 찾지 못하면 **websearch** 항목에 실제 CLI 경로를 지정하는 `env`를 추가하세요.

```json
"env": {
  "CODEX_MCP_CODEX_BIN": "C:/absolute/path/to/codex.exe"
}
```

표준 Windows npm 설치의 `codex.cmd`도 지원합니다. 인접한 공식 `node_modules/@openai/codex/bin/codex.js`와 Node.js가 있어야 하며 임의 `.cmd` 래퍼는 지원하지 않습니다.

두 서버의 stdout은 MCP 통신 전용입니다. `uv run --frozen websearch` 또는 `uv run --frozen fileiomcp`를 직접 실행하면 stdin으로 클라이언트를 기다립니다. 대화형 명령 프롬프트나 HTTP 서비스가 아닙니다.

## 도구

### 웹검색

`websearch` 호출 예:

```json
{"query": "Python asyncio 공식 문서", "max_results": 3}
```

`query`는 공백만 있는 값을 제외한 1~2,000자 문자열입니다. `max_results`는 1~10 정수이며 기본값은 5입니다. 버전이 명시된 성공·오류 응답에 `title`, `url`, `snippet`, `published_at`, `rank`가 포함됩니다. 요약은 검색 자료를 바탕으로 모델이 작성하며, 알 수 없는 게시일은 `null`입니다. 모델·추론 설정은 인자로 받을 수 없습니다.

### 파일시스템

| 도구 | 작업 |
| --- | --- |
| `directory_create`, `directory_delete` | 폴더 생성, 빈 폴더 또는 트리 삭제 |
| `directory_move`, `directory_copy` | 폴더 트리 이동·복사 |
| `file_create`, `file_append`, `file_delete` | 텍스트 생성·교체, 청크 추가, 파일 삭제 |
| `file_read` | 줄 번호와 SHA-256을 포함한 읽기 |
| `file_move`, `file_copy` | 파일 이동·복사 |
| `file_edit_lines` | 줄 범위 삭제·교체 또는 특정 줄 뒤 삽입 |

줄 번호는 **1부터 시작하며 범위의 양 끝을 포함**합니다. 2~3줄 교체 예:

```json
{"path": "C:/work/example.txt", "operation": "replace", "start_line": 2, "end_line": 3, "lines": ["새 2줄", "새 3줄"]}
```

삭제는 `operation: "delete"`를 사용하고 `lines`를 생략합니다. 삽입은 `operation: "insert_after"`, `start_line`, `lines`를 사용하며 줄 `0`은 파일 맨 앞을 뜻합니다. `lines`의 각 항목에는 개행 문자가 없어야 합니다.

기존 대상 교체에는 `overwrite: true`가 필요합니다. 내용이 같은 `file_create` 재시도는 허용합니다. 교체 전에 기존 파일을 읽으세요. 문서·코드는 `content`를 생략해 빈 파일을 만든 뒤 `file_append`로 한 번에 약 800자 이하씩 순서대로 작성하세요. 응답당 호출 하나를 생성하고 결과를 받은 뒤 다음 호출을 진행합니다. 이는 지침이며 스키마 길이 제한은 아닙니다. 연결 실패 시 이전 청크가 이미 기록됐을 수 있으므로 실제 파일을 읽고 재시도해야 합니다.

**접근 범위는 OS 권한을 따르며 별도의 허용 폴더 샌드박스 설정은 없습니다.** 절대 경로를 사용하세요. 재귀 삭제는 선택한 트리를 영구 삭제합니다. 심볼릭 링크를 통한 쓰기는 거부되며, 배타적 생성에는 NTFS 같은 하드링크 지원이 필요합니다. 상세 동작은 [File I/O MCP](docs/file-io-mcp.md)를 참고하세요.

## 웹검색 환경변수

websearch 항목의 `env`에 설정합니다. 호환성을 위해 기존 `CODEX_MCP_` 접두사는 유지합니다.

| 변수 | 기본값 | 용도 |
| --- | --- | --- |
| `CODEX_MCP_CODEX_BIN` | `codex` | CLI 실행 파일 이름 또는 절대 경로 |
| `CODEX_MCP_TIMEOUT_SECONDS` | `180` | 대기열 포함 제한 시간, 1~600초 |
| `CODEX_MCP_MAX_CONCURRENCY` | `2` | 서버당 동시 CLI 프로세스 수, 1~8 |

클라이언트 도구 제한 시간은 서버보다 길게 설정하세요. 기본 서버 180초라면 클라이언트는 210초 등이 가능합니다. 검색마다 임시 작업 폴더에서 Codex를 실행하며 읽기 전용 샌드박스와 실시간 웹검색을 사용합니다. 셸·앱·에이전트 도구는 비활성화하고 사용자 설정과 저장소 규칙은 검색 실행에서 제외합니다.

## 문제 해결

| 증상 | 확인 사항 |
| --- | --- |
| 서버 시작 실패 | `uv sync --locked` 실행 여부와 실행 파일 절대 경로 |
| `CODEX_NOT_FOUND` | CLI 설치 또는 `CODEX_MCP_CODEX_BIN`; GUI와 터미널 PATH 차이 |
| `CODEX_FAILED` | CLI 로그인, 모델 접근 권한, 네트워크, 계정 한도 |
| `TIMEOUT` | 서버·클라이언트 제한 시간과 동시 요청 |
| JSON 문자열 미종결 / 도구 호출 생성 실패 | 클라이언트 출력 토큰 상한 증가 또는 작은 청크 사용; 완전한 호출이 서버에 도착하지 않은 상태 |
| `WebSocket closed by the client` | 클라이언트 로그와 통합 연결 상태; 이 메시지만으로 파일시스템 오류 원인을 특정할 수 없음 |
| 파일이 이미 존재함 | 먼저 읽고 의도한 교체일 때만 `overwrite: true` 지정 |

## 상세 문서

| 주제 | 문서 |
| --- | --- |
| 목적 | [개요](docs/overview.md) |
| 도구 계약 | [API](docs/api.md) |
| 연결 | [사용법](docs/usage.md) · [MCP JSON 예제](examples/mcp.json) |
| 파일시스템 동작 | [File I/O MCP](docs/file-io-mcp.md) |
| 제한 | [제약](docs/constraints.md) |
| 설계 | [아키텍처](docs/architecture.md) · [CLI 내부 동작](docs/internals.md) |
| 개발 확인 | [테스트](docs/testing.md) |
