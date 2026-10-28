"""상품 주문 노트북의 초안·검증·모의 접수 흐름을 실행합니다."""
import json
import os
from pathlib import Path
from time import perf_counter

from common.client import get_openai_client
from common.prompt_store import get_prompt
from schemas.product_order import OrderDraft
from schemas.session_state import OrderState, SessionState

BASE_DIR = Path(__file__).resolve().parents[1]


def generate_order_draft(state: SessionState, menu, options, trace):
    """고객 주문과 이전 초안을 모델에 보내 주문 초안을 상태에 담아 돌려줍니다."""
    # 1. 입력 준비: 공통 지침과 모델 연결을 준비하고 메뉴·옵션을 대화 입력에 붙입니다.
    persona = get_prompt('prompts/persona.md')
    order_prompt = get_prompt('prompts/order_extraction.md')
    model = os.getenv('OPENAI_MODEL', 'gpt-5-nano').strip() or 'gpt-5-nano'
    client = get_openai_client()

    ## 메뉴 이름과 선택지를 지침에 붙이고 이전 대화 다음에 현재 상태를 전달합니다.
    reference = [{key: item[key] for key in ("name", "aliases", "temperatures", "available")} for item in menu]
    system = f"{persona}\n\n{order_prompt}\n\n## 메뉴 참고자료\n{json.dumps(reference, ensure_ascii=False)}\n\n## 옵션 참고자료\n{json.dumps(options, ensure_ascii=False)}"
    messages = [{"role": "system", "content": system}]
    messages.extend(message.model_dump(mode="json") for message in state.history)
    messages.append({"role": "user", "content": state.model_dump_json(exclude={"history", "customer"})})

    # 2. 모델 호출: 고객이 말한 주문 내용을 정해진 형식으로 추출합니다.
    response = client.responses.parse(model=model, input=messages, text_format=OrderDraft)
    if response.output_parsed is None:
        raise ValueError("주문 초안을 받지 못했습니다.")

    # 3. 실행 기록: 실제로 사용한 지침과 입력, 모델 설정을 테스트보드에 전달합니다.
    trace.update({'prompt': system, 'input': messages, 'model': getattr(response, 'model', model)})

    # 4. 상태 저장: 금액은 추측하지 않고 실제 메뉴 확인 전 상태로 둡니다.
    state.order = OrderState(**response.output_parsed.model_dump(mode="json"))
    state.order.total_price = None

    return state




def validate_order(state: SessionState, menu, options):
    """주문 초안을 메뉴·옵션과 비교해 누락 여부와 확인 질문을 상태에 담아 돌려줍니다."""
    # 1. 주문 확인: 기존 질문이 있거나 주문 항목이 없으면 고객에게 확인합니다.
    order = state.order
    if order is None or not order.items:
        state.answer = {"answer": order.question if order and order.question else "어떤 메뉴를 주문하시겠어요?"}

        return state
    if order.needs_clarification:
        state.answer = {"answer": order.question or "주문 내용을 다시 알려주세요."}

        return state

    # 2. 메뉴 확인: 실제 이름·별칭과 판매 여부를 확인하고 기본 가격을 채웁니다.
    missing = []
    for item in order.items:
        item.product_id = None
        item.price = None
        matches = [entry for entry in menu if item.product_name in [entry["name"], *entry.get("aliases", [])]]
        if not matches or not matches[0]["available"]:
            state.answer = {"answer": f"{item.product_name or '해당 메뉴'}는 주문할 수 없습니다. 다른 메뉴를 알려주세요."}

            return state

        ## 판매 가능한 메뉴가 확인되면 원본 자료의 이름과 가격을 채웁니다.
        selected = matches[0]
        item.product_id = selected["menu_id"]
        item.product_name = selected["name"]
        item.price = selected["price"]

        ## 수량과 온도가 빠졌거나 메뉴와 맞지 않는지 확인합니다.
        if item.quantity is None or item.quantity <= 0 or not float(item.quantity).is_integer():
            missing.append(f"{item.product_name} 수량")
        if selected["temperatures"] and item.temperature not in selected["temperatures"]:
            missing.append(f"{item.product_name} 온도")
        elif not selected["temperatures"] and item.temperature is not None:
            state.answer = {"answer": f"{item.product_name}은 온도 선택이 없습니다."}

            return state

        ## 옵션이 빠졌으면 질문하고 중복되거나 허용되지 않은 조합은 거절합니다.
        if item.options is None:
            missing.append(f"{item.product_name} 옵션 여부")
        else:
            if len(item.options) != len(set(item.options)) or ("두유로 변경" in item.options and "오트 음료로 변경" in item.options):
                state.answer = {"answer": "중복되거나 함께 적용할 수 없는 옵션이 있습니다."}

                return state
            for option in item.options:
                if option not in options or item.product_id not in options[option]["menu_ids"]:
                    state.answer = {"answer": f"{item.product_name}에는 {option} 옵션을 적용할 수 없습니다."}

                    return state

    # 3. 필수 정보 확인: 이용과 결제 정보를 포함해 빠진 내용을 질문합니다.
    if order.order_type is None:
        missing.append("매장 이용 또는 포장")
    if order.payment_method is None:
        missing.append("결제 방식")
    if missing:
        state.answer = {"answer": "주문을 위해 " + ", ".join(missing) + "을 알려주세요."}
    else:
        ## 필수 정보가 모두 있으면 주문 요약을 만들고 고객 확인을 기다립니다.
        order.confirmation_status = "pending"
        summary = ", ".join(f"{item.product_name} {int(item.quantity)}개 ({item.temperature or '온도 없음'}, 옵션: {', '.join(item.options) or '없음'})" for item in order.items)
        state.answer = {"answer": f"{summary} / {order.order_type} / {order.payment_method} 맞나요? yes / no로 답해 주세요."}

    return state

def handle_order(state: SessionState, menu, options):
    """고객 확인 답변과 주문 상태를 받아 승인된 주문만 모의 접수하고 결과를 돌려줍니다."""
    # 1. 확인 상태 검사: 확인 대기 주문과 명시적인 승인 답변이 있어야 접수합니다.
    if state.order is None or state.order.confirmation_status != "pending":
        state.answer = {"answer": "확인할 주문이 없습니다."}

        return state
    if state.input.text.strip().lower() != "yes":
        state.order.confirmation_status = "awaiting_revision"
        state.answer = {"answer": "수정할 주문 내용을 알려주세요."}

        return state

    # 2. 재검증: 승인 시 메뉴와 필수 정보를 다시 확인합니다.
    state = validate_order(state, menu, options)
    if state.order.confirmation_status != "pending" or not state.answer["answer"].endswith("yes / no로 답해 주세요."):

        return state

    # 3. 모의 접수: 실제 주문 저장과 결제 없이 메뉴·옵션 가격으로 금액을 계산합니다.
    from uuid import uuid4
    total = sum((item.price + sum(options[name]["price"] for name in item.options)) * int(item.quantity) for item in state.order.items)
    state.order.order_id = f"test-{uuid4().hex[:12]}"
    state.order.total_price = total
    state.order.confirmation_status = "confirmed"
    state.answer = {"answer": f"테스트 주문번호 {state.order.order_id}, 결제금액 {total:,}원입니다."}

    return state


def run_order(payload: SessionState):
    """고객 상태로 주문 초안을 만들거나 확인한 뒤 단계별 결과를 돌려줍니다."""
    # 1. 자료 준비: 메뉴와 옵션을 읽고 받은 상태를 복사합니다.
    started_at = perf_counter()
    menu = json.loads((BASE_DIR / 'data/menu.json').read_text(encoding='utf-8'))
    options = json.loads((BASE_DIR / 'data/order_options.json').read_text(encoding='utf-8'))
    state = payload.model_copy(deep=True)
    steps = []
    reference_data = {'menu_file': 'data/menu.json', 'menu_count': len(menu), 'options_file': 'data/order_options.json', 'option_count': len(options)}

    # 2. 처리 분기: 확인 대기 상태의 yes 또는 no는 모의 접수 단계로 보냅니다.
    if state.order and state.order.confirmation_status == 'pending' and state.input.text.strip().lower() in ('yes', 'no'):
        step_input = {'text': state.input.text, 'order': state.order.model_dump(mode='json'), **reference_data}
        state = handle_order(state, menu, options)
        steps.append({'step': 'handle_order', 'input': step_input, 'state': state.model_dump(mode='json')})
    else:
        trace = {}
        state = generate_order_draft(state, menu, options, trace)
        steps.append({'step': 'generate_order_draft', 'state': state.model_dump(mode='json'), **trace})
        step_input = {'order': state.order.model_dump(mode='json'), **reference_data}
        state = validate_order(state, menu, options)
        steps.append({'step': 'validate_order', 'input': step_input, 'state': state.model_dump(mode='json')})

    # 3. 결과 반환: 다음 대화에서 이어 쓸 상태와 실제 처리 단계를 돌려줍니다.

    return {'state': state.model_dump(mode='json'), 'steps': steps, 'elapsed_ms': round((perf_counter() - started_at) * 1000, 2)}

