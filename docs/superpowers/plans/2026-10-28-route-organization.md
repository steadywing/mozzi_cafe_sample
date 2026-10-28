# 라우터와 경로 정리 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 화면과 API의 URL과 파일 책임을 현재 처리 흐름에 맞게 일관되게 정리합니다.

**Architecture:** 화면 GET은 `routers/test_pages.py`에 명시적으로 모으고, 기능 라우터는 `/chatbot/...` 처리만 제공합니다. 샘플 자료 GET은 `routers/test_samples.py`가 맡습니다. `/test/...`는 HTML, `/chatbot/...`는 챗봇 처리, `/test/api/...`는 테스트 자료·실행 기록으로 구분합니다. 공개 경로와 라우터 파일 이름에서 `notebook`을 빼고, 두 주문 흐름은 각각 유지합니다.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, vanilla JavaScript, unittest

**Spec:** `docs/superpowers/specs/2026-10-28-route-organization-design.md`

## Global Constraints

- `AGENTS.md`의 쉬운 한국어 docstring·단계 주석 규칙을 따릅니다.
- 서비스 함수, 모델 프롬프트, 저장 형식과 외부 모델 호출 방식은 바꾸지 않습니다.
- 이전 경로 별칭은 두지 않습니다. 요청 없는 commit·push는 하지 않습니다.
- 실제 모델 API는 호출하지 않습니다.

## Review Focus

- `/test/consultation`과 `/test/points`가 포괄 경로 제거 후에도 열리는지 확인합니다.
- 두 주문 화면과 API가 각각 다른 처리 함수를 호출하는지 확인합니다.
- `/test/api/search/images/{sample}`와 포인트 샘플 이미지가 정상 응답하는지 확인합니다.
- 공통 실습 기록 JS가 새 trace 경로에서 조회·삭제하는지 확인합니다.
- 이전 URL이 OpenAPI와 화면 링크에 남지 않았는지 확인합니다.

---

### Task 1: 경로 계약 테스트

**Files:** `tests/test_route_map.py`

- [x] 새 화면·API 경로와 이전 경로 부재를 확인하는 테스트를 작성합니다.
- [x] 테스트가 기존 코드에서 의도대로 실패하는지 확인합니다.

### Task 2: 백엔드 경로와 화면 라우터

**Files:** `main.py`, `routers/test_pages.py`, `routers/test_samples.py`, `routers/testboard.py`, `routers/history.py`, `routers/intent_classifier.py`, `routers/product_order.py` → `routers/order.py`, `routers/notebook_*.py` → 이름을 바꾼 기능 라우터, `tests/test_*.py`

- [x] 화면 GET을 `test_pages.py`로 옮기고 포괄 경로를 제거합니다.
- [x] 챗봇 처리에는 `/chatbot/...`, 테스트 자료에는 `/test/api/...` 접두어를 적용합니다.
- [x] 기존 API 테스트의 요청 경로를 갱신하고 반환 형식·처리 검증을 유지합니다.
- [x] 관련 Python 테스트를 실행합니다.

### Task 3: 화면 호출과 경로 설명

**Files:** `templates/*.html`, `static/js/*.js`, `tests/frontend/*.cjs`, `README.md`, `docs/폴더-구조.md`, `static/diagrams/service-flow.svg`

- [x] 내비게이션, `fetch()` 호출, 화면에 표시되는 경로를 새 주소로 바꿉니다.
- [x] 두 주문 화면을 명확히 구분하고 구조 문서·SVG의 주소를 갱신합니다.
- [x] 프런트엔드 테스트와 정적 경로 검사를 실행합니다.

### Task 4: 통합 검증

**Files:** 변경 없음

- [x] 전체 Python·프런트엔드 테스트를 실행합니다.
- [x] TestClient로 모든 화면 GET과 주요 예시 자료 경로를 확인합니다.
- [x] 실제 브라우저에서 내비게이션과 서비스 SVG를 확인합니다.
- [x] 최종 변경 파일과 민감 파일 포함 여부를 확인합니다.
