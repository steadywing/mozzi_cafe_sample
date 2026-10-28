"""의도를 알 수 없는 요청의 확인 질문 API를 제공합니다."""
from uuid import uuid4
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from schemas.session_state import SessionState
from services.notebook_unknown import run_unknown
from common.notebook_step_store import record_result

router = APIRouter(prefix='/chatbot', tags=['챗봇 확인 답변'])


@router.post('/unknown')
def unknown_turn(payload: SessionState):
    """고객 상태를 받아 확인 질문 생성 결과를 돌려줍니다."""
    # 1. 입력 확인: 현재 문장이 없으면 모델을 호출하지 않습니다.
    if payload.input is None:

        return JSONResponse(status_code=422, content={'detail': '고객 입력이 필요합니다.'})
    try:
        # 2. 답변 생성: 노트북의 생성 함수를 호출해 결과를 돌려줍니다.

        session_id = payload.session_id or uuid4().hex
        payload.session_id = session_id

        return record_result('unknown', session_id, run_unknown(payload))
    except Exception:
        # 3. 오류 안내: 모델 연결이나 답변 오류를 화면에 알립니다.

        return JSONResponse(status_code=502, content={'detail': '확인 답변 생성에 실패했습니다. OpenAI 설정과 연결 상태를 확인해주세요.'})
