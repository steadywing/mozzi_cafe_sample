"""고객 문장에서 주문을 읽고 메뉴를 확인한 뒤, 고객의 승인에 따라 테스트 접수를 처리합니다."""
import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from common.client import get_openai_client
from common.customer_store import prepare_customer_state
from common.history_store import load_history
from common.prompt_store import get_prompt
from common.state_store import save_state
from schemas.product_order import OrderDraft
from schemas.session_state import HistoryMessage, IntentResult, OrderState, SessionState

BASE_DIR = Path(__file__).resolve().parents[1]
MENU_FILE = BASE_DIR / 'data' / 'menu.json'
OPTIONS_FILE = BASE_DIR / 'data' / 'order_options.json'
PERSONA_PROMPT_FILE = 'prompts/persona.md'
ORDER_PROMPT_FILE = 'prompts/order_extraction.md'


def load_order_data():
    """저장된 메뉴와 옵션 파일을 읽어, 주문 확인과 금액 계산에 쓸 두 자료를 돌려줍니다."""
    # 1. 자료 조회: 가격과 판매 여부는 모델이 아닌 로컬 원본 데이터에서 확인합니다.
    menu = json.loads(MENU_FILE.read_text(encoding='utf-8'))
    options = json.loads(OPTIONS_FILE.read_text(encoding='utf-8'))

    return menu, options


def get_order_prompt():
    """공통 말투·주문 지침에 메뉴와 옵션 자료를 붙여, 주문 모델에게 보낼 지침을 돌려줍니다."""
    # 1. 지침 조회: 메모리에 보관한 공통 말투와, 주문 내용을 읽을 때 지킬 지침을 가져옵니다.
    persona = get_prompt(PERSONA_PROMPT_FILE)
    role = get_prompt(ORDER_PROMPT_FILE)

    # 2. 참고자료 준비: 모델에는 상품명과 선택지를 제공하고 실제 금액은 코드에서 계산합니다.
    menu, options = load_order_data()
    menu_reference = [
        {key: item[key] for key in ['name', 'aliases', 'temperatures', 'available']}
        for item in menu
    ]

    return (
        f'{persona.strip()}\n\n{role.strip()}\n\n'
        f'## 메뉴 참고자료\n{json.dumps(menu_reference, ensure_ascii=False)}\n\n'
        f'## 옵션 참고자료\n{json.dumps(options, ensure_ascii=False)}'
    )


def create_order_draft(state: SessionState, trace: dict | None = None):
    """고객 입력과 이전 주문 상태를 모델에 보내, 상품·수량·옵션을 정해진 형식의 주문 초안으로 받습니다."""
    # 1. 대화 준비: 지침과 이전 대화 다음에 현재 상태를 전달합니다.
    messages = [{'role': 'system', 'content': get_order_prompt()}]
    messages.extend(message.model_dump(mode='json') for message in state.history)
    messages.append({'role': 'user', 'content': state.model_dump_json(exclude={'history', 'customer'})})

    # 2. 모델 호출: 주문 부분의 JSON만 지정된 스키마로 받습니다.
    model = os.getenv('OPENAI_MODEL', 'gpt-5-nano').strip() or 'gpt-5-nano'
    response = get_openai_client().responses.parse(model=model, input=messages, text_format=OrderDraft)

    # 3. 초안 반환: 모델이 준 주문 내용을 공통 상태 형식으로 옮기고, 실제 코드가 계산할 총액은 비워 둡니다.
    if response.output_parsed is None:
        raise ValueError('주문 초안을 받지 못했습니다.')
    if trace is not None:
        trace.update({'input': messages, 'prompt': messages[0]['content'], 'model': getattr(response, 'model', model)})
    order = OrderState(**response.output_parsed.model_dump(mode='json'))
    order.total_price = None

    return order


def match_menu_and_fill_prices(state: SessionState):
    """상태에 담긴 주문을 실제 메뉴와 비교해 ID·가격을 채우고, 찾지 못한 상품은 확인 질문을 남깁니다."""
    # 1. 기존 값 초기화: 수정된 상품에 이전 ID와 가격이 남지 않도록 비웁니다.
    if state.order is None:

        return state
    state.order.total_price = None
    for item in state.order.items:
        item.product_id = None
        item.price = None

    # 2. 메뉴 대조: 실제 이름과 별칭으로 상품을 찾고 판매 여부를 확인합니다.
    menu, _ = load_order_data()
    menu_by_name = {name: item for item in menu for name in [item['name'], *item.get('aliases', [])]}

    ## 각 주문 상품을 실제 이름 또는 별칭으로 찾아 판매 가능한지 확인합니다.
    for item in state.order.items:
        menu_item = menu_by_name.get(item.product_name)
        if menu_item is None:
            state.order.needs_clarification = True
            state.order.question = f'{item.product_name or "요청하신 상품"}은 메뉴에서 찾을 수 없습니다. 주문할 메뉴를 다시 알려주세요.'

            return state
        if not menu_item['available']:
            state.order.needs_clarification = True
            state.order.question = f'{item.product_name}은 현재 판매하지 않습니다. 다른 메뉴를 선택해 주세요.'

            return state

        # 3. 가격 반영: 모델의 값 대신 실제 메뉴의 ID와 기본 단가를 기록합니다.
        item.product_id = menu_item['menu_id']
        item.product_name = menu_item['name']
        item.price = menu_item['price']

    return state


def check_order(state: SessionState):
    """상태에 담긴 주문의 수량·옵션·필수 정보를 확인해 질문을 돌려주고, 모두 맞으면 None을 돌려줍니다."""
    # 1. 메뉴와 수량 확인: 실제 상품이 확인되지 않았거나 수량이 잘못되면 질문합니다.
    order = state.order
    if order is None:

        return '어떤 메뉴를 주문하시겠어요?'
    if not order.items:

        return order.question or '어떤 메뉴를 주문하시겠어요?'

    ## 주문 항목이 있으면 실제 메뉴와 옵션 자료를 읽어 상품별 검사를 준비합니다.
    menu, option_reference = load_order_data()
    menu_by_id = {item['menu_id']: item for item in menu}
    missing = []
    for item in order.items:
        if item.product_id is None or item.price is None:

            return order.question or '주문할 메뉴를 다시 알려주세요.'

        ## 상품 정보가 확인되면 수량과 실제 메뉴 존재 여부를 점검합니다.
        if item.quantity is None or item.quantity <= 0 or not float(item.quantity).is_integer():

            return f'{item.product_name}는 몇 개로 주문하시겠어요? 양의 정수로 알려주세요.'
        menu_item = menu_by_id.get(item.product_id)
        if menu_item is None:

            return '주문할 메뉴를 다시 확인해 주세요.'

        # 2. 상품별 정보 확인: 온도와 옵션을 확인하고 지원하지 않는 조합은 접수하지 않습니다.
        if menu_item['temperatures'] and item.temperature not in menu_item['temperatures']:
            missing.append(f'{item.product_name} 온도({", ".join(menu_item["temperatures"])})')
        elif not menu_item['temperatures'] and item.temperature is not None:

            return f'{item.product_name}은 온도를 선택하지 않는 상품입니다. 주문 내용을 확인해 주세요.'

        ## 옵션 누락과 중복, 함께 선택할 수 없는 우유 변경을 확인합니다.
        if item.options is None:
            missing.append(f'{item.product_name} 옵션 추가 여부(없으면 없음)')
            continue
        if len(item.options) != len(set(item.options)):

            return f'{item.product_name}에 같은 옵션이 중복되어 있습니다. 적용할 옵션을 다시 알려주세요.'
        if '두유로 변경' in item.options and '오트 음료로 변경' in item.options:

            return f'{item.product_name}의 우유 변경은 두유 또는 오트 음료 중 하나를 선택해 주세요.'

        ## 각 옵션이 이 상품에 허용된 선택지인지 원본 자료로 확인합니다.
        for option in item.options:
            allowed = option_reference.get(option)
            if allowed is None or item.product_id not in allowed['menu_ids']:

                return f'{item.product_name}에는 {option} 옵션을 적용할 수 없습니다. 옵션을 다시 선택해 주세요.'

    # 3. 이용·결제 확인: 매장·포장과 결제 방식의 누락, 모델이 표시한 모호함을 확인합니다.
    if order.order_type is None:
        missing.append('매장 이용 또는 포장')
    if order.payment_method is None:
        missing.append('결제 방식(카드, 현금, 간편결제)')
    if missing:

        return '주문을 위해 ' + ', '.join(missing) + '을 알려주세요.'
    if order.needs_clarification:

        return order.question or '주문에서 확인이 필요한 내용을 다시 알려주세요.'

    return None


def place_order(state: SessionState):
    """주문을 다시 확인하고 실제 가격으로 합계를 계산해, 실제 결제 없이 테스트 주문번호와 금액을 돌려줍니다."""
    # 1. 접수 전 확인: 실제 자료로 상품과 옵션을 다시 확인합니다.
    match_menu_and_fill_prices(state)
    question = check_order(state)
    if question:
        raise ValueError(question)

    # 2. 금액 계산: 상품 기본가에 옵션 가격을 더한 뒤 수량을 곱해, 주문 전체 금액을 계산합니다.
    _, options = load_order_data()
    total_price = 0
    for item in state.order.items:
        option_price = sum(options[name]['price'] for name in item.options)
        total_price += (item.price + option_price) * int(item.quantity)

    # 3. 테스트 결과: 실제 주문 저장이나 결제는 하지 않고, 연습용 주문번호·금액·접수 상태를 돌려줍니다.

    return {'order_id': f'test-{uuid4().hex[:12]}', 'total_price': total_price, 'status': 'accepted'}


def run_product_order(payload: SessionState):
    """고객 입력과 주문 상태를 받아 확인·수정·테스트 접수를 처리하고, 기록을 저장한 뒤 새 상태를 돌려줍니다."""
    # 1. 상태 준비: 받은 상태를 복사해 서버 고객 자료를 채우고, 해당 세션의 이전 대화를 읽습니다.
    started_at = perf_counter()
    state = prepare_customer_state(payload)
    if state.input is None:
        raise ValueError('고객 입력이 필요합니다.')

    ## 세션 식별자를 준비하고 해당 고객의 이전 대화를 복원합니다.
    state.session_id = state.session_id or str(uuid4())
    history = load_history(state.customer_id, state.session_id)
    state.history = [HistoryMessage.model_validate(message) for message in history]
    steps = [{'step': 'input', 'input': state.input.model_dump(mode='json'), 'state': state.model_dump(mode='json')}]

    ## 이번 턴의 의도와 답변을 준비하고 승인 여부를 비교할 문장을 만듭니다.
    state.intent = IntentResult(intent='product_order', confidence=None)
    state.answer = None
    text = state.input.text.strip().lower()

    # 2. 완료·최종 승인: 접수 완료와 수정 대기를 구분하고 yes일 때만 접수합니다.
    if state.order and state.order.confirmation_status == 'confirmed':
        state.answer = {'answer': '이미 테스트 접수된 주문입니다. 새로운 주문은 새 대화에서 시작해 주세요.'}
    elif state.order and text == 'yes':
        if state.order.confirmation_status == 'awaiting_revision':
            state.answer = {'answer': '먼저 수정할 내용을 알려주세요. 새 주문 내용을 확인한 뒤 접수하겠습니다.'}
        else:
            ## 수정 대기가 아니면 실제 메뉴와 필수 정보를 다시 확인한 뒤 접수합니다.
            menu, options = load_order_data()
            reference_data = {'menu_file': MENU_FILE.name, 'menu_count': len(menu), 'options_file': OPTIONS_FILE.name, 'option_count': len(options)}
            match_input = {'order': state.order.model_dump(mode='json'), **reference_data}
            match_menu_and_fill_prices(state)
            steps.append({'step': 'match_menu_and_fill_prices', 'input': match_input, 'state': state.model_dump(mode='json')})
            check_input = {'order': state.order.model_dump(mode='json'), **reference_data}
            question = check_order(state)
            steps.append({'step': 'check_order', 'input': check_input, 'output': {'question': question}, 'state': state.model_dump(mode='json')})
            if question:
                state.answer = {'answer': question}
            else:
                ## 테스트 접수 결과에 따라 주문번호와 금액 또는 실패 안내를 채웁니다.
                place_input = {'order': state.order.model_dump(mode='json'), **reference_data}
                receipt = place_order(state)
                if receipt['status'] == 'accepted':
                    state.order.confirmation_status = 'confirmed'
                    state.order.order_id = receipt['order_id']
                    state.order.total_price = receipt['total_price']
                    state.answer = {'answer': f'테스트 주문번호 {state.order.order_id}, 결제금액 {state.order.total_price:,}원입니다.'}
                else:
                    state.answer = {'answer': '주문을 접수하지 못했습니다. 다시 시도해 주세요.'}
                steps.append({'step': 'place_order', 'input': place_input, 'output': receipt, 'state': state.model_dump(mode='json')})

    # 3. 수정 요청: 확인을 거절하면 새 수정 문장을 받기 전까지 접수를 막습니다.
    elif state.order and text == 'no':
        menu, options = load_order_data()
        reference_data = {'menu_file': MENU_FILE.name, 'menu_count': len(menu), 'options_file': OPTIONS_FILE.name, 'option_count': len(options)}
        match_input = {'order': state.order.model_dump(mode='json'), **reference_data}
        match_menu_and_fill_prices(state)
        steps.append({'step': 'match_menu_and_fill_prices', 'input': match_input, 'state': state.model_dump(mode='json')})
        check_input = {'order': state.order.model_dump(mode='json'), **reference_data}
        question = check_order(state)
        steps.append({'step': 'check_order', 'input': check_input, 'output': {'question': question}, 'state': state.model_dump(mode='json')})
        if question:
            state.answer = {'answer': question}
        else:
            revision_input = {'text': state.input.text, 'order': state.order.model_dump(mode='json')}
            state.order.confirmation_status = 'awaiting_revision'
            state.answer = {'answer': '어떤 내용을 수정할까요? 변경할 상품이나 주문 정보를 알려주세요.'}
            steps.append({'step': 'awaiting_revision', 'input': revision_input, 'state': state.model_dump(mode='json')})

    # 4. 초안 갱신: 새 문장에서 추출한 주문을 실제 메뉴와 대조하고 필수 정보를 확인합니다.
    else:
        model_trace = {}
        state.order = create_order_draft(state, model_trace)
        steps.append({'step': 'create_order_draft', 'state': state.model_dump(mode='json'), **model_trace})
        menu, options = load_order_data()
        reference_data = {'menu_file': MENU_FILE.name, 'menu_count': len(menu), 'options_file': OPTIONS_FILE.name, 'option_count': len(options)}
        steps[-1]['data'] = reference_data
        match_input = {'order': state.order.model_dump(mode='json') if state.order else None, **reference_data}
        match_menu_and_fill_prices(state)
        steps.append({'step': 'match_menu_and_fill_prices', 'input': match_input, 'state': state.model_dump(mode='json')})
        check_input = {'order': state.order.model_dump(mode='json') if state.order else None, **reference_data}
        question = check_order(state)
        if question:
            state.answer = {'answer': question}
        else:
            ## 누락 정보가 없으면 상품별 옵션과 이용·결제 정보를 묶어 확인을 요청합니다.
            lines = []
            for item in state.order.items:
                temperature = {'HOT': '따뜻한', 'ICE': '아이스'}.get(item.temperature, '')
                options = ', '.join(item.options) if item.options else '없음'
                lines.append(f'{temperature} {item.product_name} {int(item.quantity)}개 / 옵션: {options}'.strip())
            summary = '\n'.join(lines) + f'\n이용: {state.order.order_type} / 결제: {state.order.payment_method}'
            state.answer = {'answer': summary + '\n추가·수정할 내용이 없으면 이대로 주문할까요? yes / no로 답해 주세요.'}
        steps.append({'step': 'check_order', 'input': check_input, 'output': {'question': question}, 'state': state.model_dump(mode='json')})

    # 5. 기록 저장: 단계별 상태와 처리 시간을 저장한 뒤 갱신한 상태를 돌려줍니다. 대화 문장 저장은 별도 API가 맡습니다.
    steps.append({'step': 'response', 'input': {'order': state.order.model_dump(mode='json') if state.order else None, 'question': state.answer}, 'state': state.model_dump(mode='json')})
    elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
    save_state(state.customer_id, state.session_id, {'steps': steps, 'elapsed_ms': elapsed_ms})

    return state.model_dump(mode='json')
