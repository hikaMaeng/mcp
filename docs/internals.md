# CLI 계약

`runner.build_args()`가 고정하는 핵심 옵션:

```text
codex exec --model gpt-6-luna -c model_reasoning_effort="low"
  -c web_search="live" --json --output-schema <temporary-schema> -
  --ignore-user-config --ignore-rules --ephemeral --skip-git-repo-check
  --sandbox read-only -c approval_policy="never" -c project_doc_max_bytes=0
  --disable shell_tool --disable multi_agent --disable apps --color never
```

검색 프롬프트는 [build_prompt](../src/websearch/runner.py)에 고정한다. 검색어는 UTF-8 stdin으로 보내고 `shell=True`를 사용하지 않는다. 글로벌 CLI 설정 상속을 끊어 자기 MCP 서버의 재귀 실행과 모델 변경을 막는다.

- 요청마다 고유 임시 폴더와 스키마를 만들고 종료 시 정리한다.
- stdout JSONL 중 완료된 `web_search`와 검색어, 마지막 `agent_message`, `turn.completed`를 확인한다. 페이지 열기만으로 검색 성공을 인정하지 않는다.
- stdout은 4 MiB, stderr는 512 KiB까지 읽는다. CLI 진단 출력은 MCP stdout으로 전달하지 않는다.
- 시간 초과·취소 시 Windows는 `taskkill /T`, POSIX는 별도 프로세스 그룹 종료를 사용한다. 출력 파이프도 끝까지 닫는다.
- 요청별 검색 결과를 기본적으로 저장하지 않는다. `scripts/smoke.py`는 검증 목적으로 `artifacts/`에 저장한다.

JSON Schema의 원본은 Pydantic 모델이다. `uv run --frozen python scripts/export_schemas.py`로 게시 파일을 갱신하고, 테스트로 원본과의 일치를 검사한다.

근거: [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference), [공식 MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).

재사용 조회: `npm search codex mcp --registry=https://verdaccio.neurondev.net/`는 2026-09-28 TLS `ERR_SSL_TLSV1_UNRECOGNIZED_NAME`으로 실패했다. 내부 패키지의 적합성은 확인하지 못했으며 공식 MCP SDK를 채택했다. vendor 대상이나 파생 버전은 없다.
