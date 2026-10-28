# 고객정보 기반 상품추천 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고객 ID로 조회한 프로필을 State에 담고, 고객 조건 필터·주문 인기 집계 도구를 모델이 선택하는 03 노트북을 만든다.

**Architecture:** 서버 State에 허용한 고객정보만 조회해 담는다. 노트북에는 필요한 스키마와 짧은 함수를 직접 정의하고, 도구 직접 실행과 실제 Responses function calling 연결을 차례로 보여준다.

**Tech Stack:** Python 3.12, uv, Pydantic, OpenAI Responses, Jupyter, unittest.

**Spec:** `docs/superpowers/specs/2026-10-28-product-recommendation-design.md`

## Global Constraints

- 기존 미커밋 파일 보존. commit·push·새 패키지·고객 원본 수정 금지.
- 함수에 한국어 docstring과 함수별 연속 번호의 처리 단계 주석을 작성한다.
- 노트북에 assert, %run, sys.path 변경, cwd 자동 변경, 외부 스키마 import를 넣지 않는다.
- 프롬프트는 `.md` 파일에 저장한다. 외부 모델 실행과 대체 응답 테스트를 구분한다.
- 개인정보를 출력에 저장하지 않으며 고객의 미확인 알레르기·선호를 만들어내지 않는다.

## Review Focus

- 다른 고객의 프로필/조건이 재사용되지 않는가: Task 1에서 고객 전환 검증.
- 누락/null/[]가 서로 구분되는가: Task 1·2에서 프로필과 추천 초기화 검증.
- 도구 인자로 기존 알레르기를 우회하지 않는가: Task 2에서 저장 알레르기 유지 검증.
- 인기 순위에 조건 미확인·판매 불가 메뉴가 추천되지 않는가: Task 2에서 후보 제한과 수량 집계 검증.
- 모델 출력의 함수 호출을 실제 실행하고 결과를 다시 전달하는가: Task 2에서 대체 응답으로 왕복과 반복 상한 검증.

### Task 1: 고객 프로필 State 연결 — 담당 customer_state worker

**Files:** `schemas/session_state.py`, `common/customer_store.py`, `services/intent_classifier.py`, `services/product_order.py`, `tests/test_customer_profile.py`.

**Interfaces:** `CustomerProfile(customer_id, name, birth_year, membership_level, allergies, preferences)` 모두 실제 의미 description 작성. `SessionState.customer: CustomerProfile | None = None`. `load_customer_profile(customer_id)`는 허용 필드만 가져오고 없는 ID는 None. `prepare_customer_state(state)`는 원본을 복사해 프로필을 조회하고 첫 추천 조건을 초기화한다. 고객 불일치 시 추천 조건 초기화. 서버 모델 입력에서는 customer를 제외한다.

- [x] 테스트를 먼저 작성하고 `uv run python -m unittest tests.test_customer_profile -v`로 미구현 실패를 확인한다.
- [x] 프로필 조회·상태 준비를 구현하고 두 서비스의 복사 직후 연결한다. 데이터 경로는 테스트에서 patch 가능하게 둔다.
- [x] 같은 명령과 기존 API/State 관련 검증으로 회귀를 확인한다.

### Task 2: 03 노트북과 도구 — 담당 recommendation_notebook worker

**Files:** `notebooks/03_상품추천.ipynb`, `prompts/recommendation_tools.md`, `tests/test_recommendation_notebook.py`.

**Interfaces:** 노트북 내부 최소 `CustomerProfile`, `CustomerInput`, `RecommendationState`, `HistoryMessage`, `SessionState`를 정의한다. `load_customer(state)`, `filter_menu(state, allergies=None, preferences=None)`, `analyze_popular_menu(state, limit=3, start_date=None, end_date=None, personalized=False)`, `run_product_recommendation(state)`를 제공한다. 도구 인자의 null은 기존 값 유지, []는 세션 조건 없음이며 저장 고객 알레르기는 항상 유지한다. 필터와 개인 인기 추천은 미확인 항목 질문을 반환한다. 인기 집계 결과는 기간과 수량 기준을 포함한다.

- [x] 노트북 함수 정의를 AST로 읽어 독립 실행하는 행동 테스트부터 작성하고 미구현 실패를 확인한다. 테스트용 루트 경로 처리는 테스트 파일에서만 한다.
- [x] 자료 로드→고객 조회→두 함수 직접 실행→도구 정의→함수명/인자/결과/답변 확인→전체 연결→후속 대화 순으로 노트북을 작성한다. 모델 원본 주문 대신 집계 결과만 전달한다.
- [x] 대체 응답으로 실제 Python 필터/집계 실행, function_call_output call_id, 후속 호출, 고객 조건 유지·수정·미확인, 후보 없음, 날짜 범위를 검증한다.
- [x] 실제 모델 호출 예제는 명시적인 실행 셀로 제공하고, 실행하지 못하면 보고한다. 고객·주문 파일을 수정하지 않는다.

### Task 3: 통합 검증 — 담당 Codex 본체와 읽기 전용 reviewer

- [x] 두 작업 결과를 읽고 스키마 이름·필드와 노트북 규칙을 대조한다.
- [x] `uv run python -m unittest discover -s tests -v`를 실행해 전체 결과를 확인한다.
- [x] 노트북 JSON·코드 문법, 셀 순서, 함수 설명·주석, 금지 코드, 민감 출력 포함 여부를 확인한다.
- [x] 읽기 전용 검토 결과를 반영하고 필요한 검증을 다시 실행한다. 실제 모델 실행 여부를 구분해 최종 보고한다.

## 실행 기록

- 변경 전 기준: 전체 unittest 85개 통과.
- Task 1: 신규 9개 테스트 실패→통과, 구현 후 전체 94개 통과. 별도 읽기 전용 리뷰에서 관련 65개 통과와 요구사항 충족 확인.
- 결정: 사용자가 고객정보 기반으로 진행하도록 지시했으므로 수정된 설계와 본 계획을 같은 세션에서 실행한다.
- 결정: 프로젝트 전체가 미커밋 상태여서 git 상태를 바꾸지 않고 현재 작업공간에서 파일 소유권을 나누어 진행한다. commit·push는 하지 않는다.
- 결정: 고객 원본에는 알레르기·선호를 새로 만들어 넣지 않고 누락된 값만 질문으로 확인한다.
- Task 2·3: 전체 unittest 105개 통과, nbformat·36셀 문법·7함수 주석·빈 출력 확인. 검토에서 발견한 알레르기 별칭/미지원 값 처리 결함을 테스트 실패→수정→통과로 보완하고 재검토 승인.
- 실제 gpt-5-nano 확인: 일반 인기 질문은 analyze_popular_menu, 우유 알레르기와 인기 결합 질문은 filter_menu 이후 analyze_popular_menu 호출. 두 요청 모두 실제 JSON 집계 근거로 답변. 수량을 건수로 표현하지 않도록 후속 프롬프트 보완.
