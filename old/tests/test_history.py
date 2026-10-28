"""분류 요청을 실행해, 서버 대화를 읽고 턴별 상태만 저장하는지 확인합니다."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from main import app
from common.history_store import load_history, save_history
from common.state_store import load_state
from schemas.session_state import SessionState


class HistoryTests(unittest.TestCase):
    def setUp(self):
        """대화·상태 저장소를 임시 폴더로 바꾸고, 분류 API에 요청할 클라이언트를 준비합니다."""
        # 1. 준비: 대화·상태 저장소를 임시 폴더로 바꾸고, 분류 API에 요청할 클라이언트를 준비합니다.
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'history'
        self.state_path = Path(self.directory.name) / 'state'

        for target, path in [('common.state_store.STATE_DIR', self.state_path),
                             ('common.history_store.HISTORY_DIR', self.path)]:
            patcher = patch(target, path)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.api = TestClient(app)

    def test_unknown_records_each_state_change_without_saving_history(self):
        """분류 보류 요청을 처리해, 서버 대화는 유지하고 입력·분류·답변 단계 상태를 저장하는지 확인합니다."""
        # 1. 준비: 저장된 대화와 다른 대화를 넣은 요청을 준비해, 서버 기록이 사용되는지 확인합니다.
        previous = [{'role': 'user', 'content': '안녕하세요'},
                    {'role': 'assistant', 'content': '무엇을 도와드릴까요?'}]

        # 2. 실행: 준비한 고객 상태로 분류 함수를 호출해, 반환 결과와 모델에 전달한 입력을 받습니다.
        save_history('c1', 's1', previous)

        intent = {'intent': 'unknown', 'confidence': 0.8}
        reply = {'answer': '어떤 메뉴를 찾으시나요?', 'model': 'test-model'}
        request = {'input': {'text': '추천해줘요'}, 'customer_id': 'c1', 'session_id': 's1',
                   'history': [{'role': 'user', 'content': '변조된 기록'}],
                   'intent': {'intent': 'product_order', 'confidence': 0.9},
                   'answer': {'answer': '이전 답변', 'model': 'old'}}
        captured = {}

        def classify(state):
            """분류에 전달된 상태를 기록하고, 실제 모델 대신 준비한 의도 결과를 돌려줍니다."""
            # 1. 준비: 전달된 상태를 기록하고 준비한 모델 결과를 돌려줍니다.
            captured['classification'] = state.model_dump(mode='json', exclude_unset=True)

            return intent

        def generate(state):
            """답변 생성에 전달된 상태를 기록하고, 실제 모델 대신 준비한 안내 문장을 돌려줍니다."""
            # 1. 준비: 전달된 상태를 기록하고 준비한 모델 결과를 돌려줍니다.
            captured['response'] = state.model_dump(mode='json', exclude_unset=True)

            return reply

        with patch('services.intent_classifier.classify_intent', side_effect=classify), \
             patch('services.intent_classifier.generate_unknown_response', side_effect=generate):
            response = self.api.post('/intent_classifier', json=request)

        # 3. 확인: 서버 대화는 그대로 남고, 입력·분류·답변 단계마다 전체 상태가 저장되는지 확인합니다.
        self.assertEqual(response.status_code, 200)

        result = response.json()

        self.assertEqual(result['history'], previous)
        self.assertEqual(load_history('c1', 's1'), previous)
        self.assertEqual(captured['classification']['history'], previous)
        self.assertEqual(captured['classification']['intent'], request['intent'])
        self.assertEqual(captured['response']['intent'], request['intent'])
        self.assertIsNone(captured['response']['answer'])

        ## 대화 파일과 구분해 한 턴의 단계별 상태 기록을 읽습니다.
        turns = load_state('c1', 's1')

        self.assertEqual(len(turns), 1)

        steps = turns[0]['steps']

        self.assertEqual([step['step'] for step in steps], ['input', 'classify_intent', 'generate_unknown_response'])
        # 입력하지 않은 기본 항목도 모든 단계의 저장 기록에 포함됩니다.

        for step in steps:
            self.assertEqual(set(step['state']), set(SessionState.model_fields))
            self.assertIsNone(step['state']['search'])
            self.assertIsNone(step['state']['recommendation'])

        ## 입력·분류·답변 단계마다 의도와 답변이 바뀌는 위치를 비교합니다.
        self.assertEqual(steps[0]['state']['intent'], request['intent'])
        self.assertEqual(steps[0]['state']['answer'], request['answer'])
        self.assertEqual(steps[1]['state']['intent'], request['intent'])
        self.assertIsNone(steps[1]['state']['answer'])
        self.assertEqual(SessionState.model_validate(steps[2]['state']).model_dump(mode='json', exclude_none=True), result)

    def test_known_intent_records_input_and_classification_only(self):
        """주문으로 분류된 요청을 처리해, 답변 모델 호출 없이 입력·분류 단계만 저장하는지 확인합니다."""
        # 1. 준비: 주문으로 분류하는 대체 결과를 준비하고, 확인 답변 모델은 호출되지 않게 기록합니다.
        intent = {'intent': 'product_order', 'confidence': 0.9}

        with patch('services.intent_classifier.classify_intent', return_value=intent), \
             patch('services.intent_classifier.generate_unknown_response') as llm:

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={
                'customer_id': 'c1', 'input': {'text': '라떼 한 잔'},
                'answer': {'answer': '이전 답변', 'model': 'old'}})

        result = response.json()

        # 3. 확인: 대화 파일이나 모델 답변 없이, 입력과 분류 상태 두 단계만 남는지 확인합니다.
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('answer', result)
        self.assertEqual(result['history'], [])
        self.assertFalse(self.path.exists())

        steps = load_state('c1', result['session_id'])[0]['steps']

        self.assertEqual([step['step'] for step in steps], ['input', 'classify_intent'])
        self.assertEqual(SessionState.model_validate(steps[-1]['state']).model_dump(mode='json', exclude_none=True), result)
        self.assertIsNone(steps[-1]['state']['answer'])
        llm.assert_not_called()

    def test_turn_records_processing_time_in_milliseconds(self):
        """0.125초 걸린 요청을 처리해, 상태 기록에 125밀리초로 저장하는지 확인합니다."""
        # 처리 시간은 초 단위 시각의 차이를 밀리초로 바꿔 기록합니다.
        # 1. 준비: 시계가 0.125초 차이를 반환하도록 바꾸고, 주문 분류 결과를 준비합니다.
        with patch('services.intent_classifier.perf_counter', side_effect=[10.0, 10.125]), \
             patch('services.intent_classifier.classify_intent', return_value={'intent': 'product_order', 'confidence': 0.9}):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={
                'customer_id': 'c1', 'input': {'text': '라떼 한 잔'}})

        # 3. 확인: 저장된 턴의 elapsed_ms가 125.0인지 확인합니다.
        self.assertEqual(response.status_code, 200)

        turn = load_state('c1', response.json()['session_id'])[0]

        self.assertEqual(turn['elapsed_ms'], 125.0)

    def test_unknown_keeps_last_classified_intent_for_followup_guidance(self):
        """분류 보류가 연속으로 나와도, 마지막으로 확인한 작업 의도를 답변 생성에 전달하는지 확인합니다."""
        # 분류 보류가 반복되어도 마지막으로 확인된 작업 의도는 남아 있어야 합니다.
        # 1. 준비: 추천 의도 뒤 unknown 두 번을 반환하게 하고, 답변 생성에 전달된 의도를 기록합니다.
        results = [
            {'intent': 'product_recommendation', 'confidence': 0.9},
            {'intent': 'unknown', 'confidence': 0.8},
            {'intent': 'unknown', 'confidence': 0.7},
        ]
        preserved_intents = []

        def generate(state):
            """답변 생성에 넘어온 의도를 모아 두고, 추천을 이어 갈지 묻는 대체 답변을 돌려줍니다."""
            # 1. 준비: 전달된 상태를 기록하고 준비한 모델 결과를 돌려줍니다.
            preserved_intents.append(state.intent.model_dump(mode='json'))

            return {'answer': '메뉴 추천을 이어서 도와드릴까요?', 'model': 'test-model'}


        with patch('services.intent_classifier.classify_intent', side_effect=results), \
             patch('services.intent_classifier.generate_unknown_response', side_effect=generate):
            state = {'customer_id': 'c1'}
            for text in ['메뉴를 추천해주세요', '음', '글쎄요']:

                # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
                response = self.api.post('/intent_classifier', json={**state, 'input': {'text': text}})

                # 3. 확인: 두 번의 확인 답변에도 처음 확인한 추천 의도가 전달되는지 비교합니다.
                self.assertEqual(response.status_code, 200, response.text)
                state = response.json()

        self.assertEqual(preserved_intents, [results[0], results[0]])
        self.assertEqual(state['intent'], results[0])
        self.assertNotIn('previous_intent', state)

    def test_invalid_input_does_not_create_history_or_state(self):
        """잘못된 고객 입력을 보내, 모델 호출과 대화·상태 파일 생성을 모두 막는지 확인합니다."""
        # 1. 준비: 입력 누락·공백·잘못된 이미지 여부를 준비하고, 분류 함수의 호출 여부를 기록합니다.
        with patch('services.intent_classifier.classify_intent') as classifier:
            for payload in [{}, {'input': {'text': '   '}},
                            {'input': {'text': '안녕하세요', 'has_image': 'yes'}}]:
                with self.subTest(payload=payload):

                    # 2. 확인: 입력 오류를 반환하고, 모델 호출이나 기록 폴더 생성은 없는지 확인합니다.
                    self.assertEqual(self.api.post('/intent_classifier', json=payload).status_code, 422)

        classifier.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.state_path.exists())

    def test_failed_turn_is_not_saved(self):
        """분류 함수가 실패하면, 오류 응답을 반환하고 해당 턴의 대화·상태는 저장하지 않는지 확인합니다."""
        # 1. 준비: 분류 함수가 실패하게 설정하고, 기록 폴더에 파일이 생기는지 확인합니다.
        with patch('services.intent_classifier.classify_intent', side_effect=ValueError('failed')):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={'input': {'text': '실패'}, 'session_id': '../invalid'})

        # 3. 확인: 실패 응답을 반환하고, 대화·상태 폴더에 JSON 파일은 없는지 확인합니다.
        self.assertEqual(response.status_code, 502)
        self.assertEqual(list(self.path.glob('*.json')), [])
        self.assertEqual(list(self.state_path.glob('*.json')), [])

    def test_sequential_turns_accumulate_state_records(self):
        """같은 고객·세션으로 10번 요청해, 입력별 상태가 하나도 빠지지 않고 저장되는지 확인합니다."""
        # 1. 준비: 항상 주문으로 분류하도록 설정하고, 같은 고객·세션에 보낼 10번의 입력을 준비합니다.
        from services.intent_classifier import run_intent_classifier
        intent = {'intent': 'product_order', 'confidence': 0.9}

        with patch('services.intent_classifier.classify_intent', return_value=intent):
            for i in range(10):

                # 2. 실행: 같은 고객·세션으로 입력 문장만 바꾸어 분류 처리를 10번 실행합니다.
                run_intent_classifier(SessionState(input={'text': str(i)}, customer_id='c1', session_id='s1'))

        turns = load_state('c1', 's1')

        # 3. 확인: 10개 상태 기록에 각 입력이 한 번씩 있고, 대화 기록은 추가되지 않았는지 확인합니다.
        self.assertEqual(len(turns), 10)
        self.assertEqual({turn['steps'][0]['state']['input']['text'] for turn in turns}, {str(i) for i in range(10)})
        self.assertEqual(load_history('c1', 's1'), [])
