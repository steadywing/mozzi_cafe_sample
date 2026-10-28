# 모찌카페

카페 챗봇 수업 확장 예제. 현재는 의도 분류와 기능별 독립 실습 API를 테스트보드에서 확인하며, 고객용 통합 챗봇은 아직 연결하지 않았다.

## 클론 후 로컬 서버 실행

Git, Python 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/)를 준비합니다. 아래 명령은 프로젝트 루트에서 실행합니다. 저장소에 접근 권한이 필요한 경우 GitHub에서 본인이 사용할 수 있는 클론 URL로 바꿉니다.

```sh
git clone https://github.com/steadywing/mozzi_cafe_sample.git
cd mozzi_cafe_sample
uv sync --locked
```

`.env.example`을 `.env`로 복사한 뒤 사용할 기능의 API 키를 채웁니다. macOS·Linux에서는 `cp .env.example .env`, Windows PowerShell에서는 `Copy-Item .env.example .env`를 사용합니다. 의도 분류에는 `TYPESAFE_API_KEY`, 주문·추천 등 답변 생성에는 `OPENAI_API_KEY`가 필요합니다. 영수증 포인트 실습을 사용한다면 `.env`에 `GEMINI_API_KEY=발급받은_키`도 추가합니다. `.env`는 Git에 올리지 않습니다.

```sh
uv run uvicorn main:app --reload
```

서버가 켜지면 다음 주소를 확인합니다. 종료할 때는 터미널에서 `Ctrl+C`를 누릅니다.

| 주소 | 확인할 내용 |
|---|---|
| http://127.0.0.1:8000/ | 구현 현황 화면 |
| http://127.0.0.1:8000/test/intent | 의도 분류 테스트 화면 |
| http://127.0.0.1:8000/health | 서버 응답 (`{"status":"ok"}`) |
| http://127.0.0.1:8000/docs | API 문서 |

`data/`는 Git 관리에서 제외되어 클론만으로는 내려오지 않습니다. 서버와 기본 화면은 실행할 수 있지만, 메뉴·고객·주문·카페 문서·샘플 사진·FAISS 인덱스를 사용하는 실습에는 프로젝트 관리자가 제공한 `data/` 폴더를 프로젝트 루트에 별도로 놓아야 합니다. 로컬 상품 검색에는 추가로 `uv sync --locked --group embedding`으로 검색 의존성을 설치해야 합니다. 임베딩 모델은 첫 검색 때 인터넷에서 내려받아 캐시에 보관합니다.

### Windows + NVIDIA GPU에서 Docker 실행

Docker Desktop의 WSL 2 백엔드와 NVIDIA 드라이버를 준비한 뒤, WSL 2 터미널에서 프로젝트 폴더로 이동해 실행합니다. 이미지는 Linux `amd64`용이며 Python 3.12와 잠금 파일의 `embedding` 의존성 그룹을 사용합니다. 현재 잠금 파일의 Linux PyTorch는 CUDA 13 계열을 사용하므로 NVIDIA 드라이버는 R580 이상이어야 합니다.

```sh
docker build --platform linux/amd64 -t wanted-cafe-chatbot:cuda .
docker run --rm --gpus all -p 8000:8000 --env-file .env \
  -v wanted-cafe-data:/app/data -v wanted-cafe-hf:/models/hf \
  wanted-cafe-chatbot:cuda
```

실행 전 `.env.example`을 참고해 프로젝트 루트에 `.env`와 필요한 API 키를 준비합니다. `data/`는 빌드 시 이미지에 복사됩니다. 새 `wanted-cafe-data` 볼륨에는 이미지의 데이터가 처음 실행할 때 복사되고, 이후 대화·상태 변경이 볼륨에 남습니다. 이미지에 새 데이터를 넣어 다시 빌드해도 기존 볼륨의 파일은 자동으로 바뀌지 않습니다. 검색 모델은 첫 상품 검색 때 인터넷에서 내려받고 `wanted-cafe-hf` 볼륨에 보관하므로 사전 다운로드는 필요하지 않습니다. 서버 확인 주소는 `http://localhost:8000/health`입니다.

Slack으로 이미지를 전달하려면 빌드한 컴퓨터에서 `docker save wanted-cafe-chatbot:cuda | gzip > wanted-cafe-chatbot-cuda.tar.gz`로 파일을 만들고, 받은 컴퓨터에서 `docker load -i wanted-cafe-chatbot-cuda.tar.gz`를 실행합니다. 받은 사람은 자신의 `.env`를 만든 뒤 위 `docker run` 명령으로 서버를 켭니다. `.env`는 이미지나 전달 파일에 넣지 않습니다. 이미지에는 빌드 시점의 `data/history/`·`data/state/` 기록도 포함되므로 전달 전에 해당 기록을 확인합니다. 압축 파일이 [Slack의 파일당 1GB 제한](https://slack.com/help/articles/201330736-Add-files-to-Slack)을 넘으면 다른 파일 공유 방법을 사용해야 합니다.

현재 상품 검색은 임베딩 생성에 CUDA를 사용하고, 17개 메뉴 벡터의 FAISS 검색은 CPU 인덱스로 수행합니다. `faiss-gpu` 설치만으로 검색이 GPU로 바뀌지 않아 이 이미지에는 `faiss-cpu`를 유지했습니다. GPU 사용 여부는 `docker run --rm --gpus all wanted-cafe-chatbot:cuda python -c "import torch; print(torch.cuda.is_available())"`로 확인할 수 있습니다.

## 기능 현황

1. 의도 분류와 확인 답변: 세션 상태를 복원하고 매 턴 Jev로 분류합니다. `unknown`이면 OpenAI로 확인 답변을 생성하고 메모리 상태에 저장합니다.
2. 상품 주문: 기존 주문 테스트와 단계별 주문 실습은 서로 다른 처리 함수를 사용합니다. 두 경로 모두 주문 초안 확인과 모의 접수를 실행하며 실제 결제나 주문 저장은 하지 않습니다.
3. 상품 추천: 별도 실습 API에서 알레르기·선호 조건을 수집하고 메뉴를 필터링해 답변합니다.
4. 상품 검색: 별도 실습 API에서 서버에 준비된 샘플 사진과 문장으로 이미지 임베딩·유사 메뉴 검색·답변을 실행합니다. 고객 사진 업로드는 아직 받지 않습니다.
5. 카페 정보 문의: 별도 실습 API에서 필요한 카페 문서를 선택해 읽고, 문서 내용에 근거해 답변합니다.
6. 영수증 포인트 적립: 별도 실습 API에서 샘플 영수증을 판독·검증하고, 고객 확인 후 가상 포인트를 갱신합니다. 종이 쿠폰을 사용하는 스탬프 적립은 이 경로에 구현되지 않았습니다.
7. 테스트보드: 각 API의 단계별 상태·모델 입력·프롬프트·처리 결과를 확인합니다. 범용 중간 결과 수정·단계 재실행·수정 전후 비교는 아직 제공하지 않습니다.

의도 분류 결과가 기능별 API를 자동 호출하는 통합 처리 경로, 고객용 챗봇 화면, STT·TTS는 아직 구현되지 않았습니다. 코드 작성 원칙과 목표 기능은 `AGENTS.md`에 있습니다.

## 현재 상태

`/test/intent`에서 노트북 `1_0`을 바탕으로 매 턴 상태를 준비하고 Jev로 분류한 뒤 메모리에 저장합니다. 왼쪽에서 대화와 테스트 사례를 선택하고 오른쪽에서 각 단계의 상태, 모델 입력, 프롬프트와 처리 시간을 확인합니다. `unknown`이면 고객에게 보낼 확인 답변도 생성합니다. 주문은 `/test/order`의 기존 처리와 `/test/order/practice`의 단계별 실습을 구분해 실행합니다. 그 밖의 기능도 각 테스트 화면에서 독립적으로 실행합니다.

## 경로 안내

- `/test/...`: HTML 테스트 화면입니다. `/test/intent`, `/test/unknown`, `/test/order`, `/test/order/practice`, `/test/recommendation`, `/test/search`, `/test/consultation`, `/test/points`를 명시적으로 제공합니다.
- `/chatbot/...`: 챗봇 처리와 대화 기록 API입니다. 현재 화면별 실습이 호출하며, 의도 분류 결과가 다른 기능을 자동 실행하지는 않습니다.
- `/test/api/...`: 테스트 사례, 샘플 이미지, 프롬프트, 상태와 단계 기록의 조회·초기화 API입니다.

### 의도 분류

`.env`에 `TYPESAFE_API_KEY`를 설정하고 서버를 실행합니다. 기본 모델은 `TYPESAFE_MODEL=jev-latest`입니다. 주문 기능의 OpenAI 설정은 `.env.example`을 참고합니다. 프롬프트 파일을 수정하면 서버를 재시작합니다.

- `GET /test/intent`: 의도 분류 테스트보드
- `GET /test/api/intent-turn/cases`: 단일 입력과 연속 대화 테스트 사례
- `POST /chatbot/intent/turn`: `session_id`, `customer_info`, `input`을 받아 상태 준비 → 의도 분류 → `unknown` 확인 답변 생성 → 상태 저장 결과를 반환합니다. Jev에는 `text`, `previous_intent`, `has_image`만 보냅니다.
- `DELETE /chatbot/intent/turn/{session_id}`: 지정한 의도 분류 세션의 메모리 상태를 초기화합니다.
- `GET /test/order`, `POST /chatbot/order`: 기존 주문 테스트보드와 처리 API
- `GET /test/order/practice`, `POST /chatbot/order/practice`: 단계별 주문 실습 화면과 처리 API
- `GET /test/api/order/prompts`, `GET /test/api/order/cases`: 주문 지침과 사례 조회
- `POST /chatbot/history`, `DELETE /test/api/session`, `DELETE /test/api/sessions`: 주문 테스트에서 사용하는 대화·상태 기록 관리
- `POST /chatbot/unknown`, `/chatbot/recommendation`, `/chatbot/search`, `/chatbot/consultation`: 각 기능을 독립 실행하는 실습 API
- `POST /chatbot/points/start`, `/chatbot/points/confirm`: 샘플 영수증 판독과 고객 확인 후 가상 포인트 적립
- `GET /test/api/search/cases`, `/test/api/search/images/{sample}`, `/test/api/points/cases`, `/test/api/points/samples/{sample}`: 실습 예시와 샘플 이미지
- `GET·DELETE /test/api/traces/{feature}/{session_id}`: 기능별 단계 기록 조회·삭제

의도 분류 세션은 서버 프로세스 메모리에만 저장되며 서버를 재시작하면 초기화됩니다. 사례 선택 후 보내기를 눌러 실행하고, 독립 사례는 새 대화에서 시작합니다. 의도 분류 화면의 이미지 사례는 첨부 여부만 전달합니다. 실제 이미지 인식이나 Jev의 분류 정확도는 별도 검증이 필요합니다.

## 파일 구조

```text
main.py                 # FastAPI 앱, 라우터와 정적 파일 연결
common/client.py        # Jev·OpenAI 클라이언트 생성·재사용·종료
common/prompt_store.py  # 프롬프트 시작 시 로드와 조회·저장 함수
common/history_store.py # 고객·세션별 대화 기록 저장
common/state_store.py   # 고객·세션별 업무 상태 기록 저장
routers/intent_classifier.py # 의도 분류 API
routers/order.py         # 기존 상품 주문 API
routers/order_practice.py # 단계별 주문 실습 API
routers/unknown.py, recommendation.py, search.py, consultation.py, points.py # 기능 처리 API
routers/traces.py       # 기능별 실습 단계 기록 API
routers/history.py      # 대화 기록 저장 API
routers/test_pages.py   # 테스트 화면 GET 경로
routers/test_samples.py # 검색·포인트 예시와 샘플 이미지 GET 경로
routers/testboard.py    # 테스트 자료·프롬프트·상태 조회 및 관리 API
schemas/session_state.py # SessionState와 내부 데이터 형식
schemas/history.py      # 대화 기록 저장 요청 형식
schemas/testboard.py    # 테스트보드 요청 형식
schemas/product_order.py # 주문 Structured Output 스키마
services/intent_notebook.py # 상태 준비·Jev 분류·메모리 저장
services/product_order.py # 기존 주문 추출·검증·모의 접수
services/notebook_*.py # 단계별 실습 처리
templates/index.html    # 현재 서비스 구현 현황 화면
templates/test.html     # 의도 분류 실행 화면
templates/order.html    # 상품 주문 실행 화면
templates/notebook_order.html # 단계별 주문 실습 화면
templates/notebook_*.html # 기능별 실습 화면
notebooks/              # 기초 사용법과 기능별 실습
tests/fixtures/intent_turn_cases.json # 의도 분류 테스트 예제
static/css/style.css    # 공통·설계 화면 스타일
static/css/intent-test.css # 의도 분류 화면 스타일
static/js/diagram-details.js # 흐름도 상세 표시
static/js/intent-turn.js # 의도 분류 화면의 입력·API 호출·결과 표시
static/js/intent-test.js # 기존 주문 화면의 입력·API 호출·결과 표시
static/js/notebook_*.js # 기능별 실습 화면의 API 호출·결과 표시
tests/frontend/intent-session.test.cjs # 프런트 세션 유지 검증
static/diagrams/service-flow.svg  # 현재 API별 처리 흐름의 노드·연결선
```

전체 폴더 구성과 파일별 역할은 [폴더 구조](docs/폴더-구조.md)에 정리되어 있다. 작성 기준은 [주석 규칙](docs/주석-규칙.md)과 [노트북 작성 규칙](docs/노트북-작성-규칙.md)을 따른다.

구현 현황 설명은 `templates/index.html`, 화면 스타일은 `static/css/style.css`, 흐름도의 노드와 연결선은 `static/diagrams/service-flow.svg`에서 수정한다. 흐름도는 외부 CDN이나 라이브러리 없이 로컬 SVG로 표시한다.
HTML 연결은 FastAPI의 [템플릿 공식 문서](https://fastapi.tiangolo.com/advanced/templates/)를 따른다.
