"""화면에서 보낸 고객 입력과 챗봇 답변을 받아, 해당 고객·세션의 대화 기록에 추가합니다."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from common.history_store import load_history, save_history
from schemas.history import HistoryInput

router = APIRouter(prefix='/chatbot', tags=['챗봇 대화 기록'])


@router.post('/history', summary='대화 기록 추가', description='고객 ID와 세션 ID에 해당하는 기존 대화에 메시지를 추가하고 전체 대화 목록 반환. 파일 읽기 또는 저장 실패 시 오류 응답.')
def append_history(payload: HistoryInput):
    """고객·세션 ID와 새 메시지를 받아 기존 대화 뒤에 저장하고, 합친 대화 목록을 돌려줍니다."""
    try:
        # 1. 기록 관리: 기존 대화 뒤에 이번 입력과 답변을 추가해 저장합니다.
        history = load_history(payload.customer_id, payload.session_id)
        history.extend(message.model_dump(mode='json') for message in payload.messages)
        save_history(payload.customer_id, payload.session_id, history)

        return {'history': history}
    except Exception:
        # 2. 저장 실패: 파일을 읽거나 쓰다가 오류가 나면, 저장하지 못했다는 HTTP 500 응답을 보냅니다.

        return JSONResponse(status_code=500, content={'detail': '대화 기록을 저장하지 못했습니다.'})
