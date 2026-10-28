"""주문 노트북의 단계와 확인 조건을 대체 모델로 확인합니다."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.order_practice import router
from schemas.product_order import OrderDraft


class OrderNotebookApiTests(unittest.TestCase):
    """주문 초안과 확인 절차의 연결을 확인합니다."""

    def test_order_requires_confirmation_before_mock_receipt(self):
        """완전한 주문을 보내고 명시적으로 확인한 다음에만 모의 접수되는지 확인합니다."""
        # 1. 준비: 주문 초안을 반환할 대체 모델과 시험용 API를 만듭니다.
        app = FastAPI()
        app.include_router(router)
        draft = OrderDraft(items=[{'product_name': '아메리카노', 'quantity': 2, 'temperature': 'ICE', 'options': []}], order_type='포장', payment_method='카드', total_price=None, confirmation_status='pending', needs_clarification=False, question=None)
        client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: SimpleNamespace(output_parsed=draft)))
        api = TestClient(app)

        # 2. 실행: 초안 생성 후 같은 주문 상태에 yes를 전달합니다.
        with patch('services.notebook_order.get_openai_client', return_value=client):
            first = api.post('/chatbot/order/practice', json={'input': {'text': '아이스 아메리카노 두 잔 포장 카드'}})
        self.assertEqual(first.status_code, 200)
        state = first.json()['state']
        self.assertEqual(state['order']['confirmation_status'], 'pending')
        self.assertIsNone(state['order']['order_id'])
        self.assertEqual(first.json()['steps'][1]['input']['order']['items'][0]['product_name'], '아메리카노')
        self.assertGreater(first.json()['steps'][1]['input']['menu_count'], 0)
        state['input'] = {'text': 'yes', 'has_image': False}
        second = api.post('/chatbot/order/practice', json=state)

        # 3. 확인: 검증 후 고객이 승인한 경우에만 테스트 주문번호가 생깁니다.
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['state']['order']['confirmation_status'], 'confirmed')
        self.assertTrue(second.json()['state']['order']['order_id'].startswith('test-'))
        self.assertEqual(second.json()['steps'][0]['input']['text'], 'yes')


if __name__ == '__main__':
    unittest.main()
