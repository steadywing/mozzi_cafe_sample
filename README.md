# 모찌카페

## 클론 후 서버 실행

Git, Python 3.12, [uv](https://docs.astral.sh/uv/getting-started/installation/)를 준비합니다.

### 1. 프로젝트 받기

```sh
git clone https://github.com/steadywing/mozzi_cafe_sample.git
cd mozzi_cafe_sample
uv sync --locked
```

실습용 `data/`는 저장소에 포함되어 함께 내려옵니다. 상품 검색도 사용하려면 추가 의존성을 설치합니다.

```sh
uv sync --locked --group embedding
```

### 2. API 키 설정

프로젝트 루트의 `.env.example`을 복사해 `.env`를 만듭니다.

```sh
# macOS / Linux
cp .env.example .env
```

Windows PowerShell에서는 `Copy-Item .env.example .env`를 실행합니다.

`.env`에 사용할 기능의 키를 입력합니다.

- `TYPESAFE_API_KEY`: 의도 분류·카페 문서 선택
- `OPENAI_API_KEY`: 주문·추천·검색 등 답변 생성
- `GEMINI_API_KEY`: 영수증 포인트 실습을 사용할 때 추가

### 3. 서버 실행

```sh
uv run uvicorn main:app --reload
```

브라우저에서 http://127.0.0.1:8000 에 접속합니다. API 문서는 http://127.0.0.1:8000/docs 에서 확인합니다.

상품 검색 모델은 첫 검색 때 내려받습니다. 서버를 종료하려면 터미널에서 `Ctrl+C`를 누릅니다.
