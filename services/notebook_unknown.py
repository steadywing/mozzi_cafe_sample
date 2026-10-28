"""unknown 노트북의 확인 질문 생성 단계를 실행합니다."""
import json
import os
from time import perf_counter

from common.client import get_openai_client
from common.prompt_store import get_prompt
from schemas.session_state import SessionState


def run_unknown(payload: SessionState):
    """고객 입력과 이전 대화를 받아 확인 질문과 모델 실행 정보를 돌려줍니다."""
    # 1. 입력 준비: 공통 말투와 확인 지침, 이전 대화 및 이번 입력을 모델에 전달합니다.
    started_at = perf_counter()
    state = payload.model_copy(deep=True)
    prompt = f"{get_prompt('prompts/persona.md').strip()}\n\n{get_prompt('prompts/unknown_response.md').strip()}"

    ## 공통 지침 뒤에 이전 대화와 현재 입력을 차례로 붙입니다.
    messages = [{'role': 'system', 'content': prompt}]
    messages.extend(message.model_dump(mode='json') for message in state.history)
    current = {'text': state.input.text, 'has_image': state.input.has_image, 'previous_intent': state.previous_intent}
    messages.append({'role': 'user', 'content': json.dumps(current, ensure_ascii=False)})

    # 2. 답변 생성: 실제 모델이 반환한 확인 질문과 모델명을 상태에 저장합니다.
    model = os.getenv('OPENAI_MODEL', 'gpt-5-nano').strip() or 'gpt-5-nano'
    response = get_openai_client().responses.create(model=model, input=messages)
    answer = response.output_text.strip()
    if not answer:
        raise ValueError('모델이 답변을 반환하지 않았습니다.')
    state.answer = {'answer': answer, 'model': response.model}

    # 3. 결과 반환: 노트북의 처리 결과와 실제 모델 입력 및 지침을 보여줍니다.

    return {'state': state.model_dump(mode='json'), 'steps': [{'step': 'generate_unknown_response', 'state': state.model_dump(mode='json'), 'input': messages, 'prompt': prompt, 'model': response.model}], 'elapsed_ms': round((perf_counter() - started_at) * 1000, 2)}
