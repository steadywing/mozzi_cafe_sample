"""고객 문장과 준비된 사진으로 상품을 검색하는 API를 제공합니다."""
from uuid import uuid4
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from services.notebook_search import run_search, sample_names
from common.notebook_step_store import record_result

router = APIRouter(tags=['챗봇 상품검색'])


class SearchRequest(BaseModel):
    """검색할 고객 문장과 서버에 준비된 샘플 사진 이름을 담습니다."""
    text: str = Field(min_length=1, max_length=4000, description='검색할 고객 문장')
    sample: str = Field(description='서버에 준비된 검색 샘플 사진 파일명')
    session_id: str | None = Field(default=None, description='검색 단계와 턴 기록을 묶을 실습 세션 ID')

    @field_validator('text')
    @classmethod
    def check_text(cls, value):
        """고객 문장의 공백을 제거하고 빈 문장은 거부합니다."""
        # 1. 문장 확인: 내용 없는 요청을 검색 전에 거부합니다.
        if not value.strip():
            raise ValueError('고객 문장을 입력해 주세요.')

        return value.strip()


@router.post('/chatbot/search')
def search_turn(payload: SearchRequest):
    """고객 문장과 샘플 사진을 받아 검색 단계를 실행합니다."""
    # 1. 사진 확인: 임의의 서버 경로는 사용하지 않습니다.
    if payload.sample not in sample_names():

        return JSONResponse(status_code=422, content={'detail': '준비된 샘플 사진을 선택해 주세요.'})
    try:

        session_id = payload.session_id or uuid4().hex

        return record_result('search', session_id, run_search(payload.text, payload.sample))
    except Exception:

        return JSONResponse(status_code=502, content={'detail': '검색에 실패했습니다. 로컬 임베딩 모델, 인덱스와 모델 설정을 확인해 주세요.'})
