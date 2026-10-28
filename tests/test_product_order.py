"""주문 추출부터 고객 확인·모의 접수까지 실행해, 금액 계산과 잘못된 주문 차단을 확인합니다."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from common.history_store import load_history, save_history
from common.state_store import load_state
from main import app
from schemas.session_state import CustomerInput, HistoryMessage, OrderItem, OrderState, SessionState


class ProductOrderTests(unittest.TestCase):
    def test_unavailable_item_question_survives_empty_draft(self):
        """판매하지 않는 상품을 빼서 주문이 비어도, 구체적인 판매 불가 안내를 유지하는지 확인합니다."""
        # 1. 준비: 판매하지 않는 상품을 모델이 제외했다고 가정해, 빈 주문과 구체적인 재선택 질문을 만듭니다.
        from services.product_order import check_order
        state = SessionState(order=OrderState(items=[], needs_clarification=True,
                                             question='망고 치즈버거는 판매하지 않습니다. 다른 메뉴를 골라주세요.'))

        # 2. 확인: 빈 목록이라는 이유로 구체적인 안내를 일반 질문으로 바꾸지 않습니다.
        self.assertEqual(check_order(state), state.order.question)

    def setUp(self):
        """임시 메뉴·옵션·기록 저장소와 대체 모델을 준비해, 실제 주문 없이 처리 흐름을 시험합니다."""
        # 1. 준비: 메뉴와 옵션 자료를 임시 폴더에 만듭니다.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.menu_file = self.root / 'menu.json'
        self.options_file = self.root / 'order_options.json'
        self.menu = [
            {'menu_id': 'americano', 'name': '아메리카노', 'aliases': ['아아'], 'price': 4500,
             'temperatures': ['HOT', 'ICE'], 'available': True},
            {'menu_id': 'latte', 'name': '카페라떼', 'aliases': ['라떼'], 'price': 5000,
             'temperatures': ['HOT', 'ICE'], 'available': True},
        ]
        self.menu_file.write_text(json.dumps(self.menu), encoding='utf-8')

        ## 메뉴 가격과 별도로 추가 옵션의 가격과 적용 가능한 메뉴를 저장합니다.
        self.options_file.write_text(json.dumps({
            '샷 추가': {'price': 500, 'menu_ids': ['americano', 'latte']},
            '두유로 변경': {'price': 500, 'menu_ids': ['latte']},
            '오트 음료로 변경': {'price': 500, 'menu_ids': ['latte']},
        }), encoding='utf-8')

        ## 실제 모델 연결을 대체해 주문 API의 처리 흐름만 확인합니다.
        self.api = TestClient(app)
        model_patcher = patch('services.product_order.get_openai_client')
        model_patcher.start()
        self.addCleanup(model_patcher.stop)

        # 2. 격리: 기록 저장소를 임시 폴더로 바꾸고 실제 파일은 건드리지 않습니다.
        for target, value in [('common.state_store.STATE_DIR', self.root / 'state'),
                              ('common.history_store.HISTORY_DIR', self.root / 'history')]:
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def ready_state(self, text='yes'):
        """입력 문장을 넣어, 옵션·이용·결제가 확인된 주문 상태를 테스트용 가격과 함께 만들어 돌려줍니다."""
        # 1. 입력 준비: 실제 가격과 다른 값을 넣어 서버가 메뉴 기준으로 다시 확인하게 합니다.

        return SessionState(customer_id='customer-1', session_id='session-1', input=CustomerInput(text=text),
                            order=OrderState(items=[
                                OrderItem(product_name='아메리카노', product_id='wrong', quantity=2,
                                          temperature='ICE', options=['샷 추가'], price=1),
                                OrderItem(product_name='카페라떼', quantity=1, temperature='HOT', options=[]),
                            ], order_type='포장', payment_method='카드', confirmation_status='pending'))

    def reference_patches(self):
        """주문 함수가 임시 메뉴·옵션 파일을 읽도록 바꾸는 테스트 설정을 돌려줍니다."""
        # 1. 자료 준비: 두 파일 경로를 한 번에 바꾸는 테스트 문맥을 만듭니다.

        return patch.multiple('services.product_order', MENU_FILE=self.menu_file, OPTIONS_FILE=self.options_file)

    def test_missing_input_is_rejected_without_model_call(self):
        """입력 없는 주문 요청을 보내, 모델 처리나 상태 저장 전에 입력 오류를 반환하는지 확인합니다."""
        # 1. 실행: 입력이 없는 상태로 주문 API를 요청합니다.
        response = self.api.post('/chatbot/order', json={})

        # 2. 확인: 입력 오류를 반환하며 저장소를 만들지 않습니다.
        self.assertEqual(response.status_code, 422)
        self.assertFalse((self.root / 'state').exists())

    def test_structured_output_uses_state_and_menu_reference(self):
        """주문 초안을 생성해, 대화·메뉴·출력 형식을 전달하고 모델이 만든 금액은 버리는지 확인합니다."""
        # 1. 준비: 모델 출력만 대체하고 실제 입력 조합 코드는 실행합니다.
        from schemas.product_order import OrderDraft
        from services.product_order import create_order_draft
        parsed = OrderDraft(items=[{'product_name': '아메리카노', 'quantity': 1, 'temperature': 'ICE', 'options': []}],
                            order_type='포장', payment_method='카드', total_price=99999,
                            confirmation_status='pending', needs_clarification=False, question=None)
        client = Mock()
        client.responses.parse.return_value = SimpleNamespace(output_parsed=parsed)
        state = self.ready_state('아이스 아메리카노 한 잔')
        state.history = [HistoryMessage(role='assistant', content='무엇을 주문하시겠어요?')]

        # 2. 실행: 공통 상태를 사용해 주문 초안을 생성합니다.
        with self.reference_patches(), patch('services.product_order.get_openai_client', return_value=client):
            order = create_order_draft(state)

        # 3. 확인: system 지침, history, 현재 상태를 전달하고 모델이 추측한 금액은 사용하지 않습니다.
        arguments = client.responses.parse.call_args.kwargs
        self.assertEqual(arguments['input'][0]['role'], 'system')
        self.assertIn('아메리카노', arguments['input'][0]['content'])
        self.assertEqual(arguments['input'][1], {'role': 'assistant', 'content': '무엇을 주문하시겠어요?'})
        self.assertEqual(json.loads(arguments['input'][-1]['content'])['input']['text'], state.input.text)
        self.assertIs(arguments['text_format'], OrderDraft)
        self.assertIsNone(order.total_price)

    def test_extraction_fills_menu_price_and_saves_steps_without_history(self):
        """첫 주문을 처리해, 실제 메뉴 가격을 채우고 대화 대신 단계별 상태만 저장하는지 확인합니다."""
        # 1. 준비: 저장된 대화와 미확인 옵션이 있는 모델 초안을 준비합니다.
        previous = [{'role': 'user', 'content': '안녕하세요'}]
        save_history('customer-1', 'session-1', previous)
        draft = OrderState(items=[OrderItem(product_name='아아', quantity=2)], confirmation_status='pending')
        with self.reference_patches(), patch('services.product_order.create_order_draft', return_value=draft), \
             patch('services.product_order.perf_counter', side_effect=[10, 10.125]):
            # 2. 실행: 고객의 첫 주문 문장을 처리합니다.
            response = self.api.post('/chatbot/order', json={
                'customer_id': 'customer-1', 'session_id': 'session-1', 'input': {'text': '아아 두 잔'}})

        # 3. 확인: 가격은 메뉴 기준이고 빠진 정보 질문과 단계별 전체 상태가 남습니다.
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()
        self.assertEqual(state['order']['items'][0]['product_name'], '아메리카노')
        self.assertEqual(state['order']['items'][0]['product_id'], 'americano')
        self.assertEqual(state['order']['items'][0]['price'], 4500)
        self.assertIn('옵션', state['answer']['answer'])
        self.assertIn('결제', state['answer']['answer'])
        self.assertEqual(state['intent'], {'intent': 'product_order', 'confidence': None})
        self.assertEqual(load_history('customer-1', 'session-1'), previous)

        ## 대화 기록과 구분해 단계별 상태와 처리 시간이 저장됐는지 확인합니다.
        turn = load_state('customer-1', 'session-1')[0]
        self.assertEqual(turn['elapsed_ms'], 125)
        self.assertIn('match_menu_and_fill_prices', [step['step'] for step in turn['steps']])
        for step in turn['steps']:
            self.assertEqual(set(step['state']), set(SessionState.model_fields))

    def test_yes_calculates_authoritative_menu_and_option_prices(self):
        """확인된 주문에 yes를 보내, 메뉴·옵션 가격으로 계산한 금액과 테스트 접수번호를 반환하는지 확인합니다."""
        # 1. 실행: 이미 확인된 주문을 최종 승인합니다.
        with self.reference_patches(), patch('services.product_order.create_order_draft') as llm:
            response = self.api.post('/chatbot/order', json=self.ready_state().model_dump(mode='json'))

        # 2. 확인: 모델 재호출 없이 실제 자료의 금액을 반영하고 가정 접수를 표시합니다.
        self.assertEqual(response.status_code, 200, response.text)
        state = response.json()
        self.assertEqual(state['order']['total_price'], 15000)
        self.assertEqual(state['order']['items'][0]['price'], 4500)
        self.assertEqual(state['order']['confirmation_status'], 'confirmed')
        self.assertTrue(state['order']['order_id'].startswith('test-'))
        self.assertIn('15,000원', state['answer']['answer'])
        self.assertIn('테스트', state['answer']['answer'])
        llm.assert_not_called()

    def test_no_requires_revision_then_another_confirmation(self):
        """no 뒤에 yes와 수정 요청을 보내, 수정 전 접수를 막고 수정 후 다시 확인받는지 확인합니다."""
        # 1. 실행: no와 즉시 yes를 차례로 보내고 수정 문장을 처리합니다.
        with self.reference_patches():
            refused = self.api.post('/chatbot/order', json=self.ready_state('no').model_dump(mode='json')).json()
            blocked = self.api.post('/chatbot/order', json={**refused, 'input': {'text': 'yes'}}).json()
            revised_order = self.ready_state().order
            revised_order.items[0].quantity = 1
            with patch('services.product_order.create_order_draft', return_value=revised_order), \
                 patch('services.product_order.place_order') as place:
                revised = self.api.post('/chatbot/order', json={**refused, 'input': {'text': '아메리카노 한 잔으로 바꿔줘요'}}).json()

        # 2. 확인: 수정 전 접수를 막고 수정 뒤에도 확인 질문만 합니다.
        self.assertEqual(refused['order']['confirmation_status'], 'awaiting_revision')
        self.assertIsNone(blocked['order']['order_id'])
        self.assertIn('수정', blocked['answer']['answer'])
        self.assertEqual(revised['order']['items'][0]['quantity'], 1)
        self.assertIn('yes', revised['answer']['answer'])
        self.assertIsNone(revised['order']['order_id'])
        place.assert_not_called()

    def test_invalid_menu_quantity_and_options_never_place_order(self):
        """판매 불가 메뉴·잘못된 수량·지원하지 않는 옵션을 보내, 주문 접수는 실행하지 않는지 확인합니다."""
        # 1. 준비: 서로 다른 검증 실패를 일으키는 주문들을 만듭니다.
        states = []
        for name, quantity, options in [('없는 메뉴', 1, []), ('아메리카노', 0, []),
                                        ('아메리카노', 0.5, []), ('아메리카노', 1, None),
                                        ('아메리카노', 1, ['두유로 변경']),
                                        ('아메리카노', 1, ['샷 추가', '샷 추가']),
                                        ('카페라떼', 1, ['두유로 변경', '오트 음료로 변경'])]:
            state = self.ready_state()
            state.order.items[0].product_name = name
            state.order.items[0].quantity = quantity
            state.order.items[0].options = options
            states.append(state)

        # 2. 실행과 확인: 모든 실패에서 접수 API를 호출하지 않습니다.
        with self.reference_patches(), patch('services.product_order.place_order') as place:
            for state in states:
                with self.subTest(order=state.order.model_dump(mode='json')):
                    response = self.api.post('/chatbot/order', json=state.model_dump(mode='json'))
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertIsNone(response.json()['order']['order_id'])
            self.menu[0]['available'] = False
            self.menu_file.write_text(json.dumps(self.menu), encoding='utf-8')
            response = self.api.post('/chatbot/order', json=self.ready_state().model_dump(mode='json'))
            self.assertIn('판매', response.json()['answer']['answer'])
        place.assert_not_called()

    def test_already_confirmed_order_is_not_submitted_again(self):
        """접수된 주문을 다시 보내, 기존 주문번호를 유지하고 중복 접수하지 않는지 확인합니다."""
        # 1. 준비: 접수된 상태를 준비합니다.
        state = self.ready_state()
        state.order.confirmation_status = 'confirmed'
        state.order.order_id = 'test-existing'
        state.order.total_price = 15000

        # 2. 실행과 확인: 저장된 접수 결과를 유지하며 추가 접수를 하지 않습니다.
        with self.reference_patches(), patch('services.product_order.place_order') as place:
            response = self.api.post('/chatbot/order', json=state.model_dump(mode='json'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['order']['order_id'], 'test-existing')
        self.assertIn('이미', response.json()['answer']['answer'])
        place.assert_not_called()

    def test_failed_receipt_does_not_mark_order_confirmed(self):
        """접수 함수가 실패를 반환하면, 주문을 완료로 바꾸거나 주문번호를 안내하지 않는지 확인합니다."""
        # 1. 실행: 접수 API가 실패한 것으로 대체합니다.
        with self.reference_patches(), patch('services.product_order.place_order', return_value={'status': 'failed'}):
            response = self.api.post('/chatbot/order', json=self.ready_state().model_dump(mode='json'))

        # 2. 확인: 고객 확인 상태와 빈 주문번호를 유지하고 실패를 안내합니다.
        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertEqual(state['order']['confirmation_status'], 'pending')
        self.assertIsNone(state['order']['order_id'])
        self.assertIsNone(state['order']['total_price'])
        self.assertIn('접수하지 못', state['answer']['answer'])

    def test_model_failure_returns_public_error_and_saves_no_turn(self):
        """주문 모델 호출에 오류를 발생시켜, 내부 정보 노출과 실패한 턴 저장을 막는지 확인합니다."""
        # 1. 실행: 모델 실패를 대체하고 첫 주문을 요청합니다.
        with self.reference_patches(), patch('services.product_order.create_order_draft', side_effect=ValueError('private')):
            response = self.api.post('/chatbot/order', json={'input': {'text': '메뉴 주문할게요'}})

        # 2. 확인: 실패한 턴을 저장하거나 내부 오류를 노출하지 않습니다.
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('private', response.text)
        self.assertFalse((self.root / 'state').exists())
