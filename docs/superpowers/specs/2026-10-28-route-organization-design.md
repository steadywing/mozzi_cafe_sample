# 라우터와 경로 정리 설계

## 목적

현재 화면 경로가 `main.py`, `routers/testboard.py`, 기능별 라우터에 흩어지고 API 접두어도 서로 다릅니다. 초보자가 화면, 챗봇 처리, 테스트 자료의 역할을 경로만 보고 구별할 수 있도록 현재 동작을 유지하며 주소와 파일 책임을 정리합니다.

## 선택한 방식

사용자가 기존 주소 변경을 허용하고 챗봇 관련 경로에 `chatbot` 접두어를 요청했습니다. 화면은 명시적인 `/test/...`, 챗봇 처리·대화 기록은 `/chatbot/...`, 테스트 자료·실행 기록은 `/test/api/...`로 옮깁니다. 공개 경로에서 노트북 출처를 뜻하는 `notebook`을 빼고 기능 이름을 씁니다. 이전 주소의 별칭은 두지 않습니다. `main.py`의 포괄 화면 경로 두 개를 없애고, `/`를 포함한 화면 GET은 `routers/test_pages.py` 한 파일에 둡니다. 서비스 함수·스키마·저장 형식·모델 입력은 바꾸지 않습니다.

## 화면 경로

| 화면 | 새 경로 | 이전 경로 |
|---|---|---|
| 구현 현황 | `/` | `/` |
| 의도 분류 | `/test/intent` | `/test` |
| 확인 답변 | `/test/unknown` | `/test/notebook/unknown` |
| 기존 주문 테스트 | `/test/order` | `/test/order` |
| 단계별 주문 실습 | `/test/order/practice` | `/test/notebook/order` |
| 상품추천 | `/test/recommendation` | `/test/recommendation` |
| 상품검색 | `/test/search` | `/test/search` |
| 카페 정보 문의 | `/test/consultation` | `/test/notebook/consultation` |
| 포인트 적립 | `/test/points` | `/test/notebook/points` |

두 주문 화면은 서로 다른 처리 함수를 쓰므로 합치지 않습니다. 메뉴에는 두 경로의 차이를 표시합니다.

## 챗봇 처리 경로와 테스트 자료 경로

| 역할 | 새 경로 | 이전 경로 |
|---|---|---|
| 의도 분류 실행·초기화 | `POST /chatbot/intent/turn`, `DELETE /chatbot/intent/turn/{session_id}` | `/intent_classifier/turn...` |
| 기존 주문 처리 | `POST /chatbot/order` | `/product_order` |
| 대화 기록 추가 | `POST /chatbot/history` | `/history` |
| 테스트보드 자료·상태 | `/test/api/...` | `/test/...`의 자료·상태 경로 |
| 확인 답변 | `POST /chatbot/unknown` | `POST /notebook/unknown` |
| 단계별 주문 실습 | `POST /chatbot/order/practice` | `POST /notebook/order` |
| 상품추천·검색·정보문의 | `POST /chatbot/recommendation`, `/chatbot/search`, `/chatbot/consultation` | `POST /notebook/...` |
| 검색 예시·이미지 | `GET /test/api/search/samples`, `/test/api/search/cases`, `/test/api/search/images/{sample}` | `GET /notebook/search/...` |
| 포인트 적립·초기화 | `/chatbot/points/...` | `/notebook/points/...` |
| 포인트 예시·이미지 | `/test/api/points/...` | `/notebook/points/cases`, `/notebook/points/samples/...` |
| 실습 기록 조회·삭제 | `GET·DELETE /test/api/traces/{feature}/{session_id}` | `GET·DELETE /notebook/traces/...` |

테스트보드 자료 경로의 나머지 부분과 HTTP 메서드는 유지합니다. 예를 들어 `/test/order/cases`는 `/test/api/order/cases`, `/notebook/points/confirm`은 `/chatbot/points/confirm`이 됩니다. 포인트의 시작·확인·초기화, 실습 기록의 조회·삭제는 각각 다른 상태를 다루므로 분리된 경로를 유지합니다. 두 주문 실행 함수는 합치지 않고 `/chatbot/order`와 `/chatbot/order/practice`로 구분합니다.

## 함께 바꿀 부분

- 화면의 `fetch()` 주소, 내비게이션 링크, 화면에 보이는 API 경로
- 기능 API를 받는 `routers/notebook_*.py`는 `routers/unknown.py`, `routers/order_practice.py`, `routers/recommendation.py`, `routers/search.py`, `routers/consultation.py`, `routers/points.py`, `routers/traces.py`로 이름을 바꾸고, `routers/product_order.py`는 `routers/order.py`로 바꿉니다. 검색·포인트의 샘플 자료 GET은 `routers/test_samples.py`로 모아 기능 라우터에는 `/chatbot/...` 처리만 둡니다. 내부 `services/notebook_*.py`는 이번 경로 정리의 범위 밖입니다.
- 주소를 검증하는 Python·프런트엔드 테스트
- README, 파일 구조 문서, 서비스 SVG의 실제 경로 설명

## 검증 기준

- OpenAPI와 실제 요청에서 새 경로가 동작하고 이전 경로는 등록되지 않습니다.
- 모든 화면 GET이 명시적이며 하나의 화면 라우터에서 템플릿을 반환합니다.
- 기존 처리 함수·상태 저장·응답 형식은 유지됩니다.
- 외부 모델을 호출하지 않는 API·프런트엔드 테스트와 화면 렌더링을 확인합니다.
