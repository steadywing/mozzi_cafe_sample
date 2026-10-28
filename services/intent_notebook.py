"""노트북의 상태 준비·의도 분류·저장 흐름을 서버 메모리에서 실행합니다."""
import json
import os
from threading import Lock
from time import perf_counter

from typesafe_sdk import Choice

from common.client import get_jev_client, get_openai_client
from common.notebook_step_store import clear_trace, record_result
from common.prompt_store import get_prompt
from schemas.session_state import CustomerRequest, HistoryMessage, IntentResult, SessionState

PROMPT_FILE = 'prompts/intent_router.md'
PERSONA_PROMPT_FILE = 'prompts/persona.md'
UNKNOWN_PROMPT_FILE = 'prompts/unknown_response.md'
INTENT_CRITERIA = {
    'product_search': '상품의 이름이나 정체를 알아내거나, 특정 상품을 찾아 후보를 확인하려는 목적이다.',
    'point_accumulation': '영수증의 결제 내역으로 포인트를 적립하거나 적립 내용을 확인한다.',
    'product_recommendation': '개인 조건에 맞는 상품을 고르거나 추천받으려는 요청 또는 진행 중인 추천의 알레르기·취향·선호에 대한 답변이다.',
    'product_consultation': '카페의 운영시간·위치·시설·이용 방법 등 카페 정보를 알아보려는 목적이다.',
    'product_order': '상품·수량·옵션을 주문하거나 진행 중인 주문 초안을 확인·수정한다.',
    'unknown': '어느 의도에도 맞지 않거나 맥락이 부족해 구분하기 어렵다. 여러 요청 중 먼저 처리할 것을 정할 수 없다.',
}

# 서버 프로세스에서만 유지하며 서버 재시작 시 초기화됩니다.
state_store = {}
state_lock = Lock()


def prepare_state(request: CustomerRequest):
    """고객 요청으로 마지막 세션 상태를 복원하고 이번 입력과 대화 기록을 채워 돌려줍니다."""
    # 1. 상태 복원: 저장된 마지막 스냅샷이 있으면 복원하고 없으면 새 상태를 만듭니다.
    snapshots = state_store.get(request.session_id, [])
    if snapshots:
        state = SessionState.model_validate(snapshots[-1])
        state.previous_intent = state.intent.intent if state.intent else None
        state.intent = None
        state.answer = None
        state.input = request.input

        ## 이번 요청에 고객 정보가 있을 때만 이전 정보를 바꿉니다.
        if request.customer_info is not None:
            state.customer = request.customer_info
    else:
        state = SessionState(session_id=request.session_id, customer=request.customer_info, input=request.input)

    # 2. 입력 기록: 이번 고객 문장을 기록에 추가해 갱신된 상태를 돌려줍니다.
    state.history.append(HistoryMessage(role='user', content=request.input.text))

    return state


def classify_intent(state: SessionState, prompt: str | None = None):
    """이번 입력과 이전 의도를 Jev로 분류하고 결과를 채운 상태를 돌려줍니다."""
    # 1. 모델 입력: 고객 정보와 기록을 제외한 세 값만 전달합니다.
    user_input = {'text': state.input.text, 'previous_intent': state.previous_intent, 'has_image': state.input.has_image}
    prompt = prompt if prompt is not None else get_prompt(PROMPT_FILE)

    # 2. 모델 호출: 매 턴 현재 문장을 여섯 가지 의도 중 하나로 분류합니다.
    questions = {'intent': Choice(instructions=prompt, criteria=INTENT_CRITERIA)}
    response = get_jev_client().system_one(state=user_input, questions=questions)
    result = response.model_dump(mode='json')['answers']['intent']
    state.intent = IntentResult(intent=result['choice'], confidence=result['confidence'])
    if state.intent.confidence is None:
        raise ValueError('Jev가 신뢰도를 반환하지 않았습니다.')

    return state


def generate_unknown_response(state: SessionState):
    """분류하기 어려운 고객 요청과 앞선 대화를 받아 확인 답변과 실행 정보를 돌려줍니다."""
    # 1. 지침 준비: 공통 말투와 의도를 확인하는 역할 지침을 함께 사용합니다.
    persona = get_prompt(PERSONA_PROMPT_FILE)
    unknown_prompt = get_prompt(UNKNOWN_PROMPT_FILE)
    prompt = f'{persona.strip()}\n\n{unknown_prompt.strip()}'

    # 2. 입력 준비: 이번 고객 문장은 history의 마지막 항목이므로 이전 대화만 먼저 넣습니다.
    messages = [{'role': 'system', 'content': prompt}]
    messages.extend(message.model_dump(mode='json') for message in state.history[:-1])
    current_input = {
        'text': state.input.text,
        'previous_intent': state.previous_intent,
        'has_image': state.input.has_image,
    }
    messages.append({'role': 'user', 'content': json.dumps(current_input, ensure_ascii=False)})

    # 3. 답변 생성: 설정한 OpenAI 모델에 대화와 현재 입력을 보내 확인 질문을 만듭니다.
    model = os.getenv('OPENAI_MODEL', 'gpt-5-nano').strip() or 'gpt-5-nano'
    response = get_openai_client().responses.create(model=model, input=messages)
    answer = response.output_text.strip()
    if not answer:
        raise ValueError('모델이 답변을 반환하지 않았습니다.')

    # 4. 결과 반환: 고객에게 보일 답변과 실제 모델·입력·지침을 함께 돌려줍니다.

    return {'answer': answer, 'model': response.model, 'prompt': prompt, 'input': messages}


def save_state(state: SessionState):
    """처리한 상태를 세션 목록에 저장하고 연속된 같은 스냅샷은 중복하지 않습니다."""
    # 1. 스냅샷 저장: 마지막 상태와 다를 때만 독립된 JSON 자료를 목록에 추가합니다.
    snapshots = state_store.setdefault(state.session_id, [])
    snapshot = state.model_dump(mode='json')
    if not snapshots or snapshots[-1] != snapshot:
        snapshots.append(snapshot)

    return state


def run_turn(request: CustomerRequest):
    """고객 요청을 준비·분류·저장하고 각 단계와 실행 정보를 돌려줍니다."""
    # 1. 실행 준비: 실제로 사용할 프롬프트와 시작 시각을 기록합니다.
    started_at = perf_counter()
    prompt = get_prompt(PROMPT_FILE)

    # 2. 한 턴 처리: 같은 세션의 요청이 겹쳐도 앞선 저장 결과부터 이어갑니다.
    with state_lock:
        state = prepare_state(request)
        steps = [{'step': 'prepare_state', 'input': request.model_dump(mode='json'), 'state': state.model_dump(mode='json')}]

        ## 복원한 상태를 매 턴 분류하고 분류 직후 상태를 기록합니다.
        classify_input = {'text': state.input.text, 'previous_intent': state.previous_intent, 'has_image': state.input.has_image}
        state = classify_intent(state, prompt)
        steps.append({'step': 'classify_intent', 'input': classify_input, 'prompt': prompt, 'model': os.getenv('TYPESAFE_MODEL', 'jev-latest').strip() or 'jev-latest', 'state': state.model_dump(mode='json')})

        ## 의도를 정하지 못한 요청에는 확인 답변을 생성하고 대화에 남깁니다.
        if state.intent.intent == 'unknown':
            generated = generate_unknown_response(state)
            state.answer = {'answer': generated['answer'], 'model': generated['model']}
            state.history.append(HistoryMessage(role='assistant', content=generated['answer']))
            steps.append({
                'step': 'generate_unknown_response',
                'state': state.model_dump(mode='json'),
                'prompt': generated['prompt'],
                'input': generated['input'],
                'model': generated['model'],
            })

        ## 답변까지 반영한 최종 상태를 다음 요청에 이어 쓸 수 있도록 저장합니다.
        state = save_state(state)
        steps.append({'step': 'save_state', 'input': {'session_id': state.session_id, 'intent': state.intent.model_dump(mode='json')}, 'state': state.model_dump(mode='json')})

        ## 이번 실행의 모든 단계 스냅샷을 턴별 조회 기록에도 보관합니다.
        result = record_result('intent', request.session_id, {
            'state': state.model_dump(mode='json'),
            'steps': steps,
            'model': os.getenv('TYPESAFE_MODEL', 'jev-latest').strip() or 'jev-latest',
            'prompt': prompt,
            'elapsed_ms': round((perf_counter() - started_at) * 1000, 2),
        })

    # 3. 결과 반환: 단계별 상태와 실제 지침, 설정된 모델, 처리 시간을 함께 보여줍니다.

    return result


def reset_session(session_id: str):
    """세션 ID에 해당하는 메모리 상태를 지우고 삭제 여부를 돌려줍니다."""
    # 1. 상태 삭제: 턴 처리와 겹치지 않게 잠근 뒤 선택한 세션만 지웁니다.
    with state_lock:
        deleted = state_store.pop(session_id, None) is not None
        clear_trace('intent', session_id)

    return deleted
