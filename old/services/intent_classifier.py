"""고객이 요청한 기능을 Jev로 분류하고, 구분하기 어려우면 OpenAI로 확인 질문을 만듭니다."""
import json
import os
from time import perf_counter
from uuid import uuid4

from typesafe_sdk import Choice

from common.client import get_jev_client, get_openai_client
from common.customer_store import prepare_customer_state
from common.history_store import load_history
from common.state_store import save_state
from common.prompt_store import get_prompt
from schemas.session_state import HistoryMessage, IntentResult, SessionState

PROMPT_FILE = 'prompts/intent_router.md'
PERSONA_PROMPT_FILE = 'prompts/persona.md'
UNKNOWN_PROMPT_FILE = 'prompts/unknown_response.md'
INTENT_CRITERIA = {
    'product_search': '상품의 이름이나 정체를 알아내거나, 특정 상품을 찾아 후보를 확인하려는 목적이다.',
    'event_participation': '쿠폰·스탬프 인식, 쿠폰 검증 결과 확인·정정, 스탬프 적립이나 혜택 사용을 요청한다.',
    'product_recommendation': '개인 조건에 맞는 상품을 고르거나 추천받으려는 요청 또는 진행 중인 추천의 알레르기·취향·선호에 대한 답변이다.',
    'product_consultation': '카페의 운영시간·위치·시설·이용 방법 등 카페 정보를 알아보려는 목적이다.',
    'product_order': '상품·수량·옵션을 주문하거나 진행 중인 주문 초안을 확인·수정한다.',
    'unknown': '어느 의도에도 맞지 않거나 맥락이 부족해 구분하기 어렵다. 여러 요청 중 먼저 처리할 것을 정할 수 없다.',
}

def classify_intent(state: SessionState):
    """고객 입력과 대화 상태를 Jev에 보내, 요청한 기능의 이름과 분류 신뢰도를 돌려줍니다."""

    # 1. 입력 준비: 고객 입력과 대화 상태를 분류 모델에 전달할 자료로 묶습니다.
    user_input = {
        'text': state.input.text,
        'has_image': state.input.has_image,
        'session_state': state.model_dump(mode='json', exclude_unset=True, exclude={'input', 'history', 'customer'}),
        'history': [message.model_dump(mode='json') for message in state.history],
    }

    # 2. 분류 지침: 테스트보드에서 저장한 최신 지침을 메모리에서 읽습니다.
    prompt = get_prompt(PROMPT_FILE)

    # 3. 모델 호출: 분류 지침과 선택지를 Jev에 보내 고객 입력의 의도를 판단합니다.
    questions = {'intent': Choice(instructions=prompt, criteria=INTENT_CRITERIA)}
    response = get_jev_client().system_one(state=user_input, questions=questions)

    # 4. 결과 확인: 선택한 의도와 신뢰도를 꺼내고 신뢰도가 있는지 확인합니다.
    result = response.model_dump(mode='json')['answers']['intent']
    intent = IntentResult(intent=result['choice'], confidence=result['confidence'])
    if intent.confidence is None:
        raise ValueError('모델이 신뢰도를 반환하지 않았습니다.')

    return intent.model_dump(mode='json')


def generate_unknown_response(state: SessionState):
    """분류하기 어려운 고객 입력과 이전 대화를 OpenAI에 보내, 확인 질문과 모델명을 돌려줍니다."""

    # 1. 지침 조회: 챗봇의 공통 말투와, 고객에게 다시 물어볼 때 지킬 지침을 읽습니다.
    persona = get_prompt(PERSONA_PROMPT_FILE)
    role_prompt = get_prompt(UNKNOWN_PROMPT_FILE)

    # 2. 지침 결합: 공통 말투 뒤에 확인 질문 역할의 지침을 붙입니다.
    prompt = f'{persona.strip()}\n\n{role_prompt.strip()}'

    # 3. 대화 준비: 지침 뒤에 이전 대화를 역할별로 넣고 이번 요청을 마지막에 추가합니다.
    messages = [{'role': 'system', 'content': prompt}]
    messages.extend(message.model_dump(mode='json') for message in state.history)
    current_input = {
        'text': state.input.text,
        'has_image': state.input.has_image,
        'session_state': state.model_dump(mode='json', exclude_unset=True, exclude={'input', 'history', 'customer'}),
    }
    messages.append({'role': 'user', 'content': json.dumps(current_input, ensure_ascii=False)})

    # 4. 모델 호출: 환경에 설정한 OpenAI 모델에 준비한 대화를 전달합니다.
    model = os.getenv('OPENAI_MODEL', 'gpt-5-nano').strip() or 'gpt-5-nano'
    response = get_openai_client().responses.create(
        model=model,
        input=messages,
    )

    # 5. 결과 확인: 생성한 답변과 실제 모델명을 반환하며 빈 답변은 오류로 처리합니다.
    answer = response.output_text.strip()
    if not answer:
        raise ValueError('모델이 답변을 반환하지 않았습니다.')

    return {'answer': answer, 'model': response.model}


def run_intent_classifier(payload: SessionState):
    """받은 대화 상태를 복사해 요청을 분류하고, 처리 기록을 저장한 뒤 갱신한 상태를 돌려줍니다."""

    # 1. 상태 준비: 받은 상태를 복사해 서버의 고객 자료를 채우고, 세션 ID가 없으면 새로 만듭니다.
    started_at = perf_counter()
    state = prepare_customer_state(payload)
    if state.input is None:
        raise ValueError('고객 입력이 필요합니다.')
    state.session_id = state.session_id or str(uuid4())

    # 2. 기록 준비: 고객·세션 ID로 이전 대화를 읽고, 분류 전 상태를 복사해 첫 처리 기록으로 남깁니다.
    history = load_history(state.customer_id, state.session_id)
    state.history = [HistoryMessage.model_validate(message) for message in history]
    steps = [{'step': 'input', 'state': state.model_dump(mode='json')}]

    # 3. 의도 분류: 작업이 확인되면 갱신하고 분류 보류라면 기존 의도를 유지합니다.
    classification = IntentResult(**classify_intent(state))
    if classification.intent != 'unknown':
        state.intent = classification
    state.answer = None
    steps.append({'step': 'classify_intent', 'state': state.model_dump(mode='json')})

    # 4. 확인 질문: 이번 입력의 의도를 구분하지 못했을 때만 질문을 만들고, 그 결과를 상태에 넣습니다.
    if classification.intent == 'unknown':
        state.answer = generate_unknown_response(state)
        steps.append({'step': 'generate_unknown_response', 'state': state.model_dump(mode='json')})

    # 5. 기록 저장: 단계별 상태와 저장 전까지 걸린 시간을 파일에 남기고, 갱신한 상태를 돌려줍니다. 대화 문장 저장은 별도 API가 맡습니다.
    elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
    save_state(state.customer_id, state.session_id, {'steps': steps, 'elapsed_ms': elapsed_ms})

    return state.model_dump(mode='json', exclude_none=True)
