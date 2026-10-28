"""테스트 화면에서 사용할 지침·예시 입력·기록을 조회하거나 관리합니다."""
import json
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from common.prompt_store import get_prompt
from common.history_store import clear_history, delete_history
from common.state_store import clear_states, delete_state, load_state
PERSONA_PROMPT_FILE = 'prompts/persona.md'

BASE_DIR = Path(__file__).resolve().parents[1]
router = APIRouter(prefix='/test/api', tags=['테스트 자료'])


@router.delete('/sessions', summary='전체 세션 기록 초기화', description='파일로 저장된 모든 고객의 대화 기록과 상태 기록 삭제 및 각각의 삭제 파일 수 반환. 의도 분류 실습용 메모리 상태는 삭제 대상에서 제외.')
def clear_session_records():
    """전체 초기화 요청을 받으면 대화·상태 파일을 모두 지우고, 각각 삭제한 파일 수를 돌려줍니다."""
    try:
        # 1. 전체 초기화: 두 기록 저장소의 JSON 파일을 모두 삭제합니다.

        return {'deleted': {
            'history': clear_history(),
            'state': clear_states(),
        }}
    except Exception:
        # 2. 삭제 실패: 기록 파일을 지우다가 오류가 나면, 삭제하지 못했다는 HTTP 500 응답을 보냅니다.

        return JSONResponse(status_code=500, content={'detail': '전체 세션 기록을 초기화하지 못했습니다.'})


@router.delete('/session', summary='선택한 세션 기록 삭제', description='고객 ID와 세션 ID에 해당하는 파일 기반 대화·상태 기록 삭제 및 각각의 삭제 여부 반환.')
def delete_session_records(
    customer_id: str = Query(min_length=1, pattern=r'.*\S.*', description='기록을 삭제할 고객 ID'),
    session_id: str = Query(min_length=1, pattern=r'.*\S.*', description='기록을 삭제할 대화 세션 ID'),
):
    """고객 ID와 세션 ID를 받아 해당 대화·상태 기록을 지우고, 각각 삭제됐는지 돌려줍니다."""
    try:
        # 1. 선택 삭제: 받은 고객 ID와 세션 ID에 해당하는 대화·상태 기록만 지웁니다.

        return {'deleted': {
            'history': delete_history(customer_id, session_id),
            'state': delete_state(customer_id, session_id),
        }}
    except Exception:
        # 2. 삭제 실패: 기록 파일을 지우다가 오류가 나면, 삭제하지 못했다는 HTTP 500 응답을 보냅니다.

        return JSONResponse(status_code=500, content={'detail': '세션 기록을 삭제하지 못했습니다.'})


@router.get('/states', summary='세션 상태 기록 조회', description='고객 ID와 세션 ID에 해당하는 대화의 턴별 저장 상태 목록 반환.')
def get_session_states(
    customer_id: str = Query(min_length=1, pattern=r'.*\S.*', description='기록을 조회할 고객 ID'),
    session_id: str = Query(min_length=1, pattern=r'.*\S.*', description='기록을 조회할 대화 세션 ID'),
):
    """고객 ID와 세션 ID를 받아 해당 대화에서 턴마다 저장한 처리 상태 목록을 돌려줍니다."""
    try:
        # 1. 기록 관리: 선택한 고객과 세션에 저장된 턴별 상태 변화를 그대로 보여 줍니다.

        return {'states': load_state(customer_id, session_id)}
    except Exception:
        # 2. 조회 실패: 상태 파일을 읽지 못하면, 기록을 읽을 수 없다는 HTTP 500 응답을 보냅니다.

        return JSONResponse(status_code=500, content={'detail': '상태 기록을 읽을 수 없습니다.'})


@router.get('/order/prompts', summary='주문 프롬프트 조회', description='주문 처리에 사용하는 공통 말투와 주문 추출 지침의 파일명 및 현재 메모리에 불러온 내용 반환.')
def get_order_prompts():
    """주문 모델에 보내는 공통 말투와 주문 지침을 읽어, 파일명과 내용을 함께 돌려줍니다."""
    # 1. 지침 조회: 모델이 실제로 사용하는 메모리의 프롬프트를 돌려줍니다.

    return {
        'persona': {'prompt_file': PERSONA_PROMPT_FILE, 'content': get_prompt(PERSONA_PROMPT_FILE)},
        'order': {'prompt_file': 'prompts/order_extraction.md', 'content': get_prompt('prompts/order_extraction.md')},
    }


@router.get('/order/cases', summary='주문 테스트 사례 조회', description='주문 테스트 사례 파일에서 화면에 표시할 예시 입력 목록 반환.')
def order_cases():
    """주문 테스트용 파일에서 예시 질문을 읽어, 화면에서 선택할 수 있는 목록으로 돌려줍니다."""
    try:
        # 1. 사례 조회: 상태를 미리 넣지 않은 주문 입력 예제를 읽습니다.
        cases = json.loads((BASE_DIR / 'tests/fixtures/order_cases.json').read_text(encoding='utf-8'))

        return {'cases': cases}
    except Exception:
        # 2. 조회 실패: 예시 파일을 읽거나 JSON을 해석하지 못하면, HTTP 500 응답으로 알립니다.

        return JSONResponse(status_code=500, content={'detail': '주문 테스트 사례를 읽을 수 없습니다.'})


@router.get('/customers', summary='테스트 고객 목록 조회', description='고객 데이터에서 테스트 화면의 고객 선택에 필요한 ID와 이름만 반환.')
def test_customers():
    """고객 파일에서 ID와 이름만 골라, 테스트 화면에서 선택할 고객 목록을 돌려줍니다."""
    try:
        # 1. 결과 전달: 고객 선택에 필요한 식별자와 이름만 화면에 전달합니다.
        customers = json.loads((BASE_DIR / 'data/customers.json').read_text(encoding='utf-8'))

        return {'customers': [{'customer_id': item['customer_id'], 'name': item['name']} for item in customers]}
    except Exception:
        # 2. 조회 실패: 고객 파일을 읽거나 필요한 값을 꺼내지 못하면, HTTP 500 응답으로 알립니다.

        return JSONResponse(status_code=500, content={'detail': '고객 목록을 읽을 수 없습니다.'})


@router.get('/intent-turn/cases', summary='의도 분류 테스트 사례 조회', description='의도 분류 실습의 단일 입력과 연속 대화 사례 목록 반환.')
def intent_turn_cases():
    """의도 분류 실습 사례 파일을 읽어 화면에 표시할 목록을 돌려줍니다."""
    # 1. 사례 조회: 노트북의 단일 입력과 연속 대화 예시를 읽어 전달합니다.
    cases = json.loads((BASE_DIR / 'tests/fixtures/intent_turn_cases.json').read_text(encoding='utf-8'))

    return {'cases': cases}
