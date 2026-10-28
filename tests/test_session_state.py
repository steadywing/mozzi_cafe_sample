"""여러 상태 값을 스키마에 넣어, 미확인·빈 목록·잘못된 자료형을 올바르게 구분하는지 확인합니다."""
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from schemas.session_state import CouponState, OrderItem, OrderState, RecommendationState, SearchState, SessionState


class SessionStateTests(unittest.TestCase):
    def test_history_is_independent_and_contains_role_and_content(self):
        """두 세션을 만들어, 대화 목록이 서로 섞이지 않고 역할·문장을 저장하는지 확인합니다."""
        # 대화 기록은 세션별로 따로 관리하고 role과 content를 검증합니다.
        # 1. 준비: 서로 다른 두 세션과 역할·내용이 있는 메시지를 준비합니다.
        first, second = SessionState(), SessionState()

        first.history.append({'role': 'user', 'content': '안녕하세요'})

        # 2. 확인: 역할·문장을 읽을 수 있고, 한 세션에 추가한 대화가 다른 세션에는 없는지 확인합니다.
        self.assertEqual(second.history, [])
        with self.assertRaises(ValidationError):
            SessionState(history=[{'role': 'invalid', 'content': '안녕하세요'}])
        self.assertNotIn('last_question', SessionState.model_fields)
        self.assertIsNone(first.previous_intent)

    def test_existing_state_examples_are_accepted(self):
        """저장된 예제 상태를 현재 스키마로 읽어, 오류 없이 사용할 수 있는지 확인합니다."""
        # 기존 테스트보드의 예시가 정의한 상태 구조에 맞는지 확인합니다.
        # 1. 준비: 예제 상태 JSON을 읽어, 각 예제를 현재 세션 스키마에 넣습니다.
        fixtures = Path(__file__).parent / 'fixtures' / 'session_states.json'

        for case in json.loads(fixtures.read_text(encoding='utf-8')):
            with self.subTest(case=case['id']):
                state = SessionState.model_validate(case['session_state'])

                # 2. 확인: 각 예제가 세션 객체로 읽히고 의도·조건 값도 보존되는지 확인합니다.
                self.assertEqual(state.model_dump(exclude_unset=True), case['session_state'])

    def test_unchecked_and_none_are_distinct(self):
        """알레르기·선호에 null과 빈 목록을 넣어, 미확인과 조건 없음을 구분하는지 확인합니다."""
        # 1. 준비: 미확인 조건과 없다고 확인한 조건을 서로 다른 상태로 만듭니다.
        unchecked = RecommendationState()
        no_restrictions = RecommendationState(allergies=[], preferences=[])

        # 2. 확인: 미확인 값과 조건이 없다고 확인한 값을 구분합니다.
        self.assertIsNone(unchecked.allergies)
        self.assertIsNone(unchecked.preferences)
        self.assertEqual(no_restrictions.allergies, [])
        self.assertEqual(no_restrictions.preferences, [])
        self.assertIsNone(CouponState().customer_confirmed)
        self.assertIsNone(CouponState().verification)

    def test_confirmation_needs_a_boolean_value(self):
        """쿠폰 확인 여부에 숫자를 넣으면, 참·거짓 값으로 받아들이지 않는지 확인합니다."""
        # 1. 확인: 숫자 1을 확인 여부에 넣었을 때 스키마 오류가 나는지 확인합니다.
        with self.assertRaises(ValidationError):
            CouponState(customer_confirmed='yes')

    def test_candidates_preserve_order_and_do_not_share_lists(self):
        """두 추천 상태의 후보 목록을 바꿔, 순서를 유지하면서 다른 상태에 영향을 주지 않는지 확인합니다."""
        # 1. 준비: 두 추천 상태를 만들고, 한쪽에만 순서가 있는 후보 목록을 넣습니다.
        first = SessionState(recommendation=RecommendationState(candidate_menu_ids=['M02', 'M01']))
        second = SessionState(recommendation=RecommendationState(candidate_menu_ids=[]))

        first.recommendation.candidate_menu_ids.append('M03')

        # 2. 확인: 후보 ID 순서는 유지하고, 한 상태의 수정이 다른 상태로 퍼지지 않는지 확인합니다.
        self.assertEqual(first.recommendation.candidate_menu_ids, ['M02', 'M01', 'M03'])
        self.assertEqual(second.recommendation.candidate_menu_ids, [])

    def test_search_candidates_keep_order_and_distinguish_not_searched(self):
        """검색 전 null과 검색 후 빈 목록을 구분하고, 검색 후보의 순서를 유지하는지 확인합니다."""
        # 1. 확인: 검색 전 null·빈 결과·후보 ID 순서가 각각 유지되는지 확인합니다.
        self.assertIsNone(SearchState().candidate_menu_ids)
        self.assertEqual(SearchState(candidate_menu_ids=[]).candidate_menu_ids, [])

        state = SessionState(search=SearchState(candidate_menu_ids=['M02', 'M01']))

        self.assertEqual(state.search.candidate_menu_ids[1], 'M01')

    def test_order_draft_keeps_missing_and_invalid_values_for_later_validation(self):
        """미완성 주문 초안을 만들면, 빠진 값과 잘못된 수량을 이후 검증 단계까지 보존하는지 확인합니다."""
        # 불완전한 초안은 실제 주문 검증 함수에서 확인합니다.
        # 1. 준비: 필수 정보가 빠지거나 수량이 잘못된 주문 초안을 만듭니다.
        draft = OrderState(items=[OrderItem(product_name=None, quantity=None),
                                  OrderItem(product_name='라떼', quantity=0.5)])

        # 2. 확인: 초안에서 누락값·0·소수 수량이 미리 고쳐지지 않고 남아 있는지 확인합니다.
        self.assertIsNone(draft.confirmation_status)
        self.assertEqual(OrderState(confirmation_status='pending').confirmation_status, 'pending')
        self.assertIsNone(draft.items[0].quantity)
        self.assertEqual(draft.items[1].quantity, 0.5)
        self.assertEqual(OrderState(confirmation_status='confirmed').confirmation_status, 'confirmed')

    def test_unknown_order_confirmation_status_is_rejected(self):
        """정의되지 않은 주문 확인 상태를 넣으면, 스키마가 오류로 거절하는지 확인합니다."""
        # 1. 확인: 허용 목록에 없는 주문 확인 상태를 넣었을 때 스키마 오류가 나는지 확인합니다.
        with self.assertRaises(ValidationError):
            OrderState(confirmation_status='paid')

    def test_order_options_distinguish_unchecked_and_no_options(self):
        """옵션에 null과 빈 목록을 넣어, 아직 묻지 않은 상태와 옵션 없음을 구분하는지 확인합니다."""
        # 1. 준비: 서로 다른 옵션 확인 상태를 가진 상품을 만듭니다.
        unchecked = OrderItem(product_name='아메리카노', temperature='ICE')
        no_options = OrderItem(product_name='카페라떼', temperature='HOT', options=[])

        # 2. 확인: 아직 묻지 않은 옵션과 없다고 확인한 옵션을 구분합니다.
        self.assertIsNone(unchecked.options)
        self.assertEqual(no_options.options, [])
        self.assertEqual(unchecked.temperature, 'ICE')
        with self.assertRaises(ValidationError):
            OrderItem(temperature='WARM')

    def test_order_details_and_receipt_stay_inside_session_order(self):
        """주문을 수정하고 접수 결과를 넣어, 이용·결제·주문번호가 세션의 order 안에 남는지 확인합니다."""
        # 1. 준비: 수정 대기 중인 주문을 세션의 order에 넣습니다.
        state = SessionState(order=OrderState(
            items=[OrderItem(product_id='drink_americano', product_name='아메리카노',
                             quantity=1, temperature='ICE', options=[], price=4500)],
            order_type='포장', payment_method='카드', confirmation_status='awaiting_revision',
            needs_clarification=True, question='어떤 내용을 수정할까요?',
        ))

        # 2. 실행: 접수된 주문번호와 최종 금액을 같은 주문 상태에 반영합니다.
        state.order.order_id = 'order-001'
        state.order.total_price = 4500

        # 3. 확인: 주문의 모든 정보가 order 아래 유지됩니다.
        order = state.model_dump(mode='json')['order']
        self.assertEqual(order['confirmation_status'], 'awaiting_revision')
        self.assertEqual(order['order_type'], '포장')
        self.assertEqual(order['payment_method'], '카드')
        self.assertEqual(order['items'][0]['price'], 4500)
        self.assertEqual(order['order_id'], 'order-001')
        self.assertEqual(order['total_price'], 4500)

    def test_order_money_is_nullable_nonnegative_won_amount(self):
        """주문 금액에 null·정수·음수·소수를 넣어, 미확인 또는 음수가 아닌 정수만 허용하는지 확인합니다."""
        # 1. 확인: 미확인 금액과 유효한 금액을 보존합니다.
        self.assertIsNone(OrderState().total_price)
        self.assertIsNone(OrderItem().price)
        self.assertEqual(OrderState(total_price=0).total_price, 0)

        # 2. 검증: 음수나 소수 금액은 주문 상태에 저장하지 않습니다.
        for value in [-1, 4500.5]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                OrderState(total_price=value)
            with self.subTest(price=value), self.assertRaises(ValidationError):
                OrderItem(price=value)


if __name__ == '__main__':
    unittest.main()
