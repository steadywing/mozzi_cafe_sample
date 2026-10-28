"""카페 정보 문서 선택과 답변 실습을 HTTP로 제공합니다."""
from fastapi import APIRouter, HTTPException
from uuid import uuid4
from schemas.session_state import SessionState
from services.notebook_consultation import run_consultation
from common.notebook_step_store import record_result

router = APIRouter(prefix='/chatbot', tags=['챗봇 정보문의'])


@router.post('/consultation')
def consultation(payload: SessionState):
    """고객 질문을 받아 문서 선택과 답변 결과를 돌려줍니다."""
    # 1. 요청 실행: 문장이 없으면 안내하고 모델 실패는 연결 오류로 돌려줍니다.
    if payload.input is None:
        raise HTTPException(status_code=422, detail='고객 입력이 필요합니다.')
    try:

        session_id = payload.session_id or uuid4().hex
        payload.session_id = session_id

        return record_result('consultation', session_id, run_consultation(payload))
    except Exception:
        raise HTTPException(status_code=502, detail='문서 선택 또는 답변 생성에 실패했습니다. 모델 설정과 연결을 확인해 주세요.')
