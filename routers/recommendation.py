"""추천 조건과 답변을 처리하는 API를 제공합니다."""
from uuid import uuid4
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from schemas.session_state import SessionState
from services.notebook_recommendation import run_recommendation
from common.notebook_step_store import record_result

router = APIRouter(prefix='/chatbot', tags=['챗봇 상품추천'])


@router.post('/recommendation')
def recommendation_turn(state: SessionState):
    """고객 상태를 받아 추천 단계를 실행하고 결과를 돌려줍니다."""
    # 1. 단계 실행: 입력이 없으면 오류를 알리고 처리 실패는 연결 안내를 반환합니다.
    if state.input is None:

        return JSONResponse(status_code=422, content={'detail': '고객 입력이 필요합니다.'})
    try:

        session_id = state.session_id or uuid4().hex
        state.session_id = session_id

        return record_result('recommendation', session_id, run_recommendation(state))
    except Exception:

        return JSONResponse(status_code=502, content={'detail': '추천 처리에 실패했습니다. 모델 설정과 메뉴 자료를 확인해 주세요.'})
