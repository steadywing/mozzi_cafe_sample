"""고객 프로필과 구매 통계를 읽어, 추천 조건·잔액·모델 전달 정보가 올바르게 분리되는지 확인합니다."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from contextlib import ExitStack

from pydantic import ValidationError

from schemas.session_state import SessionState


class CustomerProfileTests(unittest.TestCase):
    def setUp(self):
        """임시 고객 파일과 대체 저장 함수를 준비해, 실제 고객 자료를 바꾸지 않고 테스트하도록 설정합니다."""
        # 1. 자료 준비: 개인정보는 테스트용 가상 값만 사용합니다.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.customer_file = Path(directory.name) / 'customers.json'
        self.orders_file = Path(directory.name) / 'orders.json'
        self.menu_file = Path(directory.name) / 'menu.json'
        self.orders_file.write_text('[]', encoding='utf-8')
        self.menu_file.write_text('[]', encoding='utf-8')
        self.customers = [
            {'customer_id': 'a', 'name': '가상 고객', 'birth_year': 2000,
             'membership_level': '일반', 'phone': 'private', 'gender': 'F'},
            {'customer_id': 'b', 'name': '다음 고객', 'birth_year': 1990,
             'membership_level': '우수', 'allergies': ['우유'], 'preferences': []},
        ]
        self.customer_file.write_text(json.dumps(self.customers), encoding='utf-8')

    def customer_file_patch(self):
        """고객 조회 함수가 임시 고객 파일을 읽도록 경로를 바꾸는 설정을 돌려줍니다."""
        # 1. 경로 지정: 고객 원본 파일을 테스트에서 읽거나 수정하지 않습니다.
        stack = ExitStack()
        stack.enter_context(patch('common.customer_store.CUSTOMERS_FILE', self.customer_file))
        stack.enter_context(patch('common.customer_store.ORDERS_FILE', self.orders_file, create=True))
        stack.enter_context(patch('common.customer_store.MENU_FILE', self.menu_file, create=True))

        return stack

    def test_lookup_keeps_only_allowed_fields_and_unknown_values(self):
        """고객 파일을 조회해, 허용된 정보만 반환하고 없는 조건은 미확인으로 남기는지 확인합니다."""
        # 1. 실행: 고객 자료를 실제 조회 함수로 읽습니다.
        from common.customer_store import load_customer_profile
        with self.customer_file_patch():
            customer = load_customer_profile('a')

        # 2. 확인: 허용한 정보만 반환하고 없는 조건을 추측하지 않습니다.
        self.assertEqual(customer.model_dump(), {
            'customer_id': 'a', 'name': '가상 고객', 'birth_year': 2000,
            'membership_level': '일반', 'allergies': None, 'points': None, 'stamps': None,
            'preferences': {'order_count': 0, 'total_spent': 0, 'menu_quantities': {},
                            'category_quantities': {}, 'temperature_quantities': {}},
        })

    def test_unknown_and_missing_id_return_no_profile(self):
        """없거나 모르는 고객 ID를 조회하면, 고객 프로필 없이 처리하는지 확인합니다."""
        # 1. 확인: 기존 비회원 요청도 고객 프로필 없이 허용합니다.
        from common.customer_store import load_customer_profile
        with self.customer_file_patch():
            self.assertIsNone(load_customer_profile('missing'))
            self.assertIsNone(load_customer_profile(None))

    def test_prepare_seeds_saved_conditions_without_mutating_input(self):
        """저장된 알레르기·선호로 추천 상태를 만들 때, 원본과 명시적인 빈 조건을 보존하는지 확인합니다."""
        # 1. 준비: 서버에 조건이 저장된 고객의 첫 요청을 만듭니다.
        from common.customer_store import prepare_customer_state
        payload = SessionState(customer_id='b')
        before = payload.model_dump()

        # 2. 실행: 원본과 분리된 추천 상태를 준비합니다.
        with self.customer_file_patch():
            state = prepare_customer_state(payload)
        state.recommendation.allergies.append('달걀')

        # 3. 확인: 프로필과 입력은 추천 상태 수정의 영향을 받지 않습니다.
        self.assertEqual(state.customer.allergies, ['우유'])
        self.assertIsNone(state.recommendation.preferences)
        self.assertEqual(payload.model_dump(), before)

    def test_prepare_replaces_client_profile_with_server_values(self):
        """고객이 임의로 보낸 프로필을 넣어도, 서버 고객 파일의 정보로 교체하는지 확인합니다."""
        # 1. 준비: 고객이 임의로 보낸 프로필을 포함합니다.
        from common.customer_store import prepare_customer_state
        payload = SessionState(customer_id='b', customer={
            'customer_id': 'b', 'name': '조작', 'allergies': [],
            'preferences': {'order_count': 99},
        })

        # 2. 실행과 확인: 서버의 이름과 알레르기를 사용합니다.
        with self.customer_file_patch():
            state = prepare_customer_state(payload)
        self.assertEqual(state.customer.name, '다음 고객')
        self.assertEqual(state.recommendation.allergies, ['우유'])
        self.assertIsNone(state.recommendation.preferences)

    def test_same_customer_preserves_followup_conditions(self):
        """같은 고객의 다음 요청을 준비할 때, 대화 중 수정한 알레르기·선호를 유지하는지 확인합니다."""
        # 1. 준비: 기존 고객 프로필과 후속 추천 조건을 만듭니다.
        from common.customer_store import prepare_customer_state
        payload = SessionState(customer_id='b', customer={'customer_id': 'b'},
                               recommendation={'allergies': ['우유', '견과류'],
                                               'preferences': ['디저트'], 'candidate_menu_ids': ['x']})

        # 2. 실행과 확인: 서버 프로필을 다시 읽어도 대화 상태를 덮어쓰지 않습니다.
        with self.customer_file_patch():
            state = prepare_customer_state(payload)
        self.assertEqual(state.recommendation.model_dump(), payload.recommendation.model_dump())

    def test_customer_change_discards_previous_conditions_and_candidates(self):
        """다른 고객으로 바꾸면, 이전 고객의 추천 조건과 메뉴 후보가 지워지는지 확인합니다."""
        # 1. 준비: 다른 고객의 프로필과 조건이 함께 온 요청을 만듭니다.
        from common.customer_store import prepare_customer_state
        payload = SessionState(customer_id='a', customer={'customer_id': 'b'},
                               recommendation={'allergies': ['우유'], 'preferences': [],
                                               'candidate_menu_ids': ['old'], 'extra_condition': 'old'})

        # 2. 실행과 확인: 새 고객의 미확인 조건으로 초기화합니다.
        with self.customer_file_patch():
            state = prepare_customer_state(payload)
        self.assertEqual(state.customer.customer_id, 'a')
        self.assertEqual(state.recommendation.model_dump(), {
            'allergies': None, 'preferences': None, 'candidate_menu_ids': None,
        })

    def test_unknown_id_discards_forged_profile_but_accepts_existing_state(self):
        """없는 고객 ID로 요청하면 임의 프로필을 지우고, 고객 전환 여부에 맞게 추천 조건을 처리하는지 확인합니다."""
        # 1. 준비: 프로필이 없는 기존 API 입력을 사용합니다.
        from common.customer_store import prepare_customer_state
        payload = SessionState(customer_id='missing', recommendation={'allergies': [], 'preferences': []})
        with self.customer_file_patch():
            state = prepare_customer_state(payload)

        # 2. 확인: 빈 조건은 미확인으로 바뀌지 않습니다.
        self.assertIsNone(state.customer)
        self.assertEqual(state.recommendation.allergies, [])
        self.assertEqual(state.recommendation.preferences, [])

        # 3. 고객 전환 확인: 조회되지 않는 고객으로 바뀌어도 이전 고객의 조건은 지운다.
        changed = SessionState(customer_id='missing', customer={'customer_id': 'b'},
                               recommendation={'allergies': ['우유'], 'preferences': ['단맛']})
        with self.customer_file_patch():
            state = prepare_customer_state(changed)
        self.assertIsNone(state.customer)
        self.assertIsNone(state.recommendation.allergies)
        self.assertIsNone(state.recommendation.preferences)

    def test_intent_and_order_runs_prepare_profile_and_keep_payload(self):
        """분류·주문 함수를 실행해, 서버 프로필을 연결하면서 입력 원본은 바꾸지 않는지 확인합니다."""
        # 1. 준비: 실제 모델과 파일 저장을 대체합니다.
        from services.intent_classifier import run_intent_classifier
        from services.product_order import run_product_order
        payload = SessionState(customer_id='a', input={'text': '주문해요'})
        before = payload.model_dump()
        with self.customer_file_patch(), \
             patch('services.intent_classifier.classify_intent', return_value={'intent': 'product_order', 'confidence': 0.9}), \
             patch('services.intent_classifier.load_history', return_value=[]), \
             patch('services.intent_classifier.save_state'), \
             patch('services.product_order.create_order_draft', return_value=None), \
             patch('services.product_order.load_history', return_value=[]), \
             patch('services.product_order.save_state'):
            # 2. 실행: 두 진입점의 실제 상태 준비를 호출합니다.
            classified = run_intent_classifier(payload)
            ordered = run_product_order(payload)

        # 3. 확인: 두 응답에 프로필이 있고 입력은 바뀌지 않습니다.
        self.assertEqual(classified['customer']['name'], '가상 고객')
        self.assertEqual(ordered['customer']['name'], '가상 고객')
        self.assertEqual(payload.model_dump(), before)

    def test_model_inputs_exclude_customer_profile(self):
        """프로필이 있는 상태로 분류·답변·주문을 요청해도, 모델 입력에는 프로필이 빠지는지 확인합니다."""
        # 1. 준비: 고객 자료를 포함한 상태와 모델 대체 응답을 만듭니다.
        from services.intent_classifier import classify_intent, generate_unknown_response
        from services.product_order import create_order_draft
        payload = SessionState(customer_id='a', input={'text': '안녕'}, customer={'customer_id': 'a', 'name': '비공개'})
        jev = Mock()
        jev.system_one.return_value.model_dump.return_value = {
            'answers': {'intent': {'choice': 'unknown', 'confidence': 0.9}},
        }
        openai = Mock()
        openai.responses.create.return_value = SimpleNamespace(output_text='확인해 주세요.', model='test')
        parsed = Mock()
        parsed.model_dump.return_value = {}
        openai.responses.parse.return_value = SimpleNamespace(output_parsed=parsed)

        # 2. 실행: 모델 대신 준비한 객체를 사용해 실제 메시지를 만듭니다.
        with patch('services.intent_classifier.get_prompt', return_value='지침'), \
             patch('services.intent_classifier.get_jev_client', return_value=jev), \
             patch('services.intent_classifier.get_openai_client', return_value=openai), \
             patch('services.product_order.get_order_prompt', return_value='지침'), \
             patch('services.product_order.get_openai_client', return_value=openai):
            classify_intent(payload)
            generate_unknown_response(payload)
            create_order_draft(payload)

        # 3. 확인: 모델별 실제 요청의 구조에서 customer 필드가 빠진다.
        self.assertNotIn('customer', jev.system_one.call_args.kwargs['state']['session_state'])
        unknown_input = json.loads(openai.responses.create.call_args.kwargs['input'][-1]['content'])
        order_input = json.loads(openai.responses.parse.call_args.kwargs['input'][-1]['content'])
        self.assertNotIn('customer', unknown_input['session_state'])
        self.assertNotIn('customer', order_input)


    def test_balances_preserve_missing_zero_and_saved_amounts(self):
        """고객 잔액을 읽을 때, 미확인과 0을 구분하고 주문 이력으로 잔액을 추측하지 않는지 확인합니다."""
        # 1. 준비: 과거 선호와 적립 이력을 현재 잔액과 분리합니다.
        from common.customer_store import load_customer_profile
        self.customers[0]['preferences'] = ['단맛']
        self.customers[1].update(points=0, stamps=4)
        self.customer_file.write_text(json.dumps(self.customers), encoding='utf-8')
        self.orders_file.write_text(json.dumps([
            {'order_id': 'one', 'customer_id': 'a', 'total_price': 4000,
             'stamps_earned': 20, 'items': []},
        ]), encoding='utf-8')

        # 2. 실행: 임시 자료에서 두 고객을 조회합니다.
        with self.customer_file_patch():
            first = load_customer_profile('a')
            second = load_customer_profile('b')

        # 3. 확인: 누락과 명시적 0을 구분하고 과거 선호를 추측하지 않습니다.
        self.assertIsNone(first.points)
        self.assertIsNone(first.stamps)
        self.assertEqual(second.points, 0)
        self.assertEqual(second.stamps, 4)
        self.assertEqual(first.preferences.order_count, 1)
        self.assertEqual(second.preferences.menu_quantities, {})

    def test_balances_reject_negative_and_boolean_values(self):
        """적립금·스탬프에 음수나 참·거짓 값을 넣으면, 잘못된 잔액으로 거절하는지 확인합니다."""
        # 1. 확인: 고객 프로필 경계에서 잘못된 잔액을 거절합니다.
        from schemas.session_state import CustomerProfile
        for field in ('points', 'stamps'):
            for value in (-1, True, False):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError):
                        CustomerProfile(customer_id='a', **{field: value})
        self.assertIsNone(CustomerProfile(customer_id='a').preferences)

    def test_statistics_deduplicate_orders_and_use_paid_total(self):
        """중복·타인 주문이 섞인 자료에서, 해당 고객의 고유 주문 결제액과 상품 수량만 합산하는지 확인합니다."""
        # 1. 준비: 할인·옵션, 중복 주문, 다른 고객과 비회원 주문을 섞는다.
        from common.customer_store import calculate_purchase_statistics
        menu = [{'menu_id': 'coffee', 'category': '음료'},
                {'menu_id': 'cake', 'category': '디저트'}]
        first = {'order_id': 'one', 'customer_id': 'a', 'total_price': 8700,
                 'items': [
                     {'menu_id': 'coffee', 'quantity': 2, 'temperature': 'ICE',
                      'price': 4000, 'options': [{'price': -300}], 'line_total': 7400},
                     {'menu_id': 'cake', 'quantity': 1, 'temperature': None, 'price': 2000},
                 ]}
        second = {'order_id': 'two', 'customer_id': 'a', 'total_price': 2000,
                  'items': [{'menu_id': 'coffee', 'quantity': 1, 'temperature': 'HOT'},
                            {'menu_id': 'removed', 'quantity': 3, 'temperature': None}]}
        orders = [dict(first, customer_id='b'), first, first, second,
                  dict(first, order_id='guest', customer_id=None)]

        # 2. 실행: 저장된 주문만으로 통계를 계산합니다.
        statistics = calculate_purchase_statistics('a', orders, menu)

        # 3. 확인: 할인·옵션을 다시 계산하지 않고 알려진 카테고리만 더합니다.
        self.assertEqual(statistics.model_dump(), {
            'order_count': 2, 'total_spent': 10700,
            'menu_quantities': {'coffee': 3, 'cake': 1, 'removed': 3},
            'category_quantities': {'음료': 3, '디저트': 1},
            'temperature_quantities': {'ICE': 2, 'HOT': 1},
        })
        self.assertEqual(calculate_purchase_statistics('missing', orders, menu).order_count, 0)
        self.assertEqual(calculate_purchase_statistics(None, orders, menu).order_count, 0)

    def test_lookup_recomputes_statistics_from_current_files(self):
        """주문 파일을 바꾼 뒤 고객을 다시 조회해, 구매 통계만 갱신하고 직접 입력한 조건은 유지하는지 확인합니다."""
        # 1. 준비: 고객 자료의 과거 선호를 구매 통계로 쓰지 않습니다.
        from common.customer_store import prepare_customer_state
        self.customers[1]['preferences'] = ['디저트']
        self.customer_file.write_text(json.dumps(self.customers), encoding='utf-8')
        self.menu_file.write_text(json.dumps([
            {'menu_id': 'coffee', 'category': '음료'},
        ]), encoding='utf-8')
        with self.customer_file_patch():
            initial = prepare_customer_state(SessionState(customer_id='b'))
            self.orders_file.write_text(json.dumps([
                {'order_id': 'new', 'customer_id': 'b', 'total_price': 3500,
                 'items': [{'menu_id': 'coffee', 'quantity': 1, 'temperature': 'ICE'}]},
            ]), encoding='utf-8')
            # 2. 실행: 같은 고객의 후속 조건을 포함해 다시 준비합니다.
            initial.recommendation.preferences = ['디저트']
            updated = prepare_customer_state(initial)

        # 3. 확인: 구매 통계와 직접 입력한 조건을 독립적으로 보존합니다.
        self.assertEqual(initial.customer.preferences.order_count, 0)
        self.assertEqual(updated.customer.preferences.menu_quantities, {'coffee': 1})
        self.assertEqual(updated.customer.preferences.category_quantities, {'음료': 1})
        self.assertEqual(updated.recommendation.preferences, ['디저트'])
