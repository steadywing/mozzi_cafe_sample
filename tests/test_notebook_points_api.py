"""영수증 검증과 가상 포인트 적립 API를 대체 판독으로 확인합니다."""
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.points import router
from routers.test_samples import router as test_samples_router
from common.notebook_step_store import clear_trace, get_trace
from schemas.session_state import ReceiptState
from services import notebook_points


class PointTests(unittest.TestCase):
    """가상 주문과 대체 영수증 판독 결과로 적립 규칙을 확인합니다."""

    def setUp(self):
        """각 테스트 전에 서버 메모리 상태를 비우고 API 클라이언트를 만듭니다."""
        # 1. 테스트 준비: 세션과 처리 기록을 격리합니다.
        notebook_points.sessions.clear()
        notebook_points.processed_receipts.clear()
        app = FastAPI()
        app.include_router(router)
        app.include_router(test_samples_router)
        self.client = TestClient(app)

    def test_confirmation_and_duplicate_are_checked(self):
        """일치하는 가상 영수증을 확인받은 뒤 한 번만 적립하는지 확인합니다."""
        # 1. 판독 대체: 주문 파일의 고객과 번호, 금액이 일치하는 결과를 준비합니다.
        clear_trace('points', 'a')
        def fake_ocr(state, sample):
            """샘플 요청을 받아 일치하는 가상 영수증을 상태에 담습니다."""
            # 1. 판독 결과: 실제 모델 대신 확인할 영수증 값을 반환합니다.
            state.receipt = ReceiptState(store_name='모찌카페', receipt_number='ord_20260905_0001', payment_amount=9200, status='pending')

            return state, {'model': 'test', 'input': {'sample': sample}, 'prompt': 'test'}
        with patch('services.notebook_points.generate_receipt_data', side_effect=fake_ocr):
            # 2. 실행: 확인 전 검증하고 명시적 확인 뒤 적립을 요청합니다.
            start = self.client.post('/chatbot/points/start', json={'session_id': 'a', 'sample': 'receipt-001', 'customer_id': 'cust_001'})
            reject = self.client.post('/chatbot/points/confirm', json={'session_id': 'a', 'confirmed': False, 'points_to_add': 100})
            success = self.client.post('/chatbot/points/confirm', json={'session_id': 'a', 'confirmed': True, 'points_to_add': 100})
            duplicate = self.client.post('/chatbot/points/confirm', json={'session_id': 'a', 'confirmed': True, 'points_to_add': 100})
            next_start = self.client.post('/chatbot/points/start', json={'session_id': 'b', 'sample': 'receipt-001', 'customer_id': 'cust_001'})

        # 3. 확인: 검증 및 명시적 확인 후 한 번만 잔액이 증가합니다.
        self.assertEqual(start.json()['state']['receipt']['verification'], 'passed')
        self.assertEqual(reject.json()['state']['customer']['points'], 0)
        self.assertEqual(success.json()['state']['customer']['points'], 100)
        self.assertEqual(duplicate.json()['state']['customer']['points'], 100)
        self.assertEqual(next_start.json()['state']['receipt']['verification'], 'failed')
        self.assertEqual(start.json()['steps'][1]['input']['receipt']['receipt_number'], 'ord_20260905_0001')
        self.assertEqual(success.json()['steps'][0]['input']['current_points'], 0)
        self.assertEqual(duplicate.json()['steps'][0]['input']['current_points'], 100)
        self.assertEqual([turn['turn_index'] for turn in get_trace('points', 'a')], [1, 2, 3, 4])

        ## 세션 기록을 비워도 이미 처리한 영수증은 다시 적립하지 못하게 남깁니다.
        self.assertEqual(self.client.delete('/chatbot/points/a').json(), {'deleted': True})
        self.assertEqual(get_trace('points', 'a'), [])
        self.assertIn('ord_20260905_0001', notebook_points.processed_receipts)

    def test_unapproved_sample_and_missing_session_are_rejected(self):
        """임의 파일 경로와 없는 세션의 적립을 거절하는지 확인합니다."""
        # 1. 요청 확인: 경로 주입은 422, 세션 없는 확인은 404를 반환합니다.
        invalid = self.client.post('/chatbot/points/start', json={'session_id': 'a', 'sample': '../../secret', 'customer_id': 'cust_001'})
        missing = self.client.post('/chatbot/points/confirm', json={'session_id': 'missing', 'confirmed': True, 'points_to_add': 100})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(missing.status_code, 404)

    def test_cases_use_existing_receipt_images_and_reject_other_files(self):
        """테스트 사례의 이미지가 실제 샘플과 일치하고 임의 파일 요청은 거절하는지 확인합니다."""
        # 1. 사례 조회: 준비된 사례마다 표시 이미지와 판독용 샘플 이름을 확인합니다.
        response = self.client.get('/test/api/points/cases')
        self.assertEqual(response.status_code, 200)
        cases = response.json()['cases']
        self.assertEqual(len(cases), 3)
        for case in cases:
            image = self.client.get(case['image_url'])
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.headers['content-type'], 'image/png')
            self.assertEqual(image.content, notebook_points.SAMPLES[case['sample']].read_bytes())
        self.assertEqual(self.client.get('/test/api/points/samples/not-allowed').status_code, 404)

        # 2. 사례 판독: 선택한 이미지 이름이 실제 판독 함수까지 그대로 전달됩니다.
        def fake_ocr(state, sample):
            """선택된 샘플 이름으로 영수증 판독 결과를 대신 만듭니다."""
            # 1. 판독 대체: 검증 실패 상황에서도 전달된 이름을 기록합니다.
            state.receipt = ReceiptState(status='pending')

            return state, {'model': 'test', 'input': {'sample': sample}, 'prompt': 'test'}
        with patch('services.notebook_points.generate_receipt_data', side_effect=fake_ocr):
            result = self.client.post('/chatbot/points/start', json={'session_id': 'case-3', 'sample': cases[2]['sample'], 'customer_id': cases[2]['customer_id']})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['steps'][0]['input']['sample'], cases[2]['sample'])
