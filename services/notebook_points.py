"""샘플 영수증을 읽고 가상 포인트를 검증·적립하는 실습을 실행합니다."""
import base64
import json
import os
from pathlib import Path
from threading import Lock
from time import perf_counter

from openai import OpenAI
from common.prompt_store import get_prompt
from schemas.session_state import CustomerInput, CustomerProfile, ReceiptState, SessionState

BASE_DIR = Path(__file__).resolve().parents[1]
SAMPLES = {f'receipt-{i:03d}': BASE_DIR / 'data' / 'sample_receipts' / f'receipt-{i:03d}.png' for i in range(1, 4)}
SAMPLES.update({f'mochi-receipt-{i:02d}': BASE_DIR / 'tests' / 'fixtures' / 'receipt_samples' / f'mochi-receipt-{i:02d}.png' for i in range(1, 4)})
CASES = [
    {'sample': 'mochi-receipt-01', 'title': '회원 주문과 일치', 'customer_id': 'cust_001', 'expected': '주문과 결제금액 일치'},
    {'sample': 'mochi-receipt-02', 'title': '비회원 주문', 'customer_id': 'cust_001', 'expected': '고객 주문 불일치'},
    {'sample': 'mochi-receipt-03', 'title': '다른 회원의 주문', 'customer_id': 'cust_005', 'expected': '주문과 결제금액 일치'},
]
sessions = {}
processed_receipts = set()
lock = Lock()


def generate_receipt_data(state: SessionState, sample: str):
    """허용된 샘플 영수증을 Gemini로 읽어 상태에 항목을 채워 돌려줍니다."""
    # 1. 사진 준비: 서버가 정한 샘플 파일과 영수증 읽기 지침을 사용합니다.
    path = SAMPLES[sample]
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    prompt = get_prompt('prompts/receipt_to_json.md')
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash').strip() or 'gemini-2.5-flash'

    # 2. 영수증 판독: 샘플 사진과 지침을 보내고 형식이 맞는 항목만 보관합니다.
    client = OpenAI(api_key=os.environ['GEMINI_API_KEY'], base_url='https://generativelanguage.googleapis.com/v1beta/openai/')
    try:
        response = client.chat.completions.create(model=model, response_format={'type': 'json_object'}, messages=[{'role': 'user', 'content': [{'type': 'text', 'text': prompt}, {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{encoded}'}}]}])
        receipt = json.loads(response.choices[0].message.content)
    finally:
        client.close()

    ## 판독 항목 중 형식이 맞는 값만 골라 확인 전 영수증 상태에 담습니다.
    state.receipt = ReceiptState(image_path=str(path), store_name=receipt.get('store_name') if isinstance(receipt.get('store_name'), str) else None, receipt_number=receipt.get('receipt_number') if isinstance(receipt.get('receipt_number'), str) else None, purchased_at=receipt.get('purchased_at') if isinstance(receipt.get('purchased_at'), str) else None, payment_amount=receipt.get('payment_amount') if type(receipt.get('payment_amount')) is int and receipt['payment_amount'] >= 0 else None, status='pending')

    return state, {'prompt': prompt, 'model': model, 'input': {'sample': sample}}


def validate_receipt(state: SessionState, orders: list):
    """영수증과 가상 주문을 비교해 적립 가능 여부와 이유를 상태에 담습니다."""
    # 1. 영수증 확인: 매장, 번호, 금액, 현재 고객과 중복 여부를 검사합니다.
    receipt = state.receipt
    if receipt.store_name != '모찌카페' or not receipt.receipt_number or receipt.payment_amount is None or receipt.payment_amount <= 0:
        receipt.verification, receipt.reason = 'failed', '매장명, 주문번호 또는 결제금액을 확인해 주세요.'
    elif state.customer is None or state.customer.points is None:
        receipt.verification, receipt.reason = 'failed', '고객과 현재 포인트를 확인해 주세요.'

    ## 기본 정보가 맞으면 중복 적립과 실제 고객 주문의 일치 여부를 확인합니다.
    elif receipt.receipt_number in processed_receipts:
        receipt.verification, receipt.reason = 'failed', '이미 적립한 영수증입니다.'
    elif any(item['order_id'] == receipt.receipt_number and item['customer_id'] == state.customer.customer_id and item['total_price'] == receipt.payment_amount for item in orders):
        receipt.verification, receipt.reason = 'passed', '주문과 결제금액이 일치합니다.'
    else:
        receipt.verification, receipt.reason = 'failed', '일치하는 고객 주문과 결제금액을 찾지 못했습니다.'

    return state


def request_receipt_confirmation(state: SessionState):
    """검증 결과를 받아 고객에게 확인할 주문번호와 금액을 안내합니다."""
    # 1. 확인 문장: 검증된 영수증만 고객에게 확인받습니다.
    receipt = state.receipt
    message = f'주문번호 {receipt.receipt_number}, 결제금액 {receipt.payment_amount:,}원이 맞나요?' if receipt.verification == 'passed' else receipt.reason or '영수증을 확인해 주세요.'
    state.answer = {'text': message, 'model': '확인 안내'}

    return state


def add_receipt_points(state: SessionState, confirmed: bool, points_to_add: int):
    """검증 상태와 고객 확인을 받아 가상 포인트를 중복 없이 갱신합니다."""
    # 1. 적립 조건: 저장된 검증과 고객 확인, 중복 여부를 다시 확인합니다.
    receipt = state.receipt
    receipt.customer_confirmed = confirmed
    if receipt.status == 'completed' or receipt.receipt_number in processed_receipts:
        receipt.status, receipt.reason = 'failed', '이미 적립한 영수증입니다.'
    elif receipt.verification != 'passed' or not confirmed:
        receipt.status, receipt.reason = 'failed', '검증과 고객 확인이 필요합니다.'
    elif type(points_to_add) is not int or points_to_add <= 0:
        receipt.status, receipt.reason = 'failed', '연습에 사용할 적립 포인트를 지정해 주세요.'
    else:
        # 2. 가상 적립: 파일을 변경하지 않고 세션 잔액과 처리 목록만 갱신합니다.
        state.customer.points += points_to_add
        processed_receipts.add(receipt.receipt_number)
        receipt.status, receipt.points_to_add, receipt.reason = 'completed', points_to_add, '테스트 포인트를 적립했습니다.'

    return state


def format_point_result(state: SessionState):
    """적립 상태를 받아 성공 결과나 실패 이유를 안내 문장에 담습니다."""
    # 1. 결과 안내: 실제 가상 잔액이 바뀐 경우에만 적립 결과를 보여줍니다.
    receipt = state.receipt
    message = f'테스트 포인트 {receipt.points_to_add}점을 적립했습니다. 현재 잔액은 {state.customer.points}점입니다.' if receipt.status == 'completed' else receipt.reason or '아직 적립하지 않았습니다.'
    state.answer = {'text': message, 'model': '결과 안내'}

    return state


def start_points(session_id: str, sample: str, customer_id: str):
    """샘플 영수증과 가상 고객을 받아 판독·검증·확인 단계를 실행합니다."""
    # 1. 판독 준비: 허용된 샘플과 0점의 가상 고객으로 새 실습 상태를 만듭니다.
    started = perf_counter()
    state = SessionState(session_id=session_id, customer=CustomerProfile(customer_id=customer_id, points=0), input=CustomerInput(text='이 영수증으로 포인트를 적립해 주세요', has_image=True))
    state, info = generate_receipt_data(state, sample)
    steps = [{'step': 'generate_receipt_data', 'state': state.model_dump(mode='json'), **info, 'input': {**info['input'], 'customer_id': customer_id}}]

    # 2. 주문 확인: 파일을 읽은 뒤 잠금 안에서 중복을 검사하고 확인 대기 상태를 저장합니다.
    orders = json.loads((BASE_DIR / 'data' / 'orders.json').read_text(encoding='utf-8'))
    with lock:
        validation_input = {'receipt': state.receipt.model_dump(mode='json'), 'customer_id': customer_id, 'orders_file': 'data/orders.json', 'order_count': len(orders)}
        state = validate_receipt(state, orders)
        steps.append({'step': 'validate_receipt', 'input': validation_input, 'state': state.model_dump(mode='json')})
        confirmation_input = {'receipt_number': state.receipt.receipt_number, 'payment_amount': state.receipt.payment_amount, 'verification': state.receipt.verification}
        state = request_receipt_confirmation(state)
        steps.append({'step': 'request_receipt_confirmation', 'input': confirmation_input, 'state': state.model_dump(mode='json')})
        sessions[session_id] = state.model_copy(deep=True)

    return {'state': state.model_dump(mode='json'), 'steps': steps, 'elapsed_ms': round((perf_counter() - started) * 1000, 2)}


def confirm_points(session_id: str, confirmed: bool, points_to_add: int):
    """저장된 실습 상태에 고객 확인을 적용하고 가상 적립 결과를 돌려줍니다."""
    # 1. 확인과 적립: 클라이언트 상태 대신 서버에 저장된 영수증으로 중복을 확인합니다.
    with lock:
        if session_id not in sessions:
            raise KeyError('영수증 확인부터 시작해 주세요.')
        state = sessions[session_id].model_copy(deep=True)

        ## 저장된 영수증에 적립 조건을 적용하고 결과 안내까지 같은 세션에 남깁니다.
        point_input = {'confirmed': confirmed, 'points_to_add': points_to_add, 'verification': state.receipt.verification, 'receipt_number': state.receipt.receipt_number, 'current_points': state.customer.points}
        state = add_receipt_points(state, confirmed, points_to_add)
        steps = [{'step': 'add_receipt_points', 'input': point_input, 'state': state.model_dump(mode='json')}]
        response_input = {'status': state.receipt.status, 'points_to_add': state.receipt.points_to_add, 'current_points': state.customer.points}
        state = format_point_result(state)
        steps.append({'step': 'format_point_result', 'input': response_input, 'state': state.model_dump(mode='json')})
        sessions[session_id] = state.model_copy(deep=True)

    return {'state': state.model_dump(mode='json'), 'steps': steps}


def reset_points(session_id: str):
    """지정한 실습 세션을 지우고 삭제 여부를 돌려줍니다."""
    # 1. 세션 삭제: 이미 처리한 영수증 기록은 유지해 재적립을 막습니다.
    with lock:

        return sessions.pop(session_id, None) is not None
