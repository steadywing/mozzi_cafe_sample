"""추천 조건 추출, 알레르기 필터와 답변 생성을 순서대로 실행합니다."""
import json
import os
from pathlib import Path
from time import perf_counter

from common.client import get_openai_client
from common.prompt_store import get_prompt
from schemas.session_state import RecommendationState

ROOT = Path(__file__).resolve().parents[1]


def ask_model(prompt, model_input, json_output=False):
    """지침과 입력을 받아 OpenAI의 텍스트 또는 JSON 답변을 돌려줍니다."""
    # 1. 모델 호출: 조건 추출일 때만 JSON 형식을 지정합니다.
    options = {'model': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'), 'instructions': prompt, 'input': json.dumps(model_input, ensure_ascii=False)}
    if json_output:
        options['text'] = {'format': {'type': 'json_object'}}

    return get_openai_client().responses.create(**options).output_text


def generate_recommendation_conditions(state):
    """고객 문장과 기존 조건을 받아 추출한 추천 조건을 상태에 담습니다."""
    # 1. 조건 추출: 이전 질문과 조건을 함께 보내 후속 답변을 해석합니다.
    conditions = state.recommendation or RecommendationState()
    model_input = {'text': state.input.text, 'previous_question': state.answer.get('text') if state.answer else None, 'allergies': conditions.allergies, 'preferences': conditions.preferences, 'response_format': 'json'}
    prompt = get_prompt('prompts/recommendation_conditions.md')
    result = json.loads(ask_model(prompt, model_input, True))

    # 2. 상태 갱신: 확인하지 않은 null은 기존 값을 유지합니다.
    for field in ('allergies', 'preferences'):
        value = result.get(field)
        if value is not None:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError('추천 조건은 문자열 목록이어야 합니다.')
            setattr(conditions, field, value)

    ## 조건을 다시 추출했으므로 이전 후보를 비우고 이번 확인 질문을 상태에 담습니다.
    conditions.candidate_menu_ids = None
    conditions.needs_clarification = bool(result.get('needs_clarification'))
    state.recommendation = conditions
    state.answer = {'text': result.get('question') or '', 'model': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}

    return {'input': model_input, 'prompt': prompt}


def filter_recommendation_menu(state, menu):
    """추천 조건과 메뉴를 받아 알레르기와 선호에 맞는 후보를 상태에 담습니다."""
    # 1. 필수 조건 확인: 미확인과 없음은 구분하고 필요한 경우 질문합니다.
    conditions = state.recommendation
    if getattr(conditions, 'needs_clarification', False) and state.answer and state.answer.get('text'):

        return state
    if conditions.allergies is None:
        state.answer = {'text': '피해야 할 알레르기 재료가 있나요?', 'model': 'python'}

        return state
    if conditions.preferences is None:
        state.answer = {'text': '선호하는 맛이나 메뉴가 있나요? 없다면 없다고 알려 주세요.', 'model': 'python'}

        return state

    # 2. 지원 조건 확인: 자료에서 확인할 수 없는 조건은 안전하게 다시 묻습니다.
    known = {item for product in menu for item in (product.get('allergens') or []) + (product.get('ingredients') or [])}
    supported = {tag for product in menu for tag in product.get('tags', [])} | {product['category'] for product in menu} | {'카페인 없음', '카페인 있음', '당도 없음', '당도 낮음', '당도 보통', '당도 높음'}
    if any(item not in known for item in conditions.allergies):
        state.answer = {'text': '알레르기 재료를 매장에서 확인해 주세요.', 'model': 'python'}

        return state
    if any(item not in supported for item in conditions.preferences):
        state.answer = {'text': '알 수 있는 맛이나 메뉴 종류로 선호를 다시 알려 주세요.', 'model': 'python'}

        return state

    # 3. 후보 선택: 알레르기 재료를 먼저 제외하고 모든 선호를 확인합니다.
    candidates = []
    for product in menu:
        if not product.get('available'):
            continue
        if conditions.allergies and (product.get('allergens') is None or product.get('ingredients') is None):
            continue

        ## 판매 가능 여부와 재료 정보가 확인된 메뉴에서 알레르기 재료를 제외합니다.
        ingredients = (product.get('allergens') or []) + (product.get('ingredients') or [])
        if any(allergy in ingredient for allergy in conditions.allergies for ingredient in ingredients):
            continue

        ## 알레르기를 통과한 메뉴는 카페인·당도·분류 등 모든 선호 조건을 확인합니다.
        matches = True
        for preference in conditions.preferences:
            if preference.startswith('카페인 '):
                matches = product.get('caffeine') is (preference == '카페인 있음')
            elif preference.startswith('당도 '):
                matches = product.get('sweetness') == preference.removeprefix('당도 ')
            else:
                matches = preference in product.get('tags', []) or preference == product.get('category')
            if not matches:
                break
        if matches:
            candidates.append(product['menu_id'])

    ## 조건에 맞는 메뉴 ID를 보관하고 후보가 없으면 조건 수정을 안내합니다.
    conditions.candidate_menu_ids = candidates
    state.answer = {'text': '조건에 맞는 메뉴가 없습니다. 선호 조건을 조정해 주세요.' if not candidates else '', 'model': 'python'}

    return state


def generate_recommendation_response(state, menu):
    """조건에 맞는 메뉴 후보를 받아 추천 답변과 사용한 입력을 돌려줍니다."""
    # 1. 후보 확인: 후보가 없으면 기존 확인 질문을 유지합니다.
    if not state.recommendation.candidate_menu_ids:

        return None
    candidates = [product for product in menu if product['menu_id'] in state.recommendation.candidate_menu_ids]
    statistics = state.customer.preferences.model_dump() if state.customer and state.customer.preferences else None
    model_input = {'text': state.input.text, 'conditions': state.recommendation.model_dump(), 'candidates': candidates, 'purchase_statistics': statistics}
    prompt = get_prompt('prompts/recommendation_response.md')

    # 2. 답변 생성: 필터에 통과한 후보만 모델에 전달합니다.
    answer = ask_model(prompt, model_input)
    state.answer = {'text': answer, 'model': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}

    return {'input': model_input, 'prompt': prompt}


def run_recommendation(state):
    """추천 상태를 받아 조건 추출, 필터링과 답변 단계를 돌려줍니다."""
    # 1. 자료 준비: 가상 메뉴와 실행 시간을 확인합니다.
    started = perf_counter()
    menu = json.loads((ROOT / 'data/menu.json').read_text(encoding='utf-8'))
    state = state.model_copy(deep=True)
    if state.input is None:
        raise ValueError('고객 입력이 필요합니다.')

    # 2. 단계 실행: 각 함수의 결과와 실제 모델 입력을 기록합니다.
    detail = generate_recommendation_conditions(state)
    steps = [{'step': 'generate_recommendation_conditions', 'state': state.model_dump(mode='json'), **detail}]

    ## 추출한 조건으로 메뉴를 거른 뒤 남은 후보가 있을 때 추천 답변을 만듭니다.
    filter_input = {'conditions': state.recommendation.model_dump(mode='json'), 'menu_file': 'data/menu.json', 'menu_count': len(menu)}
    filter_recommendation_menu(state, menu)
    steps.append({'step': 'filter_recommendation_menu', 'input': filter_input, 'state': state.model_dump(mode='json'), 'menu_count': len(menu)})
    detail = generate_recommendation_response(state, menu)
    steps.append({'step': 'generate_recommendation_response', 'input': {'candidate_menu_ids': state.recommendation.candidate_menu_ids}, 'state': state.model_dump(mode='json'), 'executed': detail is not None, **(detail or {})})

    return {'state': state.model_dump(mode='json'), 'steps': steps, 'elapsed_ms': round((perf_counter() - started) * 1000, 2)}
