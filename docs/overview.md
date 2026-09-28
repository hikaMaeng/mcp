# 목적

인증된 로컬 Codex CLI를 웹 검색 백엔드로 사용하는 MCP 서버다. 공개 도구는 `websearch` 하나이고 전송 방식은 stdio다.

- 모델: `gpt-6-luna`, reasoning effort: `low`, 변경 옵션 없음.
- 입력: `query`, `max_results`.
- 출력: 버전이 있는 JSON 계약. 성공과 도구 실행 오류 모두 동일한 필드.
- API 키를 별도로 저장하지 않고 Codex CLI의 로그인 상태를 이용한다.
- 검색엔진 원시 응답이나 전체 검색 건수가 아니라, Codex가 검색 자료에서 선별·정리한 출처 목록이다.

반환 계약은 [API](api.md), 보증 범위는 [Constraints](constraints.md)를 따른다.
