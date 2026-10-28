from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from routers.intent_classifier import router as intent_classifier_router
from routers.testboard import router as testboard_router
from routers.history import router as history_router
from routers.order import router as order_router
from routers.test_pages import router as test_pages_router
from routers.test_samples import router as test_samples_router
from routers.unknown import router as unknown_router
from routers.order_practice import router as order_practice_router
from routers.recommendation import router as recommendation_router
from routers.search import router as search_router
from routers.consultation import router as consultation_router
from routers.points import router as points_router
from routers.traces import router as traces_router
from common.client import close_clients
from common.prompt_store import load_prompts


# 다른 폴더에서 서버를 실행해도 main.py를 기준으로 화면 파일과 정적 파일을 찾습니다.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버가 시작되면 모델 지침을 읽어 두고, 종료되면 사용한 모델 연결을 닫습니다."""

    # 1. 지침 준비: 서버가 요청을 받기 전에 모델 지침을 메모리에 읽어 둡니다.
    load_prompts()

    # 2. 연결 정리: 서버가 실행되는 동안 기다렸다가 종료 시 모델 연결을 닫습니다.
    try:
        yield
    finally:
        close_clients()


app = FastAPI(title="모찌카페", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(test_pages_router)
app.include_router(intent_classifier_router)
app.include_router(testboard_router)
app.include_router(history_router)
app.include_router(order_router)
app.include_router(test_samples_router)
app.include_router(unknown_router)
app.include_router(order_practice_router)
app.include_router(recommendation_router)
app.include_router(search_router)
app.include_router(consultation_router)
app.include_router(points_router)
app.include_router(traces_router)


@app.get("/health", summary="서버 상태 확인", description="서버의 응답 여부 확인. 외부 모델 연결과 데이터 파일 상태는 확인 대상에서 제외.")
def health():
    """서버 상태 확인 요청을 받으면 외부 모델을 부르지 않고 정상 응답을 돌려줍니다."""

    # 1. 정상 응답: 모델이나 데이터 파일을 확인하지 않고 서버가 살아 있음을 알립니다.

    return {"status": "ok"}
