# 카페 문서 ID 분류 구현 계획

> **For agentic workers:** 노트북 담당 worker와 본체가 파일 경계를 나누어 실행한다.

**Goal:** 모델이 필요한 카페 문서 ID를 고르고 Python이 선택 원문을 읽도록 바꾼다.

**Architecture:** 고정 문서 카탈로그 → Jev의 문서별 Choice 분류 → 선택 파일 읽기 → 기존 근거 답변.

**Tech Stack:** 기존 Python, TypeSafe SDK의 Jev, Pydantic, OpenAI Responses, unittest.

**Spec:** `docs/superpowers/specs/2026-10-28-cafe-document-selection-design.md`

## Global Constraints

- 원본 자료와 사용자 변경을 보존한다. 의존성 추가·commit·push는 하지 않는다.
- 노트북의 한국어 함수 설명과 단계 주석, 직접 호출 예제를 유지한다.

## Review Focus

- 미등록 ID는 허용하지 않으며 모델이 경로를 만들지 않는다.
- 선택 전에는 문서 본문을 모델에 전달하지 않는다.
- 복합 질문의 여러 문서와 중복 ID를 처리한다.
- 문서 없음과 질문 모호함을 구분한다.
- 후속 문맥과 실제 출처 제한을 유지한다.

### Task 1: 노트북과 테스트 — consultation_notebook 담당

**Files:** `notebooks/05_카페정보문의.ipynb`, `tests/test_consultation_notebook.py`

**Interfaces:** `CAFE_DOCUMENTS`의 고정 ID/파일/제목/설명, `ConsultationQuery.document_ids`, `ConsultationState.document_ids`, `search_cafe_information(document_ids)`.

- [x] 행동 테스트를 변경하고 실패를 확인한다.
- [x] 동의어 매칭을 ID 선택 파일 읽기로 교체하고 예제를 갱신한다.
- [x] 관련 unittest를 통과시킨다.

### Task 2: 프롬프트와 통합 검증 — Codex 본체 담당

**Files:** `prompts/consultation_query.md`, 이 설계와 계획.

- [x] 프롬프트에 카탈로그 기반 다중 ID 선택과 자료 없음 처리를 명시한다.
- [x] 담당 결과의 코드와 민감 파일 포함 여부를 검토한다.
- [x] `uv run python -m unittest discover -s tests -v`와 노트북 문법을 확인한다.
- [x] 실제 모델 호출 여부와 검증 한계를 구분해 보고한다.

## 검증 결과

- 담당자가 테스트 실패를 먼저 확인한 뒤 구현했으며 본체 전체 unittest 117개 통과. 별도 reviewer 관련 12개 통과와 코드 검토 완료.
- 노트북 25개 셀의 Python 구문 확인, 저장 출력 없음 및 선택 원문/출처 제한 검사 통과. 원본 자료와 민감 파일은 수정하지 않았다.
- 실제 API 검증은 최초 자동 승인 검토에서 외부 전송 명시 승인 부족으로 거절됐으며, 사용자가 실제 API 검증을 명시 승인한 뒤 재실행했다. Jev와 gpt-5-nano로 예시 질문 3개 검증 완료: 주차·반려동물 복합 문의는 hours_location/usage를 선택해 원문 조건대로 답변, 예약·유아용 의자는 usage를 읽고 정보 없음을 안내, 대상 없는 후속 질문은 문서 선택 없이 확인 질문을 반환했다.
- 첫 답변의 used_sources에는 같은 출처가 중복됐으나 조회한 문서 범위 안이었다. Jupyter 화면 및 노트북 전체 셀 실행은 하지 않았다.
