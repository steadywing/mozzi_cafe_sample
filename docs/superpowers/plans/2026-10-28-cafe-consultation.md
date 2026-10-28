# 카페정보문의 노트북 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실제 로컬 카페 문서를 조회해 근거와 출처를 확인하며 답변하는 05 노트북을 만든다.

**Architecture:** 모델 질의 정리 → 단순 Python 주제 조회 → 모델 근거 답변. 7개 Markdown 원문과 기존 query/response/persona 프롬프트를 재사용한다.

**Tech Stack:** Python 3.12, uv, OpenAI Responses, Pydantic, Jupyter, unittest.

**Spec:** `docs/superpowers/specs/2026-10-28-cafe-consultation-design.md`

## Global Constraints

- 기존 코드·공통 State·원본 자료·프롬프트를 보존한다. commit·push·패키지 추가 금지.
- 노트북은 스키마 직접 정의, 함수 작성→호출→결과 확인으로 구성한다.
- assert·%run·루트탐색·sys.path·작업 디렉터리 자동 변경을 넣지 않는다.
- 함수 한국어 docstring·함수마다 연속 번호의 단계 주석, 모든 Field description을 적용한다.

## Review Focus

- 한국어 표현 차이로 조회를 놓치는가: 주제·동의어와 다중 주제를 테스트한다.
- 질문 명확/자료 없음과 질문 모호함을 혼동하는가: 각각 다른 분기를 테스트한다.
- 출처를 만들어낼 수 있는가: 조회하지 않은 source는 답변 출처로 허용하지 않는다.
- 후속 질문이 이전 맥락을 사용하는가: history 전달과 상태 복사를 확인한다.
- 가상 주소·운영 조건·문서 표가 훼손되는가: 실제 원문 전체 보존과 답변용 근거 전달을 확인한다.

### Task 1: 노트북과 실제 조회 — 담당 consultation_notebook worker

**Files:** Create `notebooks/05_카페정보문의.ipynb`, `tests/test_consultation_notebook.py`.

**Interfaces:** `load_cafe_documents()`로 source/title/content 문서 목록을 준비한다. `create_consultation_query(state)`는 `ConsultationQuery`를 반환한다. `search_cafe_information(query, topic)`는 실제 문서 목록을 반환한다. `create_consultation_response(state)`는 답변을 반환하고 실제 사용 출처를 검증한다. `run_product_consultation(state)`는 복사한 상태에 문의 결과와 history를 담는다.

- [x] 실제 자료 조회·다중 주제·출처 제한·모호한 질문·근거 없음·후속 대화 행동 테스트를 먼저 작성하고 미구현 실패를 확인한다.
- [x] 기존 02/03과 비슷한 크기로 함수 직접 실행과 전체 연결을 작성한다. topic과 정리된 query를 함께 사용하되 모델이 파일 경로를 지정하지 않는다.
- [x] 대체 응답으로 모델 연결을 검증한다. 외부 모델 호출은 본체가 별도 수행한다.

### Task 2: 검토와 검증 — 담당 Codex 본체와 읽기 전용 reviewer

- [x] 구현과 검증 결과를 읽고 독립 검토를 수행한다.
- [x] `uv run python -m unittest discover -s tests -v`로 기존 기능과 전체 회귀를 확인한다.
- [x] 노트북 JSON·코드·주석·금지 코드·빈 출력, 데이터/민감 파일 변경 유무를 확인한다.
- [x] 실제 모델로 근거 있는 문의와 자료 없는 문의를 확인하고 결과와 한계를 구분해 보고한다.

## 실행 기록

- 작업 중 사용자가 별도로 추가한 `04_이미지임베딩.ipynb`를 발견해 보존하고 문의 노트북 번호를 05로 정했다.
- 신규 행동 테스트 실패→통과, 후속 출처 제약 회귀 테스트 실패→통과. 본체 전체 unittest 113개 통과.
- 03·05 노트북 형식·코드 문법·한국어 함수 설명·단계 번호·빈 출력 검증 통과. 05는 25셀이다.
- 실제 API에서 자유 문자열 출처가 조회 범위를 벗어나 오류가 된 사례를 확인했다. source enum으로 생성 범위를 제한하고 사후 검증을 유지했으며 별도 리뷰 승인.
- 독립 리뷰에서 실제 조회, 상태 보존, 자료 없음과 모호함 구분, 셀 실행 연결과 출처 제한을 확인했다.
- 수정 후 실제 gpt-5-nano 재검증: 주말 10:00~21:00·마지막 주문 20:30을 해당 문서 근거로 답했다. 유아용 의자는 매장 이용 문서에 없음을 안내했고, 조회 출처 범위를 벗어나지 않았다.
- 실제 모델은 핵심 입력을 함수로 호출해 확인했다. 노트북 전체 셀의 일괄 실행과 Jupyter 화면 렌더링은 하지 않았다. 저장 출력은 비워 두었다.
