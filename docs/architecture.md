# 구성

```text
MCP client ← stdio JSON-RPC → server.py
                                ↓ 입력 검증
                             runner.py
                                ↓ stdin에 검색 프롬프트
                     codex exec --json --output-schema
                     gpt-6-luna / low / web_search=live
                                ↓ 검색 이벤트 + 최종 JSON
                             models.py 검증
                                ↓ URL 정규화·중복 제거·순위 부여
                     응답 재검증 → structuredContent + content
```

`server.py`가 API 계약과 오류 변환을 소유한다. `runner.py`는 실행·취소·시간 제한·이벤트 검증을 소유한다. `models.py`가 런타임 검증과 공개 JSON Schema의 단일 원본이다.

오류 분류를 일정하게 유지하기 위해 SDK low-level server에서 `tools/call` 인자를 직접 검증한다. `tools/list`에는 단일 도구와 입력·출력 스키마만 등록한다.
