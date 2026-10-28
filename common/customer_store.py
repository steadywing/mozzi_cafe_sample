"""고객 ID로 서버 자료를 읽어 프로필과 구매 통계를 만들고, 대화 상태에 채웁니다."""
import json
from pathlib import Path

from schemas.session_state import CustomerProfile, PurchaseStatistics, RecommendationState, SessionState

CUSTOMERS_FILE = Path(__file__).resolve().parents[1] / 'data' / 'customers.json'
ORDERS_FILE = Path(__file__).resolve().parents[1] / 'data' / 'orders.json'
MENU_FILE = Path(__file__).resolve().parents[1] / 'data' / 'menu.json'


def calculate_purchase_statistics(customer_id: str | None, orders: list[dict], menu: list[dict]) -> PurchaseStatistics:
    """고객 ID와 주문·메뉴 목록을 받아, 중복 주문을 빼고 결제액과 구매 수량을 모아 돌려줍니다."""
    # 1. 집계 준비: 고객 ID가 없으면 빈 통계를 돌려주고, 있으면 메뉴 분류와 중복 확인 목록을 준비합니다.
    statistics = PurchaseStatistics()
    if customer_id is None:

        return statistics

    ## 고객이 지정된 경우에만 메뉴 분류와 중복 주문 확인 목록을 만듭니다.
    categories = {item['menu_id']: item.get('category') for item in menu}
    seen_order_ids = set()

    # 2. 주문 집계: 해당 고객의 주문만 고르고, 같은 주문 ID가 여러 번 나와도 결제액은 한 번만 더합니다.
    for order in orders:
        if order.get('customer_id') != customer_id or order['order_id'] in seen_order_ids:
            continue
        seen_order_ids.add(order['order_id'])
        statistics.order_count += 1
        statistics.total_spent += order['total_price']

        # 3. 수량 집계: 상품별·온도별 수량을 더하고, 현재 메뉴에서 분류를 찾을 수 있는 상품은 분류별 수량도 더합니다.
        for item in order['items']:
            menu_id = item['menu_id']
            quantity = item['quantity']
            statistics.menu_quantities[menu_id] = statistics.menu_quantities.get(menu_id, 0) + quantity
            category = categories.get(menu_id)
            if category is not None:
                statistics.category_quantities[category] = statistics.category_quantities.get(category, 0) + quantity

            ## 온도 정보가 있는 상품은 따뜻한 음료와 아이스 음료로 나누어 셉니다.
            temperature = item.get('temperature')
            if temperature in ('HOT', 'ICE'):
                statistics.temperature_quantities[temperature] = statistics.temperature_quantities.get(temperature, 0) + quantity

    # 4. 결과 반환: 저장 자료에 취소·환불 구분이 없으므로, 해당 고객의 모든 주문을 합친 통계를 돌려줍니다.

    return statistics


def load_customer_profile(customer_id: str | None):
    """고객 ID로 저장 자료를 찾아 필요한 프로필과 구매 통계를 돌려주고, 없으면 None을 돌려줍니다."""
    # 1. 조회 준비: 고객을 지정하지 않은 기존 요청은 프로필 없이 처리합니다.
    if customer_id is None:

        return None
    customers = json.loads(CUSTOMERS_FILE.read_text(encoding='utf-8'))

    # 2. 항목 제한: 연락처 등 무관한 정보는 프로필에 포함하지 않습니다.
    for customer in customers:
        if customer['customer_id'] == customer_id:
            values = {name: customer[name] for name in CustomerProfile.model_fields
                      if name in customer and name != 'preferences'}

            # 3. 구매 통계: 주문·메뉴 파일로 구매량과 결제액을 계산해 프로필에 넣습니다.
            orders = json.loads(ORDERS_FILE.read_text(encoding='utf-8'))
            menu = json.loads(MENU_FILE.read_text(encoding='utf-8'))
            values['preferences'] = calculate_purchase_statistics(customer_id, orders, menu)

            return CustomerProfile(**values)

    return None


def prepare_customer_state(payload: SessionState):
    """대화 상태를 복사해 서버의 고객 자료를 채워 돌려주며, 고객이 바뀌면 이전 추천 조건을 지웁니다."""
    # 1. 고객 확인: 원본 상태를 복사한 뒤, 화면에서 받은 프로필 대신 고객 ID로 조회한 서버 자료를 채웁니다.
    state = payload.model_copy(deep=True)
    customer_changed = state.customer is not None and state.customer.customer_id != state.customer_id
    state.customer = load_customer_profile(state.customer_id)

    # 2. 조건 분리: 고객이 바뀌면 이전 고객의 조건과 후보를 모두 지웁니다.
    if customer_changed:
        state.recommendation = None

    # 3. 추천 시작: 추천 상태가 없으면 새로 만들고 저장된 알레르기만 복사합니다. 선호 조건은 미확인으로 둡니다.
    if state.recommendation is None and (state.customer is not None or customer_changed):
        state.recommendation = RecommendationState()
        if state.customer is not None:
            state.recommendation.allergies = (
                list(state.customer.allergies) if state.customer.allergies is not None else None
            )

    return state
