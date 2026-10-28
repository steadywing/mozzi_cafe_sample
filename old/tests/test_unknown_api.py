"""분류 보류 상황을 만들어, OpenAI 연결 관리와 확인 답변의 입력·출력을 확인합니다."""
import unittest
import json
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from main import app
from common import client as clients
from schemas.session_state import SessionState


class UnknownResponseTests(unittest.TestCase):
    def setUp(self):
        """기록을 임시 폴더로 보내고 분류 결과를 unknown으로 바꿔, 확인 답변을 시험할 클라이언트를 준비합니다."""
        # 1. 준비: 기록 경로·이전 연결을 정리하고, 분류 함수가 항상 unknown을 돌려주도록 바꿉니다.
        history_dir = TemporaryDirectory()
        self.addCleanup(history_dir.cleanup)
        state_patcher = patch('common.state_store.STATE_DIR', Path(history_dir.name) / 'state')
        state_patcher.start()
        self.addCleanup(state_patcher.stop)
        patcher = patch('common.history_store.HISTORY_DIR', Path(history_dir.name) / 'history')
        patcher.start()
        self.addCleanup(patcher.stop)

        ## 이전 연결을 닫아 각 테스트의 연결 생성과 종료 횟수를 독립적으로 확인합니다.
        clients.close_clients()

        self.addCleanup(clients.close_clients)
        self.api = TestClient(app)

        ## 분류 결과를 고정해 확인 답변 생성 경로로 요청을 보냅니다.
        self.jev_response = {'intent': 'unknown', 'confidence': 0.9}
        patcher = patch('services.intent_classifier.classify_intent', return_value=self.jev_response)
        self.jev = patcher.start()
        self.addCleanup(patcher.stop)

    @patch('common.client.OpenAI')
    def test_reuses_one_client_across_requests_and_closes_it(self, openai_client):
        """여러 번 OpenAI 클라이언트를 요청해, 같은 연결을 재사용하고 한 번만 닫는지 확인합니다."""
        # 1. 준비: OpenAI 키와 생성 함수를 테스트 값으로 바꾸고, 연결 생성·종료 횟수를 기록합니다.
        openai_client.return_value.responses.create.return_value = SimpleNamespace(
            output_text='어떤 도움이 필요하신가요?', model='test-model')

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only-key'}):
            for text in ['이거요', '안녕하세요']:

                # 2. 확인: 두 요청은 성공하고, 연결 생성·요청 실행·종료 횟수가 각각 예상대로인지 확인합니다.
                self.assertEqual(self.api.post('/intent_classifier', json={'input': {'text': text}}).status_code, 200)

        openai_client.assert_called_once()
        self.assertEqual(openai_client.return_value.responses.create.call_count, 2)
        openai_client.return_value.close.assert_not_called()

        clients.close_clients()

        openai_client.return_value.close.assert_called_once()

    @patch('common.client.OpenAI')
    def test_concurrent_first_calls_create_one_client(self, openai_client):
        """여러 스레드에서 동시에 첫 연결을 요청해, OpenAI 클라이언트를 하나만 만드는지 확인합니다."""
        # 1. 준비: OpenAI 연결 생성 시점을 지연시켜, 여러 스레드의 첫 호출이 겹치도록 준비합니다.
        client = Mock()
        def create_client(*args, **kwargs):
            """동시 요청이 겹치도록 잠시 기다린 뒤, 테스트용 OpenAI 클라이언트를 돌려줍니다."""
            # 1. 준비: 동시 요청이 겹치도록 지연한 뒤 같은 대체 클라이언트를 돌려줍니다.
            sleep(0.05)

            return client
        openai_client.side_effect = create_client

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only-key'}):
            with ThreadPoolExecutor(max_workers=8) as pool:

                # 2. 실행: 여러 스레드에서 최초 클라이언트 요청을 동시에 실행합니다.
                created_clients = list(pool.map(lambda _: clients.get_openai_client(), range(8)))

        # 3. 확인: 생성 함수는 한 번만 실행되고, 모든 스레드가 같은 연결을 받았는지 확인합니다.
        openai_client.assert_called_once()
        self.assertTrue(all(item is client for item in created_clients))

    @patch('common.client.OpenAI')
    def test_client_is_recreated_after_close(self, openai_client):
        """OpenAI 연결을 닫은 뒤 다시 요청하면, 닫힌 연결 대신 새 클라이언트를 만드는지 확인합니다."""
        # 1. 준비: 첫 연결을 닫은 뒤 반환할 두 번째 대체 클라이언트를 준비합니다.
        first, second = Mock(), Mock()
        openai_client.side_effect = [first, second]

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only-key'}):

            # 2. 확인: 첫 연결을 닫고, 다음 요청은 두 번째 연결을 받는지 확인합니다.
            self.assertIs(clients.get_openai_client(), first)

            clients.close_clients()

            self.assertIs(clients.get_openai_client(), second)

        first.close.assert_called_once()
        self.assertEqual(openai_client.call_count, 2)

    @patch('common.client.OpenAI')
    def test_missing_key_does_not_create_client(self, openai_client):
        """API 키가 없는 상태로 연결을 요청하면, 클라이언트를 만들지 않고 오류를 내는지 확인합니다."""
        # 1. 준비: OpenAI 키를 비우고, 클라이언트 생성 함수의 호출 여부를 기록합니다.
        with patch.dict('os.environ', {'OPENAI_API_KEY': ''}):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={'input': {'text': '이거요'}})

        # 3. 확인: 502 실패 응답을 반환하고, OpenAI 생성 함수는 호출하지 않았는지 확인합니다.
        self.assertEqual(response.status_code, 502)
        openai_client.assert_not_called()

    @patch('common.client.OpenAI')
    def test_unknown_reply_uses_model_result(self, openai_client):
        """분류 보류 요청을 보내, 입력 상태를 모델에 전달하고 받은 문장·모델명을 응답하는지 확인합니다."""
        # 1. 준비: 대체 모델 답변과 이전 업무 상태를 준비해, 반환 문장과 모델 입력을 비교합니다.
        mock_response = SimpleNamespace(output_text='어떤 도움이 필요하신가요?', model='test-model')
        openai_client.return_value.responses.create.return_value = mock_response
        request = {'input': {'text': '이거요', 'has_image': True}}

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only-key', 'OPENAI_MODEL': 'test-model'}):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json=request)

        # 3. 확인: 응답 문장·모델명과 모델에 보낸 현재 입력·진행 상태가 기대값과 같은지 비교합니다.
        self.assertEqual(response.status_code, 200, response.text)

        result = response.json()

        self.assertTrue(result.pop('session_id'))

        expected = SessionState(input=request['input'],
                                answer={'answer': '어떤 도움이 필요하신가요?', 'model': 'test-model'}).model_dump(mode='json', exclude_none=True)

        self.assertEqual(result, expected)
        self.jev.assert_called_once()

        ## 고객 응답과 별도로 모델에 보낸 현재 문장과 이미지 여부를 확인합니다.
        call = openai_client.return_value.responses.create.call_args.kwargs

        self.assertNotIn('instructions', call)
        self.assertEqual(call['input'][-1]['role'], 'user')
        self.assertEqual(json.loads(call['input'][-1]['content'])['text'], '이거요')
        self.assertTrue(json.loads(call['input'][-1]['content'])['has_image'])
        self.assertNotIn('test-only-key', response.text)

    @patch('common.client.OpenAI')
    def test_unknown_instructions_place_persona_before_role(self, openai_client):
        """분류 보류 답변을 요청해, 공통 말투 지침 뒤에 역할 지침을 연결하는지 확인합니다."""
        # 실제 고객 답변 생성에 공통 말투와 역할별 지침이 순서대로 전달됩니다.
        # 1. 준비: 대체 OpenAI 답변을 준비하고, 모델에 전달한 system 지침을 기록합니다.
        openai_client.return_value.responses.create.return_value = SimpleNamespace(
            output_text='어떤 도움이 필요하신가요?', model='test-model')
        prompts = {'prompts/persona.md': '공통 말투', 'prompts/unknown_response.md': '확인 질문 지침'}

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only-key'}), \
             patch('services.intent_classifier.get_prompt', side_effect=prompts.__getitem__):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={'input': {'text': '이거요'}})

        # 3. 확인: system 메시지에서 공통 말투가 역할 지침보다 먼저 나오는지 확인합니다.
        self.assertEqual(response.status_code, 200)

        messages = openai_client.return_value.responses.create.call_args.kwargs['input']

        self.assertEqual(messages[0], {'role': 'system', 'content': '공통 말투\n\n확인 질문 지침'})

    @patch('common.client.OpenAI')
    def test_unknown_reply_sends_previous_messages_in_order(self, openai_client):
        """이전 대화가 있는 요청을 보내, 모델에 발화자와 대화 순서를 그대로 전달하는지 확인합니다."""
        # 이전 고객과 챗봇 문장을 각각 원래 역할로 전달합니다.
        # 1. 준비: 고객·챗봇의 이전 대화와 이번 질문을 준비해, 모델 메시지의 순서를 비교합니다.
        openai_client.return_value.responses.create.return_value = SimpleNamespace(
            output_text='무엇을 도와드릴까요?', model='test-model')

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only-key'}):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            first = self.api.post('/intent_classifier', json={'input': {'text': '안녕하세요'}})

            state = first.json()
            # 분류 처리와 별도로 기록된 대화를 다음 턴에서 읽습니다.

            from common.history_store import save_history

            save_history(None, state['session_id'], [
                {'role': 'user', 'content': '안녕하세요'},
                {'role': 'assistant', 'content': '무엇을 도와드릴까요?'},
            ])
            second = self.api.post('/intent_classifier', json={**state, 'input': {'text': '추천해 주세요'}})

        # 3. 확인: 이전 고객·챗봇 문장 뒤에 이번 입력이 붙고, 발화자와 순서가 유지되는지 비교합니다.
        self.assertEqual(second.status_code, 200)

        messages = openai_client.return_value.responses.create.call_args.kwargs['input']

        self.assertEqual(messages[1:3], [
            {'role': 'user', 'content': '안녕하세요'},
            {'role': 'assistant', 'content': '무엇을 도와드릴까요?'},
        ])
        self.assertEqual(json.loads(messages[-1]['content'])['text'], '추천해 주세요')

    @patch('common.client.OpenAI')
    def test_empty_model_response_is_error(self, openai_client):
        """모델이 공백 답변을 돌려주면, 빈 답변을 성공 응답 대신 오류로 처리하는지 확인합니다."""
        # 1. 준비: OpenAI가 공백만 돌려주도록 설정해, 빈 답변 처리 방식을 시험합니다.
        openai_client.return_value.responses.create.return_value = SimpleNamespace(output_text='', model='test-model')

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only-key'}):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={'input': {'text': '이거요'}})

        # 3. 확인: 빈 답변은 502로 응답하고, 정해 둔 공개 실패 안내를 보여 주는지 확인합니다.
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('test-only-key', response.text)

if __name__ == '__main__':
    unittest.main()
