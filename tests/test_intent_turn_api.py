"""노트북 의도 분류의 세션별 흐름을 외부 모델 호출 없이 확인합니다."""
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from main import app


class IntentTurnApiTests(unittest.TestCase):
    def setUp(self):
        """각 테스트에 독립된 대체 Jev 연결과 테스트 클라이언트를 준비합니다."""
        # 1. 준비: 모델 응답과 요청 입력을 기록할 대체 연결을 만듭니다.
        self.sent = []
        self.choices = []
        self.client = Mock()

        def classify(*, state, questions):
            """분류 입력을 기록하고 미리 정한 의도와 신뢰도를 응답으로 돌려줍니다."""
            # 1. 응답 준비: 매 턴 받은 입력을 보관하고 순서대로 준비한 결과를 반환합니다.
            self.sent.append(state)
            response = Mock()
            response.model_dump.return_value = {
                'answers': {'intent': {'choice': self.choices.pop(0), 'confidence': 0.9}}
            }

            return response

        self.client.system_one.side_effect = classify
        self.patcher = patch('services.intent_notebook.get_jev_client', return_value=self.client)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        ## 분류 보류 답변도 대체 모델로 만들어 외부 호출을 막습니다.
        self.openai = Mock()
        self.openai.responses.create.return_value = Mock(output_text='어떤 도움이 필요하신가요?', model='test-model')
        self.openai_patcher = patch('services.intent_notebook.get_openai_client', return_value=self.openai)
        self.openai_patcher.start()
        self.addCleanup(self.openai_patcher.stop)
        self.api = TestClient(app)
        self.addCleanup(self.api.close)

    def test_order_followup_and_unrelated_input_are_classified_each_turn(self):
        """주문 후 확인과 무관한 질문을 이어 보내, 매 턴 이전 의도와 새 결과를 확인합니다."""
        # 1. 준비: 분류 모델이 순서대로 주문, 주문 후속, 무관한 질문을 반환하도록 정합니다.
        self.choices = ['product_order', 'product_order', 'unknown']
        self.api.delete('/chatbot/intent/turn/test-order')
        turns = ['아이스 아메리카노 주세요', '네, 맞아요', '근의 공식 알려줘']
        results = []

        # 2. 실행: 같은 세션에서 세 문장을 차례로 보냅니다.
        for text in turns:
            response = self.api.post('/chatbot/intent/turn', json={
                'session_id': 'test-order', 'input': {'text': text}
            })
            self.assertEqual(response.status_code, 200, response.text)
            results.append(response.json()['state'])

        # 3. 확인: 매 턴 분류하고 이전 결과와 현재 분류, 고객 메시지를 차례로 저장합니다.
        self.assertEqual([item['intent']['intent'] for item in results],
                         ['product_order', 'product_order', 'unknown'])
        self.assertEqual([item['previous_intent'] for item in results],
                         [None, 'product_order', 'product_order'])
        self.assertEqual([item['previous_intent'] for item in self.sent],
                         [None, 'product_order', 'product_order'])
        self.assertEqual([message['content'] for message in results[-1]['history']],
                         turns + ['어떤 도움이 필요하신가요?'])
        self.assertEqual(set(self.sent[-1]), {'text', 'previous_intent', 'has_image'})

    def test_separate_sessions_and_reset_do_not_reuse_prior_intent(self):
        """두 세션과 초기화한 세션을 요청해, 다른 대화의 이전 의도가 섞이지 않는지 확인합니다."""
        # 1. 준비: 두 세션의 이전 기록을 지우고 세 번의 분류 결과를 준비합니다.
        self.api.delete('/chatbot/intent/turn/test-a')
        self.api.delete('/chatbot/intent/turn/test-b')
        self.choices = ['product_order', 'product_consultation', 'unknown']

        # 2. 실행: A와 B를 각각 요청하고 A를 초기화한 뒤 다시 요청합니다.
        for session_id in ['test-a', 'test-b']:
            response = self.api.post('/chatbot/intent/turn', json={
                'session_id': session_id, 'input': {'text': '안녕하세요'}
            })
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.api.delete('/chatbot/intent/turn/test-a').status_code, 200)
        response = self.api.post('/chatbot/intent/turn', json={
            'session_id': 'test-a', 'input': {'text': '네'}
        })

        # 3. 확인: 각 세션의 첫 요청과 초기화 이후 요청에는 이전 의도가 없습니다.
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item['previous_intent'] for item in self.sent], [None, None, None])
        self.assertEqual(len(response.json()['state']['history']), 2)

    def test_unknown_answer_is_shown_and_saved_for_the_next_turn(self):
        """분류 보류 뒤 새 요청을 보내, 확인 답변과 대화 기록 및 답변 초기화를 확인합니다."""
        # 1. 준비: 보류와 주문 결과를 차례로 받고 독립 세션에서 시작합니다.
        self.api.delete('/chatbot/intent/turn/test-unknown-answer')
        self.choices = ['unknown', 'product_order']

        # 2. 실행: 보류 문장과 고객의 후속 요청을 같은 세션으로 보냅니다.
        first = self.api.post('/chatbot/intent/turn', json={
            'session_id': 'test-unknown-answer', 'input': {'text': '네, 맞아요'}
        })
        second = self.api.post('/chatbot/intent/turn', json={
            'session_id': 'test-unknown-answer', 'input': {'text': '커피 주문할게요'}
        })

        # 3. 확인: 생성 단계와 답변을 저장하고 다음 턴에는 이전 답변을 다시 표시하지 않습니다.
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        data = first.json()
        self.assertEqual(data['state']['answer'], {'answer': '어떤 도움이 필요하신가요?', 'model': 'test-model'})
        self.assertEqual([step['step'] for step in data['steps']],
                         ['prepare_state', 'classify_intent', 'generate_unknown_response', 'save_state'])

        ## 답변 생성 기록에 실제 호출에 사용한 지침과 입력이 남는지 비교합니다.
        generated = data['steps'][2]
        self.assertTrue(generated['prompt'])
        self.assertTrue(generated['input'])
        self.assertEqual(generated['model'], 'test-model')
        self.assertEqual(generated['input'], self.openai.responses.create.call_args.kwargs['input'])
        self.assertEqual(generated['input'][0], {'role': 'system', 'content': generated['prompt']})
        self.assertEqual(data['state']['history'][-1], {'role': 'assistant', 'content': '어떤 도움이 필요하신가요?'})

        ## 다음 턴은 이전 의도와 대화만 이어받고 답변은 새로 준비하는지 확인합니다.
        self.assertEqual(second.json()['state']['previous_intent'], 'unknown')
        self.assertIsNone(second.json()['state']['answer'])
        self.assertEqual([item['role'] for item in second.json()['state']['history']], ['user', 'assistant', 'user'])
        self.openai.responses.create.assert_called_once()

    def test_unknown_answer_failure_does_not_save_failed_turn(self):
        """답변 생성이 실패한 뒤 재시도해, 실패한 턴이 세션에 남지 않는지 확인합니다."""
        # 1. 준비: 첫 답변 생성을 실패시키고 두 분류 결과를 보류로 정합니다.
        self.api.delete('/chatbot/intent/turn/test-unknown-failure')
        self.choices = ['unknown', 'unknown']
        self.openai.responses.create.side_effect = [RuntimeError('모델 연결 실패'),
                                                   Mock(output_text='어떤 도움이 필요하신가요?', model='test-model')]

        # 2. 실행: 같은 입력을 실패 후 다시 전송합니다.
        payload = {'session_id': 'test-unknown-failure', 'input': {'text': '네'}}
        failed = self.api.post('/chatbot/intent/turn', json=payload)
        retried = self.api.post('/chatbot/intent/turn', json=payload)

        # 3. 확인: 실패는 오류로 알리고 성공한 한 턴의 대화만 보존합니다.
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertIsNone(retried.json()['state']['previous_intent'])
        self.assertEqual([item['role'] for item in retried.json()['state']['history']], ['user', 'assistant'])

    def test_unknown_followup_includes_prior_answer_once(self):
        """연속으로 분류 보류된 요청을 보내, 이전 답변과 현재 문장이 모델에 한 번씩 전달되는지 확인합니다."""
        # 1. 준비: 두 입력을 보류로 분류하고 독립 세션에서 시작합니다.
        self.api.delete('/chatbot/intent/turn/test-unknown-followup')
        self.choices = ['unknown', 'unknown']

        # 2. 실행: 첫 질문에 답변을 받은 뒤 다른 모호한 문장을 보냅니다.
        for text in ['네', '그거요']:
            response = self.api.post('/chatbot/intent/turn', json={
                'session_id': 'test-unknown-followup', 'input': {'text': text}
            })
            self.assertEqual(response.status_code, 200, response.text)

        # 3. 확인: 이전 대화와 이번 입력을 중복 없이 모델에 전달합니다.
        messages = self.openai.responses.create.call_args.kwargs['input']
        self.assertEqual([item['role'] for item in messages], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(messages[1]['content'], '네')
        self.assertEqual(messages[2]['content'], '어떤 도움이 필요하신가요?')
        self.assertIn('그거요', messages[3]['content'])

    def test_customer_information_is_retained_and_image_flag_reaches_model(self):
        """고객 정보가 있는 첫 요청과 이미지 후속 요청을 보내, 정보 유지와 모델 입력을 확인합니다."""
        # 1. 준비: 독립 세션과 두 번의 분류 결과를 준비합니다.
        self.api.delete('/chatbot/intent/turn/test-customer')
        self.choices = ['product_order', 'product_search']

        # 2. 실행: 고객 정보가 있는 문장과 이미지가 첨부된 후속 문장을 보냅니다.
        first = self.api.post('/chatbot/intent/turn', json={
            'session_id': 'test-customer',
            'customer_info': {'customer_id': 'practice', 'name': '실습 고객'},
            'input': {'text': '커피 주문할게요'},
        })
        second = self.api.post('/chatbot/intent/turn', json={
            'session_id': 'test-customer',
            'input': {'text': '이 사진 속 메뉴를 찾아주세요', 'has_image': True},
        })

        # 3. 확인: 고객 정보가 유지되고 분류 모델에는 필요한 세 항목만 전달됩니다.
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()['state']['customer']['name'], '실습 고객')
        self.assertEqual(self.sent[-1], {
            'text': '이 사진 속 메뉴를 찾아주세요',
            'previous_intent': 'product_order',
            'has_image': True,
        })
        self.assertEqual([step['step'] for step in second.json()['steps']],
                         ['prepare_state', 'classify_intent', 'save_state'])

    def test_saved_snapshot_does_not_change_or_duplicate(self):
        """저장한 상태를 다시 저장하고 원본을 바꿔, 중복 저장과 스냅샷 변경을 막는지 확인합니다."""
        # 1. 준비: 실제 상태 저장소와 한 세션의 분류된 상태를 준비합니다.
        from schemas.session_state import SessionState
        from services.intent_notebook import save_state, state_store

        state_store.pop('test-snapshot', None)
        self.addCleanup(state_store.pop, 'test-snapshot', None)
        state = SessionState(session_id='test-snapshot', input={'text': '주문할게요'},
                             intent={'intent': 'product_order', 'confidence': 0.9})

        # 2. 실행: 같은 상태를 두 번 저장하고 저장 뒤 원본을 수정합니다.
        save_state(state)
        save_state(state)
        state.input.text = '변경된 원본'

        # 3. 확인: 스냅샷은 한 개이며 저장 당시의 문장을 보존합니다.
        self.assertEqual(len(state_store['test-snapshot']), 1)
        self.assertEqual(state_store['test-snapshot'][0]['input']['text'], '주문할게요')

    def test_intent_steps_are_saved_by_turn_and_reset_together(self):
        """의도 분류를 이어 실행하면 각 단계가 조회되고 세션 초기화 때 함께 지워지는지 확인합니다."""
        # 1. 세션 준비: 기존 분류 상태와 단계 기록을 비우고 두 결과를 정합니다.
        self.api.delete('/chatbot/intent/turn/test-step-trace')
        self.choices = ['product_order', 'product_search']

        # 2. 턴 실행: 같은 세션에서 주문 문장과 이미지 검색 문장을 분류합니다.
        first = self.api.post('/chatbot/intent/turn', json={
            'session_id': 'test-step-trace', 'input': {'text': '라떼 주문할게요'}
        })
        second = self.api.post('/chatbot/intent/turn', json={
            'session_id': 'test-step-trace', 'input': {'text': '이 사진 메뉴를 찾아요', 'has_image': True}
        })
        trace = self.api.get('/test/api/traces/intent/test-step-trace')

        # 3. 기록 확인: 이전 분류와 각 함수의 입력이 다음 턴 이후에도 유지됩니다.
        self.assertEqual((first.status_code, second.status_code, trace.status_code), (200, 200, 200))
        self.assertEqual((first.json()['turn_index'], second.json()['turn_index']), (1, 2))
        turns = trace.json()['turns']
        self.assertEqual(len(turns), 2)
        self.assertIsNone(turns[0]['steps'][0]['state']['intent'])
        self.assertEqual(turns[0]['steps'][1]['state']['intent']['intent'], 'product_order')
        self.assertEqual(turns[1]['steps'][1]['input'], {
            'text': '이 사진 메뉴를 찾아요', 'previous_intent': 'product_order', 'has_image': True
        })

        ## 세션을 지운 뒤에는 앞선 분류 기록도 다시 나타나지 않는지 확인합니다.
        self.api.delete('/chatbot/intent/turn/test-step-trace')
        self.assertEqual(self.api.get('/test/api/traces/intent/test-step-trace').json()['turns'], [])

    def test_test_cases_include_independent_and_sequential_examples(self):
        """사례 목록을 조회해 단일 입력과 연속 대화 사례가 사용 가능한지 확인합니다."""
        # 1. 실행: 테스트보드에 제공되는 의도 분류 사례를 조회합니다.
        response = self.api.get('/test/api/intent-turn/cases')

        # 2. 확인: 이미지 사례와 주문 후속 대화의 입력 및 예상 의도가 들어 있습니다.
        self.assertEqual(response.status_code, 200, response.text)
        cases = {item['id']: item for item in response.json()['cases']}
        self.assertTrue(cases['search-image']['input']['has_image'])
        self.assertEqual([turn['expected_intent'] for turn in cases['order-followup']['turns']],
                         ['product_order', 'product_order', 'unknown', 'product_consultation'])


if __name__ == '__main__':
    unittest.main()
