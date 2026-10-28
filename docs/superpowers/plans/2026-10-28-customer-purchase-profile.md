# 고객 잔액·구매 통계 프로필 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 적립금과 현재 스탬프, 저장 주문 기반 구매 통계를 고객 State에 담고 추천에 활용한다.

**Architecture:** 공통 고객 조회에서 실제 주문을 집계하고, 03 노트북에 같은 최소 스키마·처리 흐름을 직접 정의한다. 구매 통계와 고객 직접 선호는 서로 다른 자료형으로 분리한다.

**Tech Stack:** Python 3.12, uv, Pydantic, Jupyter, unittest.

**Spec:** `docs/superpowers/specs/2026-10-28-customer-purchase-profile-design.md`

## Global Constraints

- 고객·주문 원본 변경, 새 패키지, commit·push 금지. 동시 사용자 변경과 04·05를 보존한다.
- 함수 한국어 docstring·연속 번호 단계 주석, Field description을 적용한다.
- 노트북은 외부 스키마 import·assert·%run·경로 보정을 넣지 않는다.
- 실제 잔액을 만들거나 누적 적립을 잔액으로 오인하지 않는다.

## Review Focus

- 잔액 누락이 0으로 바뀌지 않는지: Task1의 null/0 테스트.
- 다른 고객·비회원·중복 주문을 섞지 않는지: Task1의 고객별 집계 테스트.
- 옵션·할인을 두 번 계산하지 않는지: Task1의 total_price 합계 테스트.
- 통계를 세션 선호 목록에 복사하지 않는지: Task1·2의 상태 준비 테스트.
- 자주 산 알레르기 메뉴가 추천되는지: Task2의 필터 우선 순위 테스트.

### Task 1: 공통 프로필 — 담당 profile_purchase_state worker

**Files:** schemas/session_state.py, common/customer_store.py, tests/test_customer_profile.py.

**Interfaces:** `PurchaseStatistics` 5필드(order_count:int, total_spent:int, menu_quantities:dict[str,int], category_quantities:dict[str,int], temperature_quantities:dict[str,int]); `CustomerProfile.points/stamps` nullable StrictInt ge=0, `preferences: PurchaseStatistics | None`. `calculate_purchase_statistics(customer_id, orders, menu)` 반환 PurchaseStatistics. 고객 파일 조회는 원본 preferences 대신 주문·메뉴에서 통계를 계산한다. `ORDERS_FILE`, `MENU_FILE`은 테스트에서 patch 가능하게 둔다.

- [x] 잔액·통계·조건 분리 행동 테스트 먼저 작성해 실패를 확인한다.
- [x] 스키마·집계·조회·추천 초기화를 구현하고 관련 회귀를 검증한다.

### Task 2: 노트북과 추천 — 담당 profile_purchase_notebook worker

**Files:** notebooks/03_상품추천.ipynb, prompts/recommendation_tools.md, tests/test_recommendation_notebook.py.

**Interfaces:** Task1과 같은 스키마 및 calculate_purchase_statistics 정의를 셀에 직접 둔다. customer.preferences를 recommendation.preferences로 복사하지 않는다. 필터 통과 후보를 메뉴 수량→카테고리 수량 내림차순, 동률은 기존 순서로 정렬한다. 모델 입력은 purchase_statistics 집계만 추가한다.

- [x] 통계 로드·직접 조건 분리·통계 순위·알레르기 우선·모델 집계 전달 테스트부터 실패를 확인한다.
- [x] 노트북·프롬프트·예제를 갱신하고 기존 도구 왕복과 후속 대화를 재검증한다.

### Task 3: 통합 검증 — 담당 Codex 본체와 reviewer

- [x] 두 결과의 필드·함수·상태 의미와 개인정보 제외를 대조하고 독립 검토한다.
- [x] 전체 unittest, 노트북 형식·코드·주석·빈 출력 검증을 실행한다.
- [x] 실제 API 여부와 원본 데이터·잔액 변경 여부를 구분해 보고한다.

## 실행 기록

- 변경 전 전체 unittest 117개 통과. 두 작업에서 각 신규 행동 테스트 실패를 확인한 뒤 구현했다.
- 통합 후 본체 전체 unittest 126개 통과. 03 노트북 36셀·셀 ID·문법·한국어 함수 설명·연속 단계 번호·빈 출력 검증 통과.
- 실제 고객 10명에 대해 공통 코드와 노트북의 구매 통계 결과가 일치하며 원본 잔액 값과 null이 유지되는지 본체가 확인했다. 개인정보와 개별 고객 통계값은 출력하지 않았다.
- 독립 검토 승인. 합성 자료의 중복 주문·비회원·다른 고객·삭제 메뉴에 대해서도 공통/노트북 결과 일치를 확인했다.
- 원본 고객·주문과 잔액은 수정하지 않았다. 이번 변경에서는 실제 모델 API를 재호출하거나 Jupyter 화면을 렌더링하지 않았다.
- 영수증 적립은 이전 제안 단계이며 적립 단위·차감 정책과 실제 잔액 갱신은 이번 범위에서 진행하지 않았다.
