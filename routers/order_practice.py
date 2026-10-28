"""상품 주문의 단계별 모의 처리 API를 제공합니다."""
from uuid import uuid4
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from schemas.session_state import SessionState
from services.notebook_order import run_order
from common.notebook_step_store import record_result

router = APIRouter(prefix='/chatbot', tags=['챗봇 단계별 주문'])


@router.post('/order/practice')
def order_turn(payload: SessionState):
    """고객 상태를 받아 주문 초안이나 모의 접수 결과를 돌려줍니다."""
    # 1. 입력 확인: 주문 문장이 없으면 모델을 호출하지 않습니다.
    if payload.input is None:

        return JSONResponse(status_code=422, content={'detail': '고객 입력이 필요합니다.'})
    try:
        # 2. 주문 처리: 노트북의 추출과 검증 흐름을 실행합니다.

        session_id = payload.session_id or uuid4().hex
        payload.session_id = session_id

        return record_result('order', session_id, run_order(payload))
    except Exception:
        # 3. 오류 안내: 자료나 모델 연결 오류를 화면에 알립니다.

        return JSONResponse(status_code=502, content={'detail': '주문 처리에 실패했습니다. 메뉴 자료와 OpenAI 설정을 확인해주세요.'})
