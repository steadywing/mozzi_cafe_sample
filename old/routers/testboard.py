"""테스트 화면을 열고, 화면에서 사용할 지침·예시 입력·기록을 조회하거나 관리합니다."""
import json
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from common.prompt_store import get_prompt, save_prompt
from common.history_store import clear_history, delete_history
from common.state_store import clear_states, delete_state, load_state
from schemas.testboard import PromptInput
from old.services.intent_classifier import PERSONA_PROMPT_FILE, PROMPT_FILE, UNKNOWN_PROMPT_FILE

BASE_DIR = Path(__file__).resolve().parents[2]
router = APIRouter(prefix='/test', tags=['testboard'])
templates = Jinja2Templates(directory=BASE_DIR / 'templates')
















@router.get('/prompt')
def get_intent_prompt():
    """현재 분류에 쓰는 지침을 읽어, 편집기에서 보여 줄 파일명과 내용을 돌려줍니다."""
    try:
        # 1. 결과 전달: Jev 함수가 사용하는 같은 프롬프트 파일을 편집기에 보여 줍니다.
        content = get_prompt(PROMPT_FILE)

        return {'prompt_file': PROMPT_FILE, 'content': content}
    except Exception:
        # 2. 조회 실패: 모델 지침을 가져오지 못하면, 내용을 읽을 수 없다는 HTTP 500 응답을 보냅니다.

        return JSONResponse(status_code=500, content={'detail': '프롬프트 파일을 읽을 수 없습니다.'})


@router.get('/prompts')
def get_intent_prompts():
    """분류와 확인 질문 생성에 쓰는 세 가지 지침을 읽어, 파일명과 내용을 함께 돌려줍니다."""

    # 1. 지침 조회: 실제 모델이 사용하는 세 가지 프롬프트를 함께 돌려줍니다.

    return {
        'jev': {'prompt_file': PROMPT_FILE, 'content': get_prompt(PROMPT_FILE)},
        'persona': {'prompt_file': PERSONA_PROMPT_FILE, 'content': get_prompt(PERSONA_PROMPT_FILE)},
        'unknown': {'prompt_file': UNKNOWN_PROMPT_FILE, 'content': get_prompt(UNKNOWN_PROMPT_FILE)},
    }


@router.put('/prompt')
def save_intent_prompt(payload: PromptInput):
    """편집기에서 받은 분류 지침을 파일과 메모리에 저장하고, 저장한 내용을 돌려줍니다."""
    try:
        # 1. 지침 저장: 수정한 내용을 파일과 메모리에 저장해, 다음 분류 요청부터 사용하게 합니다.
        save_prompt(PROMPT_FILE, payload.content)

        return {'prompt_file': PROMPT_FILE, 'content': payload.content}
    except Exception:
        # 2. 저장 실패: 지침을 저장하지 못하면, 실패했다는 HTTP 500 응답을 보냅니다.

        return JSONResponse(status_code=500, content={'detail': '프롬프트를 저장하지 못했습니다.'})


@router.get('/cases')
def intent_cases():
    """테스트용 파일에서 예시 입력과 예상 의도를 읽어, 화면에 표시할 목록으로 돌려줍니다."""
    try:
        # 1. 기록 관리: 파일에 저장한 예제 입력과 기대 의도를 화면에 전달합니다.
        cases = json.loads((BASE_DIR / 'old/fixtures/intent_cases.json').read_text(encoding='utf-8'))

        return {'cases': cases}
    except Exception:
        # 2. 조회 실패: 예시 파일을 읽거나 JSON을 해석하지 못하면, HTTP 500 응답으로 알립니다.

        return JSONResponse(status_code=500, content={'detail': '테스트 사례를 읽을 수 없습니다.'})




