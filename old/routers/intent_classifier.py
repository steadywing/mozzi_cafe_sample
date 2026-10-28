"""고객 입력과 대화 상태를 받아 의도 분류 함수를 호출하고, 결과나 오류를 HTTP 응답으로 보냅니다."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from schemas.session_state import CustomerRequest, SessionState
from old.services.intent_classifier import run_intent_classifier
from services.intent_notebook import reset_session, run_turn


router = APIRouter(tags=['intent'])


@router.post('/intent_classifier')
def test_intent_classifier(payload: SessionState):
    """고객의 대화 상태를 받아 요청한 기능을 분류하고, 필요하면 확인 질문도 만들어 돌려줍니다."""
    # 1. 입력 확인: 고객 문장이 없으면 모델을 부르지 않고 HTTP 422 응답으로 알립니다.
    if payload.input is None:

        return JSONResponse(status_code=422, content={'detail': '고객 입력이 필요합니다.'})
    try:
        # 2. 분류 실행: 요청한 기능을 구분하고, 구분하기 어려운 경우에만 확인 질문을 만듭니다.

        return run_intent_classifier(payload)
    except Exception:
        # 3. 처리 실패: 분류나 질문 생성에서 오류가 나면, HTTP 502와 설정·연결을 확인하라는 안내를 보냅니다.

        return JSONResponse(status_code=502, content={'detail': '의도 분류 또는 확인 질문 생성에 실패했습니다. 설정과 연결 상태를 확인해주세요.'})




