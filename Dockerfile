# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./

# 이미지 검색에 필요한 PyTorch와 FAISS CPU를 잠금 파일 기준으로 설치합니다.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --group embedding --no-install-project


FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/hf

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY main.py ./
COPY common/ common/
COPY routers/ routers/
COPY schemas/ schemas/
COPY services/ services/
COPY templates/ templates/
COPY static/ static/
COPY prompts/ prompts/
COPY tests/fixtures/ tests/fixtures/
COPY data/ data/

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
