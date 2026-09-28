# websearch v1.0

```json
{"query":"Python 공식 asyncio 문서","max_results":3}
```

| 입력 | 제약 |
|---|---|
| `query` | 필수 문자열, 1~2000자, 앞뒤 공백 제거, 공백만 있는 값 금지 |
| `max_results` | 정수 1~10, 기본값 5, 문자열·불리언의 숫자 변환 금지 |

추가 인자는 거부한다. `model`과 `reasoning_effort` 인자는 없다.

성공 예시:

```json
{
  "schema_version":"1.0",
  "status":"ok",
  "query":"Python 공식 asyncio 문서",
  "provider":"codex-cli",
  "model":"gpt-6-luna",
  "reasoning_effort":"low",
  "searched_at":"2026-09-28T08:00:00Z",
  "search_queries":["Python 공식 asyncio 문서"],
  "results":[{
    "title":"asyncio documentation",
    "url":"https://docs.python.org/3/library/asyncio.html",
    "snippet":"Python의 비동기 I/O 라이브러리 공식 문서입니다.",
    "published_at":null,
    "rank":1
  }],
  "count":1,
  "error":null
}
```

실패해도 모든 최상위 필드를 유지한다. `status="error"`, `searched_at=null`, `search_queries=[]`, `results=[]`, `count=0`, `error={"code":"TIMEOUT","message":"..."}`가 된다. 입력 검증 실패 시 `query=null`, 다른 실행 오류에는 정규화된 입력 검색어를 보존한다.

- `structuredContent`가 정규화 JSON이다. `content[0].text`도 같은 객체를 JSON 문자열로 직렬화한다.
- 성공은 `isError=false`, 도구 실패는 `isError=true`다.
- `count`는 반환된 결과 수다. 전체 검색 건수나 검색엔진 추정치는 제공하지 않는다.
- `rank`는 1부터 연속하며 URL은 중복되지 않는다. HTTP(S) URL만 허용하고 호스트 대소문자·기본 포트·fragment를 정규화한다. 쿼리 파라미터와 경로는 보존한다.
- `snippet`은 모델이 검색 자료를 바탕으로 작성한 요약이다.
- `published_at`은 `YYYY-MM-DD` 또는 `null`이다. 검색일·수집일을 게시일로 대체하지 않는다.
- 실제 검색 후 결과가 없으면 `status="ok"`, `results=[]`다. 검색을 실행하지 않았으면 실패다.

| error.code | 의미 |
|---|---|
| `INVALID_ARGUMENT` | 필수 입력 누락, 잘못된 형식·범위, 추가 인자 |
| `CODEX_NOT_FOUND` | CLI 또는 실행 가능한 npm shim을 찾을 수 없음 |
| `CODEX_START_FAILED` | CLI 프로세스 실행 실패 |
| `CODEX_FAILED` | CLI 비정상 종료 또는 turn.failed |
| `TIMEOUT` | 대기열 시간을 포함한 검색 제한 시간 초과 |
| `OUTPUT_TOO_LARGE` | stdout 4 MiB 또는 stderr 512 KiB 초과 |
| `INCOMPLETE_RESPONSE` | 완료된 turn 이벤트 없음 |
| `SEARCH_NOT_PERFORMED` | 완료된 검색 이벤트와 검색어 없음 |
| `INVALID_RESPONSE` | CLI 이벤트 또는 최종 JSON의 형식·값 오류 |
| `INTERNAL_ERROR` | 예상하지 못한 내부 오류, 상세는 stderr |

스키마: [입력](../schemas/websearch.input.schema.json), [공개 출력](../schemas/websearch.output.schema.json), [Codex 출력](../schemas/codex.output.schema.json).

필드 제거·타입 변경은 `schema_version` 변경을 요구한다. 소비자는 `error.message` 문자열 대신 `error.code`로 분기한다.
