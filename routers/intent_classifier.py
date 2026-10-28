"""고객 입력과 대화 상태를 받아 의도 분류 함수를 호출하고, 결과나 오류를 HTTP 응답으로 보냅니다."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from schemas.session_state import CustomerRequest
from services.intent_notebook import reset_session, run_turn


router = APIRouter(prefix='/chatbot/intent', tags=['챗봇 의도 분류'])


@router.post('/turn', summary='의도 분류 한 턴 실행', description='고객 요청으로 실습용 상태 준비, Jev 의도 분류, 상태 저장을 차례로 실행하고 결과 반환. 분류 실패 시 상태 저장 없이 오류 응답.')
def run_notebook_turn(payload: CustomerRequest):
    """고객 요청으로 노트북의 상태 준비·분류·저장 과정을 실행해 결과를 돌려줍니다."""
    # 1. 한 턴 실행: 분류 실패 시 상태를 저장하지 않고 연결 확인 안내를 돌려줍니다.
    try:

        return run_turn(payload)
    except Exception:

        return JSONResponse(status_code=502, content={'detail': '의도 분류 또는 확인 답변 생성에 실패했습니다. Jev와 OpenAI 설정 및 연결 상태를 확인해주세요.'})


@router.delete('/turn/{session_id}', summary='의도 분류 실습 세션 초기화', description='지정한 세션의 의도 분류 실습용 메모리 상태 삭제 및 삭제 여부 반환. 파일에 저장된 대화·상태 기록은 삭제 대상에서 제외.')
def reset_notebook_session(session_id: str):
    """세션 ID를 받아 노트북 실습용 메모리 상태를 초기화합니다."""
    # 1. 세션 초기화: 해당 세션만 삭제하고 삭제 여부를 돌려줍니다.

    return {'deleted': reset_session(session_id)}
