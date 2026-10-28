"""고객 입력과 주문 상태를 받아 주문 처리 함수를 호출하고, 결과나 오류를 HTTP 응답으로 보냅니다."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from schemas.session_state import SessionState
from services.product_order import run_product_order

router = APIRouter(prefix='/chatbot', tags=['챗봇 주문'])


@router.post('/order', summary='상품 주문 처리', description='고객 입력과 주문 상태를 바탕으로 주문 정보를 확인하고 다음 질문 또는 테스트 접수 결과가 담긴 상태 반환. 테스트 접수는 실제 주문 저장이나 결제가 아님.')
def product_order(payload: SessionState):
    """고객의 입력과 주문 상태를 받아 다음 확인 질문이나 테스트 접수 결과가 담긴 상태를 돌려줍니다."""
    # 1. 입력 확인: 고객 문장이 없으면 모델 호출 전에 입력 오류를 돌려줍니다.
    if payload.input is None:

        return JSONResponse(status_code=422, content={'detail': '고객 입력이 필요합니다.'})

    # 2. 주문 처리: 주문을 읽고 메뉴·고객 확인을 진행하는 함수를 호출해, 그 결과를 그대로 응답합니다.
    try:

        return run_product_order(payload)
    except Exception:
        # 3. 처리 실패: 모델 호출이나 자료·기록 처리에서 오류가 나면, HTTP 502와 확인할 항목을 안내합니다.

        return JSONResponse(status_code=502, content={'detail': '주문 처리에 실패했습니다. 모델 설정과 메뉴 자료를 확인해주세요.'})
