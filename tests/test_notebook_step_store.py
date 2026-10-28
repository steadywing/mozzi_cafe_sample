"""노트북 기능의 단계별 상태를 세션별로 보관하는지 확인합니다."""
import unittest
from copy import deepcopy
from importlib import import_module
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class NotebookStepStoreTests(unittest.TestCase):
    """실습 기능과 세션별 단계 스냅샷의 분리·조회·초기화를 확인합니다."""

    def test_each_step_is_an_independent_saved_snapshot(self):
        """두 단계의 상태를 저장한 뒤 원본을 바꾸어도 각 단계의 이전 값이 유지되는지 확인합니다."""
        # 1. 상태 준비: 한 턴에서 순서대로 바뀐 상태를 만듭니다.
        from common.notebook_step_store import clear_trace, get_trace, save_turn
        clear_trace('order', 'independent-state')
        steps = [
            {'step': 'generate_order_draft', 'state': {'order': {'status': 'draft'}}},
            {'step': 'validate_order', 'state': {'order': {'status': 'pending'}}},
        ]

        # 2. 저장 실행: 턴을 저장한 뒤 원본과 조회 결과를 바꿉니다.
        turn_index = save_turn('order', 'independent-state', steps, {'order': {'status': 'pending'}})
        steps[0]['state']['order']['status'] = 'changed'
        returned = get_trace('order', 'independent-state')
        returned[0]['steps'][0]['state']['order']['status'] = 'changed-again'

        # 3. 저장 확인: 저장한 두 상태는 서로 다른 시점으로 남습니다.
        self.assertEqual(turn_index, 1)
        self.assertEqual(get_trace('order', 'independent-state')[0]['steps'][0]['state']['order']['status'], 'draft')
        self.assertEqual(get_trace('order', 'independent-state')[0]['steps'][1]['state']['order']['status'], 'pending')

    def test_trace_api_keeps_turns_separate_and_clears_one_session(self):
        """서로 다른 기능과 세션의 기록을 나누고 선택한 기록만 지우는지 확인합니다."""
        # 1. 기록 준비: 같은 세션에서 두 턴과 다른 기능의 턴을 저장합니다.
        from common.notebook_step_store import clear_trace, save_turn
        from routers.traces import router
        clear_trace('unknown', 'trace-a')
        clear_trace('order', 'trace-a')
        save_turn('unknown', 'trace-a', [{'step': 'first', 'state': {'answer': 'a'}}], {'answer': 'a'})
        save_turn('unknown', 'trace-a', [{'step': 'second', 'state': {'answer': 'b'}}], {'answer': 'b'})
        save_turn('order', 'trace-a', [{'step': 'order', 'state': {}}], {})
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # 2. 조회와 삭제: unknown의 기록 두 턴을 확인하고 그것만 지웁니다.
        response = client.get('/test/api/traces/unknown/trace-a')
        deleted = client.delete('/test/api/traces/unknown/trace-a')

        # 3. 범위 확인: 주문 기록은 그대로 남고 잘못된 기능 이름은 거부됩니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual([turn['turn_index'] for turn in response.json()['turns']], [1, 2])
        self.assertEqual(deleted.json(), {'deleted': True})
        self.assertEqual(client.get('/test/api/traces/unknown/trace-a').json()['turns'], [])
        self.assertEqual(len(client.get('/test/api/traces/order/trace-a').json()['turns']), 1)
        self.assertEqual(client.get('/test/api/traces/unknown-ish/trace-a').status_code, 404)

    def test_every_notebook_route_records_each_turn(self):
        """여섯 실습 API를 두 번 호출하면 각 턴의 단계 상태가 따로 남는지 확인합니다."""
        # 1. 요청 준비: 외부 모델 없이 각 실습 라우터에 같은 두 단계 결과를 돌려줍니다.
        from routers.traces import router as trace_router
        cases = [
            ('unknown', '/chatbot/unknown', 'run_unknown', {'input': {'text': '무슨 뜻인가요?'}}),
            ('order', '/chatbot/order/practice', 'run_order', {'input': {'text': '라떼 한 잔 주세요'}}),
            ('recommendation', '/chatbot/recommendation', 'run_recommendation', {'input': {'text': '추천해 주세요'}}),
            ('search', '/chatbot/search', 'run_search', {'text': '비슷한 상품', 'sample': 'sample.png'}),
            ('consultation', '/chatbot/consultation', 'run_consultation', {'input': {'text': '몇 시까지 열어요?'}}),
            ('points', '/chatbot/points/start', 'start_points', {'session_id': 'points-trace-case', 'sample': 'receipt-001', 'customer_id': 'cust_001'}),
        ]

        # 2. 요청 실행: 응답에서 받은 세션 ID로 다음 턴을 이어 갑니다.
        for feature, path, service_name, body in cases:
            with self.subTest(feature=feature):
                module_name = {'order': 'order_practice'}.get(feature, feature)
                module = import_module(f'routers.{module_name}')
                app = FastAPI()
                app.include_router(module.router)
                app.include_router(trace_router)
                client = TestClient(app)
                payload = deepcopy(body)
                call_results = [
                    {'state': {'phase': number}, 'steps': [
                        {'step': 'prepare', 'state': {'phase': 0}},
                        {'step': 'finish', 'state': {'phase': number}},
                    ]} for number in (1, 2)
                ]
                with patch.object(module, service_name, side_effect=call_results):
                    if feature == 'search':
                        with patch.object(module, 'sample_names', return_value=['sample.png']):
                            first = client.post(path, json=payload)
                            payload['session_id'] = first.json()['session_id']
                            second = client.post(path, json=payload)
                    else:
                        first = client.post(path, json=payload)
                        payload['session_id'] = first.json()['session_id']
                        second = client.post(path, json=payload)

                # 3. 기록 확인: 응답과 조회 기록에 순서와 단계별 이전 상태가 보존됩니다.
                self.assertEqual((first.status_code, second.status_code), (200, 200))
                self.assertEqual((first.json()['turn_index'], second.json()['turn_index']), (1, 2))
                self.assertEqual(first.json()['session_id'], second.json()['session_id'])
                trace = client.get(f"/test/api/traces/{feature}/{first.json()['session_id']}").json()
                self.assertEqual([turn['state']['phase'] for turn in trace['turns']], [1, 2])
                self.assertEqual([step['state']['phase'] for step in trace['turns'][0]['steps']], [0, 1])


if __name__ == '__main__':
    unittest.main()
