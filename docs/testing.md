# 검증

```powershell
uv sync --locked
uv run --frozen pytest -q
uv run --frozen python scripts/smoke.py "Python 공식 asyncio 문서" --max-results 3
```

단위·계약 테스트는 계정 사용량을 소모하지 않는다. 마지막 smoke 명령은 실제 CLI 웹 검색을 수행하므로 로그인과 계정 사용량이 필요하다.

- 공개 도구가 `websearch` 하나인지 stdio 연결에서 확인.
- 입력·출력 JSON Schema와 런타임 모델 일치 확인.
- 성공·빈 결과·입력 오류·CLI 오류 모두 같은 필드와 `structuredContent`/텍스트 JSON 일치 확인.
- 잘못된 JSON, 누락·추가 필드, URL·게시일 오류, 검색 미실행·turn 미완료 거부.
- 모델·추론 강도 고정, 검색어의 UTF-8 stdin 전달, 사용자 설정 무시 확인.
- 실제 subprocess를 이용한 시간 제한·출력 상한·취소와 다음 요청 처리 확인.
- smoke는 실제 stdio에서 잘못된 인자와 실제 검색을 차례로 호출하고 독립 JSON Schema 검증을 수행. 결과는 `artifacts/live-smoke.json`에 저장하며 `--output`으로 변경 가능.

모의 CLI 테스트의 통과는 실서비스 검색 품질의 보증이 아니다. 실제 CLI·MCP 실행 기록과 테스트 결과를 구분한다.

## 2026-09-28 실행 결과

- Windows / Python 3.13.15 / Codex CLI 0.155.0.
- `uv run --frozen pytest -q -W error`: **45 passed in 6.81s**, 경고 없음.
- `uv run --frozen python scripts/smoke.py --output artifacts/live-final-smoke.json`: exit 0. 실제 stdio 연결, 입력 오류 응답 검증, `gpt-6-luna` / `low` 검색 결과 3개와 공개 출력 스키마 검증 성공. 초기화와 입력 오류 호출을 포함한 전체 시간 19.359초.
- `uv lock --check`: exit 0.

로컬 실제 응답: [live-final-smoke.json](../artifacts/live-final-smoke.json). `artifacts/`는 버전 관리 대상이 아니다.
