"""모델 대신 대체 HTTP 응답을 사용해, 의도 분류 API의 입력·출력·연결·오류 처리를 확인합니다."""
import json
from copy import deepcopy
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import httpx2
from fastapi.testclient import TestClient
from typesafe_sdk import RetryPolicy, TypeSafeClient

from main import app
from common import client as clients
from common import prompt_store
from services.intent_classifier import classify_intent
from schemas.session_state import SessionState

ROOT = Path(__file__).resolve().parents[1]
INTENTS = ['product_search', 'event_participation', 'product_recommendation',
           'product_consultation', 'product_order', 'unknown']


class IntentApiTests(unittest.TestCase):
    def setUp(self):
        """대화·상태 저장소를 임시 폴더로 바꾸고, 이전 모델 연결을 정리한 API 클라이언트를 준비합니다."""
        # 1. 준비: 기록 경로를 임시 폴더로 바꾸고, 테스트가 끝나면 파일·연결·경로 설정을 정리하도록 등록합니다.
        history_dir = TemporaryDirectory()
        self.addCleanup(history_dir.cleanup)
        state_patcher = patch('common.state_store.STATE_DIR', Path(history_dir.name) / 'state')
        state_patcher.start()
        self.addCleanup(state_patcher.stop)
        patcher = patch('common.history_store.HISTORY_DIR', Path(history_dir.name) / 'history')
        patcher.start()
        self.addCleanup(patcher.stop)

        clients.close_clients()

        self.addCleanup(clients.close_clients)
        self.api = TestClient(app)

    def test_client_created_once_for_concurrent_calls_and_closed(self):
        """8개 스레드에서 연결을 요청해, 하나만 생성·재사용하고 닫은 뒤에는 새로 만드는지 확인합니다."""
        # 1. 준비: 기존 연결을 닫고 생성 시점을 지연하는 대체 클라이언트를 준비합니다.
        clients.close_clients()
        client = Mock()

        def create(**kwargs):
            """여러 스레드의 첫 요청이 겹치도록 기다린 뒤, 같은 Jev 대체 클라이언트를 돌려줍니다."""
            # 1. 지연: 여러 스레드의 최초 요청이 겹치도록 기다린 뒤 같은 객체를 돌려줍니다.
            sleep(0.02)

            return client

        # 2. 실행: 대체 생성 함수를 연결하고 여덟 스레드에서 클라이언트를 요청합니다.
        with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'test-only-key'}), patch('common.client.TypeSafeClient', side_effect=create) as factory:
            with ThreadPoolExecutor(max_workers=8) as executor:
                created_clients = list(executor.map(lambda _: clients.get_jev_client(), range(8)))

            # 3. 확인: 모든 요청이 같은 객체를 받고 생성 함수는 한 번만 호출되어야 합니다.
            self.assertTrue(all(item is client for item in created_clients))
            factory.assert_called_once()

            # 4. 종료 확인: 열린 객체를 한 번 닫고 다음 요청에서 새로 생성하는지 확인합니다.
            clients.close_clients()
            client.close.assert_called_once()
            clients.get_jev_client()
            self.assertEqual(factory.call_count, 2)
            clients.close_clients()

    def test_two_requests_reuse_open_client(self):
        """분류 요청을 두 번 보내, 같은 Jev 연결을 재사용하고 요청 횟수만 늘어나는지 확인합니다."""
        # 1. 준비: API 키와 Jev 생성 함수를 테스트 값으로 바꾸고, 두 번 호출할 분류 결과를 준비합니다.
        clients.close_clients()

        client = self.sdk_client()

        with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'test-only-key'}), patch('common.client.TypeSafeClient', return_value=client) as factory:

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            first = self.api.post('/intent_classifier', json={'input': {'text': '메뉴를 찾아줘'}})
            second = self.api.post('/intent_classifier', json={'input': {'text': '다른 메뉴를 찾아줘'}})

            # 3. 확인: 연결은 한 번 생성하고, 분류 요청은 두 번 실행했는지 호출 횟수를 비교합니다.
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            factory.assert_called_once()

        clients.close_clients()

    def test_server_shutdown_closes_both_clients(self):
        """서버를 시작했다 종료해, 생성된 Jev·OpenAI 연결을 각각 한 번씩 닫는지 확인합니다."""
        # 서버 수명주기가 종료되면 생성해 둔 두 클라이언트를 모두 닫는다.
        # 1. 준비: Jev·OpenAI 연결을 테스트 객체로 바꿔, 서버 종료 때 각각 닫히는지 기록합니다.
        jev, openai = Mock(), Mock()

        with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'test-only-key', 'OPENAI_API_KEY': 'test-only-key'}), \
             patch('common.client.TypeSafeClient', return_value=jev), patch('common.client.OpenAI', return_value=openai):
            with TestClient(app) as api:

                # 2. 확인: 서버 종료 뒤 두 연결의 close가 각각 한 번 호출되고, 저장된 참조도 비워졌는지 확인합니다.
                self.assertEqual(api.get('/health').status_code, 200)
                self.assertIs(clients.get_jev_client(), jev)
                self.assertIs(clients.get_openai_client(), openai)
                jev.close.assert_not_called()
                openai.close.assert_not_called()

            jev.close.assert_called_once()
            openai.close.assert_called_once()

    def test_close_error_does_not_prevent_other_client_cleanup(self):
        """Jev 연결 종료에 오류를 발생시켜도, OpenAI 연결 정리를 계속하는지 확인합니다."""
        # 1. 준비: Jev를 닫을 때 오류가 나게 하고, OpenAI 연결도 열린 상태로 준비합니다.
        jev, openai = Mock(), Mock()
        jev.close.side_effect = RuntimeError('Jev close failed')

        with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'test-only-key', 'OPENAI_API_KEY': 'test-only-key'}), \
             patch('common.client.TypeSafeClient', return_value=jev), patch('common.client.OpenAI', return_value=openai):
            clients.get_jev_client()
            clients.get_openai_client()

            with self.assertRaisesRegex(RuntimeError, 'Jev close failed'):
                clients.close_clients()

            # 2. 확인: Jev 종료 오류가 전달되어도 OpenAI의 close는 실행됐는지 확인합니다.
            jev.close.assert_called_once()
            openai.close.assert_called_once()

    def sdk_client(self, choice='product_search', *, status=200, malformed=False, timeout=False):
        """선택할 의도와 오류 조건을 받아, 외부 통신 대신 대체 HTTP 응답을 쓰는 SDK 클라이언트를 돌려줍니다."""
        # 1. 준비: SDK 요청과 오류 조건을 확인하고 대체 응답을 준비합니다.
        def respond(request):
            """SDK 요청의 형식을 확인하고, 지정한 의도·서버 오류·시간 초과 조건에 맞는 대체 응답을 돌려줍니다."""
            # 1. 준비: SDK 요청과 오류 조건을 확인하고 대체 응답을 준비합니다.
            if timeout:
                raise httpx2.ReadTimeout('timeout', request=request)
            if status != 200:

                return httpx2.Response(status, json={'error': 'upstream detail must stay private'})

            ## 정상 요청은 의도 선택지와 모델에 보낸 상태·지침을 기록합니다.
            payload = json.loads(request.content)

            self.assertEqual(payload['questions']['intent']['type'], 'choice')
            self.assertEqual(set(payload['questions']['intent']['criteria']), set(INTENTS))

            self.sent_state = payload['state']
            self.sent_prompt = payload['questions']['intent']['instructions']

            ## 선택한 의도와 오류 조건에 맞는 SDK 응답을 만듭니다.
            answer = {'type': 'choice', 'choice': choice, 'confidence': 0.9,
                      'probabilities': {name: float(name == choice) for name in INTENTS}}
            if malformed:
                answer['probabilities']['product_search'] = 4.0

            return httpx2.Response(200, json={
                'model': 'jev-test', 'answers': {'intent': answer},
                'usage': {'input_tokens': 10, 'output_tokens': 1},
            })

        ## 대체 HTTP 응답을 SDK에 연결하고 테스트 뒤 연결을 닫도록 등록합니다.
        client = TypeSafeClient(api_key='test-only-key', model='jev-latest',
                                compression=False, retry=RetryPolicy(max_retries=0),
                                transport=httpx2.MockTransport(respond))
        self.addCleanup(client.close)

        return client

    def test_prompt_read_save_and_next_classification(self):
        """프롬프트를 수정·저장한 뒤 분류해, 새 지침이 파일과 다음 모델 요청에 반영되는지 확인합니다."""
        # 실제 프롬프트 파일 대신 임시 디렉터리에서 저장과 다음 실행을 확인합니다.
        # 1. 준비: 임시 지침 파일과 분류 결과를 준비해, 지침 조회·저장·재사용을 순서대로 시험합니다.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'prompts').mkdir()
            prompt_path = root / 'prompts/intent_router.md'
            prompt_path.write_text('기존 프롬프트', encoding='utf-8')

            with patch('common.prompt_store.PROMPT_DIR', root / 'prompts'):
                prompt_store.load_prompts()

                # 2. 실행: /test/prompt 경로에 요청해 응답을 받습니다.
                response = self.api.get('/test/prompt')

                # 3. 확인: 저장된 파일 내용과 다음 Jev 요청의 지침이 수정한 문장과 같은지 비교합니다.
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {'prompt_file': 'prompts/intent_router.md', 'content': '기존 프롬프트'})

                ## 지침을 수정한 뒤 파일과 조회 응답에 같은 내용이 반영되는지 확인합니다.
                updated = '수정한 분류 기준\n상품 주문을 확인한다.\n'

                response = self.api.put('/test/prompt', json={'content': updated})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(prompt_path.read_text(encoding='utf-8'), updated)
                self.assertEqual(self.api.get('/test/prompt').json()['content'], updated)

                ## 다음 분류 호출이 수정된 지침을 사용하는지 확인합니다.
                with patch('services.intent_classifier.get_jev_client', return_value=self.sdk_client()):
                    response = self.api.post('/intent_classifier', json={'input': {'text': '메뉴를 찾아줘'}})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['intent']['intent'], 'product_search')
                self.assertEqual(self.sent_prompt, updated)
            prompt_store.load_prompts()

    def test_prompts_endpoint_returns_cached_classification_and_unknown_prompts(self):
        """프롬프트 조회 API를 요청해, 파일을 다시 읽지 않고 메모리의 두 지침을 반환하는지 확인합니다."""
        # 실제 모델 호출에 사용할 분류·공통·역할별 지침을 확인합니다.
        # 1. 준비: 메모리에 올린 분류·확인 답변 지침을 준비하고, 파일을 다시 읽지 못하게 설정합니다.
        with TemporaryDirectory() as directory:
            prompt_dir = Path(directory)
            (prompt_dir / 'intent_router.md').write_text('분류 지침', encoding='utf-8')
            (prompt_dir / 'unknown_response.md').write_text('확인 질문 지침', encoding='utf-8')
            (prompt_dir / 'persona.md').write_text('공통 말투', encoding='utf-8')

            with patch('common.prompt_store.PROMPT_DIR', prompt_dir):
                prompt_store.load_prompts()
                with patch('pathlib.Path.read_text', side_effect=AssertionError('파일 재조회')):

                    # 2. 실행: /test/prompts 경로에 요청해 응답을 받습니다.
                    response = self.api.get('/test/prompts')

                # 3. 확인: 조회 결과에 메모리의 두 지침이 들어 있고, 파일 읽기 함수는 호출되지 않았는지 확인합니다.
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {
                    'jev': {'prompt_file': 'prompts/intent_router.md', 'content': '분류 지침'},
                    'persona': {'prompt_file': 'prompts/persona.md', 'content': '공통 말투'},
                    'unknown': {'prompt_file': 'prompts/unknown_response.md', 'content': '확인 질문 지침'},
                })
            prompt_store.load_prompts()

    def test_prompts_are_loaded_once_and_reused(self):
        """프롬프트를 여러 번 요청해, 처음 한 번만 파일을 읽고 이후에는 저장된 내용을 재사용하는지 확인합니다."""
        # 메모리에 불러온 지침을 반복해서 사용하므로 요청마다 파일을 읽지 않습니다.
        # 1. 준비: 프롬프트 저장소를 비우고 파일 읽기를 기록해, 반복 조회 때 읽은 횟수를 셉니다.
        with TemporaryDirectory() as directory:
            prompt_dir = Path(directory)
            (prompt_dir / 'intent_router.md').write_text('캐시한 지침', encoding='utf-8')

            with patch('common.prompt_store.PROMPT_DIR', prompt_dir):
                prompt_store.load_prompts()
                with patch('pathlib.Path.read_text', side_effect=AssertionError('요청마다 다시 읽음')):

                    # 2. 확인: 반복 조회 결과가 같고, 파일 읽기는 필요한 지침마다 한 번만 실행됐는지 확인합니다.
                    self.assertEqual(prompt_store.get_prompt('prompts/intent_router.md'), '캐시한 지침')
                    self.assertEqual(prompt_store.get_prompt('prompts/intent_router.md'), '캐시한 지침')
            prompt_store.load_prompts()

    def test_failed_prompt_write_keeps_previous_cached_content(self):
        """프롬프트 파일 저장에 오류를 발생시켜, 메모리에 있던 이전 지침을 유지하는지 확인합니다."""
        # 파일 저장이 실패하면 메모리도 기존 지침을 유지합니다.
        # 1. 준비: 이전 지침을 메모리에 올린 뒤, 새 지침의 파일 저장만 실패하도록 설정합니다.
        with TemporaryDirectory() as directory:
            prompt_dir = Path(directory)
            (prompt_dir / 'intent_router.md').write_text('기존 지침', encoding='utf-8')

            with patch('common.prompt_store.PROMPT_DIR', prompt_dir):
                prompt_store.load_prompts()
                with patch('pathlib.Path.write_text', side_effect=OSError('쓰기 실패')):
                    with self.assertRaises(OSError):
                        prompt_store.save_prompt('prompts/intent_router.md', '새 지침')

                # 2. 확인: 저장 실패 뒤에도 조회한 지침이 이전 내용인지 확인합니다.
                self.assertEqual(prompt_store.get_prompt('prompts/intent_router.md'), '기존 지침')
            prompt_store.load_prompts()

    def test_invalid_prompt_is_not_saved(self):
        """빈 지침이나 잘못된 값을 저장 요청으로 보내면, 파일 쓰기 전에 거절하는지 확인합니다."""
        # 1. 준비: 빈 문자열 등 잘못된 지침을 준비하고, 파일 쓰기 함수가 호출되는지 기록합니다.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'prompts').mkdir()
            prompt_path = root / 'prompts/intent_router.md'
            prompt_path.write_text('원본', encoding='utf-8')

            with patch('common.prompt_store.PROMPT_DIR', root / 'prompts'):
                prompt_store.load_prompts()
                for content in ['', '  \n ', 'a' * 50001]:
                    with self.subTest(length=len(content)):

                        # 2. 확인: 잘못된 지침에는 입력 오류를 반환하고, 파일 쓰기는 실행하지 않았는지 확인합니다.
                        self.assertEqual(self.api.put('/test/prompt', json={'content': content}).status_code, 422)

                self.assertEqual(prompt_path.read_text(encoding='utf-8'), '원본')
            prompt_store.load_prompts()

    def test_prompt_file_errors_are_sanitized(self):
        """프롬프트 읽기에 파일 오류를 발생시켜, 응답에서 내부 경로를 숨기는지 확인합니다."""
        # 1. 준비: 프롬프트 읽기 함수가 내부 경로를 담은 오류를 내도록 설정합니다.
        with patch('routers.testboard.get_prompt', side_effect=OSError('private file path')):

            # 2. 실행: /test/prompt 경로에 요청해 응답을 받습니다.
            response = self.api.get('/test/prompt')

        # 3. 확인: 실패 응답에 공개 안내만 있고 내부 파일 경로는 없는지 확인합니다.
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('private file path', response.text)

        with patch('pathlib.Path.write_text', side_effect=OSError('private file path')):
            response = self.api.put('/test/prompt', json={'content': '새 프롬프트'})

        self.assertEqual(response.status_code, 500)
        self.assertNotIn('private file path', response.text)

    def test_board_page(self):
        """테스트보드 페이지를 요청해, 화면과 의도 분류 안내가 응답 HTML에 들어 있는지 확인합니다."""
        # 1. 실행: /test 경로에 요청해 응답을 받습니다.
        response = self.api.get('/test')

        # 2. 확인: HTML 응답에 테스트보드 제목과 분류 요청 경로가 들어 있는지 확인합니다.
        self.assertEqual(response.status_code, 200)
        self.assertIn('의도 분류', response.text)

    def test_classifier_returns_only_intent_and_confidence(self):
        """분류 함수에 고객 입력을 넣어, 선택한 의도와 신뢰도 두 항목만 돌려주는지 확인합니다."""
        # 분류 함수는 Jev 원본 대신 선택 결과와 신뢰도만 돌려줍니다.
        # 1. 준비: 고객 입력과 Jev 대체 응답을 준비해, 분류 함수의 반환 항목을 확인합니다.
        with patch('services.intent_classifier.get_jev_client', return_value=self.sdk_client('product_order')):

            # 2. 실행: 준비한 고객 상태로 분류 함수를 호출해, 반환 결과와 모델에 전달한 입력을 받습니다.
            result = classify_intent(SessionState(input={'text': '라떼 주문할게요'}))

        # 3. 확인: 반환값이 준비한 의도·신뢰도 두 항목과 정확히 같은지 비교합니다.
        self.assertEqual(result, {'intent': 'product_order', 'confidence': 0.9})

    def test_classifier_rejects_missing_confidence_or_unknown_choice(self):
        """모델이 신뢰도를 빼거나 모르는 의도를 주면, 유효한 분류 결과로 반환하지 않는지 확인합니다."""
        # 모델이 선택지 밖의 값이나 신뢰도 없는 결과를 주면 임의로 보정하지 않습니다.
        # 1. 준비: 신뢰도가 없거나 선택지 밖 의도를 담은 대체 응답을 준비합니다.
        for choice, confidence in [('product_order', None), ('invalid', 0.9)]:
            client = Mock()
            client.system_one.return_value.model_dump.return_value = {
                'answers': {'intent': {'choice': choice, 'confidence': confidence}}
            }

            with self.subTest(choice=choice, confidence=confidence), \
                 patch('services.intent_classifier.get_jev_client', return_value=client):
                with self.assertRaises(ValueError):

                    # 2. 실행: 준비한 고객 상태로 분류 함수를 호출해, 반환 결과와 모델에 전달한 입력을 받습니다.
                    classify_intent(SessionState(input={'text': '라떼 주문할게요'}))

    def test_cases_and_classifier_inputs(self):
        """테스트 예제를 읽고 분류해, 예제 형식과 Jev에 전달되는 입력·상태가 맞는지 확인합니다."""
        # 1. 준비: 예제 API의 입력 목록을 읽고, 분류 모델에 실제 전달되는 요청을 기록합니다.
        cases = json.loads((ROOT / 'tests/fixtures/intent_cases.json').read_text())

        # 2. 확인: 예제 목록과 Jev 요청의 state·questions가 기대한 형식인지 비교합니다.
        self.assertTrue(any(case['expected_intent'] == 'unknown' for case in cases))
        self.assertEqual(self.api.get('/test/cases').json()['cases'], cases)
        # 실제 SDK에 대체 HTTP 응답을 연결해 분류 함수의 입출력을 확인합니다.

        for case in cases:
            with self.subTest(case=case['id']):
                request = case['input']
                state = SessionState(**request['session_state'], input={
                    'text': request['text'], 'has_image': request['has_image']})
                with patch('services.intent_classifier.get_jev_client', return_value=self.sdk_client(case['expected_intent'])):
                    result = classify_intent(state)
                self.assertEqual(result, {'intent': case['expected_intent'], 'confidence': 0.9})
                self.assertEqual(self.sent_state['session_state'], request['session_state'])

    def test_unknown_returns_classification(self):
        """unknown으로 분류된 결과도, 다른 의도처럼 의도와 신뢰도로 반환하는지 확인합니다."""
        # 1. 준비: Jev가 unknown을 선택하는 대체 응답을 준비합니다.
        with patch('services.intent_classifier.get_jev_client', return_value=self.sdk_client('unknown')):

            # 2. 실행: 준비한 고객 상태로 분류 함수를 호출해, 반환 결과와 모델에 전달한 입력을 받습니다.
            result = classify_intent(SessionState(input={'text': '도와줘'}))

        # 3. 확인: 반환된 의도가 unknown이며 신뢰도도 함께 있는지 비교합니다.
        self.assertEqual(result, {'intent': 'unknown', 'confidence': 0.9})

    def test_invalid_input_does_not_call_sdk(self):
        """잘못된 요청을 분류 API에 보내, 입력 오류를 반환하고 Jev 호출은 하지 않는지 확인합니다."""
        # 1. 준비: 빈 요청과 잘못된 입력을 준비하고, Jev 연결 함수의 호출 여부를 기록합니다.
        with patch('services.intent_classifier.get_jev_client') as client:
            for payload in [{'input': {'text': ''}}, {'input': {'text': '   '}},
                            {'input': []}, {'input': {'text': 'a', 'has_image': 'yes'}},
                            {'input': {'text': 'a' * 4001}}]:
                with self.subTest(payload=str(payload)[:60]):

                    # 2. 확인: 입력 오류 응답을 반환하고 Jev 생성 함수는 호출하지 않았는지 확인합니다.
                    self.assertEqual(self.api.post('/intent_classifier', json=payload).status_code, 422)
            client.assert_not_called()

    def test_invalid_known_state_fields_return_422_without_model_call(self):
        """형식이 틀린 상태 필드를 보내면, 모델 호출 전에 422 입력 오류를 반환하는지 확인합니다."""
        # 상태 스키마의 타입 오류는 Jev 호출 전에 입력 오류로 안내합니다.
        # 1. 준비: 신뢰도·쿠폰 확인 여부 등 자료형이 틀린 상태를 준비하고, 모델 호출을 기록합니다.
        with patch('services.intent_classifier.get_jev_client') as client:
            for state in [
                {'intent': {'intent': 'not_an_intent', 'confidence': 0.9}},
                {'intent': {'intent': 'product_order', 'confidence': 1.1}},
                {'coupon': {'customer_confirmed': 'yes'}},
                {'recommendation': {'allergies': '우유'}},
            ]:
                with self.subTest(state=state):

                    # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
                    response = self.api.post('/intent_classifier', json={**state, 'input': {'text': '이거요'}})

                    # 3. 확인: 응답 코드가 422이고, Jev 연결·분류는 실행하지 않았는지 확인합니다.
                    self.assertEqual(response.status_code, 422, response.text)
            client.assert_not_called()

    def test_state_validation_preserves_extra_data_sent_to_classifier(self):
        """추가 상태 항목이 있는 요청을 검증해, 정의된 기본 필드 밖의 정보도 Jev에 전달하는지 확인합니다."""
        # 상태의 추가 항목도 분류 함수에서 모델로 전달합니다.
        # 1. 준비: 기본 스키마에 없는 추가 항목을 넣은 상태와 Jev 대체 응답을 준비합니다.
        state = {'search': {'candidate_menu_ids': ['M02', 'M01'], 'note': '확인'},
                 'custom': {'source': 'test'}}

        with patch('services.intent_classifier.get_jev_client', return_value=self.sdk_client()):

            # 2. 실행: 준비한 고객 상태로 분류 함수를 호출해, 반환 결과와 모델에 전달한 입력을 받습니다.
            classify_intent(SessionState(**state, input={'text': '이 메뉴 찾아줘'}))

        # 3. 확인: 추가로 넣은 상태가 Jev에 전달된 state에도 그대로 있는지 비교합니다.
        self.assertEqual(self.sent_state['session_state'], state)

    def test_missing_key_is_sanitized(self):
        """Jev API 키 없이 요청해, 키 이름과 내부 오류를 숨긴 실패 응답을 반환하는지 확인합니다."""
        # 1. 준비: API 키가 없는 환경을 만들어, 연결 오류에 내부 정보가 포함되는지 시험합니다.
        with patch.dict('os.environ', {'TYPESAFE_API_KEY': ''}):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={'input': {'text': '아메리카노 두 잔 주세요'}})

        # 3. 확인: 실패 안내에서 API 키 이름과 내부 오류 문구가 드러나지 않는지 확인합니다.
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('TYPESAFE_API_KEY', response.text)

    def test_timeout_and_upstream_errors_are_sanitized(self):
        """Jev 시간 초과와 서버 오류를 발생시켜, 내부 오류 내용이 응답에 드러나지 않는지 확인합니다."""
        # 1. 준비: 시간 초과나 서버 오류를 반환하는 대체 Jev 전송을 준비합니다.
        for client in [self.sdk_client(timeout=True), self.sdk_client(status=401)]:
            with self.subTest(client=client):
                with patch('services.intent_classifier.get_jev_client', return_value=client):

                    # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
                    response = self.api.post('/intent_classifier', json={'input': {'text': '이 메뉴 찾아줘'}})

                # 3. 확인: 시간 초과·서버 오류가 발생해도 응답에 내부 오류 문구가 없는지 확인합니다.
                self.assertEqual(response.status_code, 502)
                self.assertNotIn('upstream detail', response.text)

    def test_combined_known_intent_returns_state_without_calling_openai(self):
        """의도가 정해진 요청을 보내, OpenAI 답변을 생성하지 않고 분류 상태만 반환하는지 확인합니다."""
        # 명확한 의도는 상태에 저장하며 고객 확인 질문을 만들지 않습니다.
        # 1. 준비: 상품검색으로 분류할 대체 Jev 응답을 준비하고, OpenAI 호출 여부를 기록합니다.
        intent = {'intent': 'product_order', 'confidence': 0.9}

        with patch('services.intent_classifier.classify_intent', return_value=intent) as jev, \
             patch('services.intent_classifier.generate_unknown_response') as openai:

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={'input': {'text': '라떼 주세요'}})

        # 3. 확인: 분류 결과와 기존 상태를 보존하고, OpenAI는 호출하지 않았는지 확인합니다.
        self.assertEqual(response.status_code, 200)

        result = response.json()

        self.assertTrue(result.pop('session_id'))

        expected = SessionState(input={'text': '라떼 주세요'}, intent=intent).model_dump(mode='json', exclude_none=True)

        self.assertEqual(result, expected)
        jev.assert_called_once()
        openai.assert_not_called()

    def test_state_preserves_existing_and_extra_data_without_mutating_input(self):
        """여러 업무 상태가 있는 입력을 분류해, 원본을 바꾸지 않고 기존·추가 상태를 결과에 보존하는지 확인합니다."""
        # 1. 준비: 추천·쿠폰·추가 상태를 넣은 원본 입력과 새 분류 결과를 준비합니다.
        from services.intent_classifier import run_intent_classifier
        request = {'text': '라떼 주문해요', 'session_state': {
            'customer_id': 'cust_1', 'custom': {'tag': '유지'},
            'recommendation': {'allergies': [], 'extra_condition': '유지'},
            'order': {'items': [{'product_name': '라떼', 'quantity': 1, 'custom_option': '유지'}]},
        }}
        original = deepcopy(request)
        from schemas.session_state import SessionState
        payload = SessionState.model_validate({**request['session_state'], 'input': {'text': request['text']}})
        original_payload = payload.model_dump()
        intent = {'intent': 'product_order', 'confidence': 0.9}

        with patch('services.intent_classifier.classify_intent', return_value=intent):

            # 2. 실행: 준비한 고객 상태로 분류 함수를 호출해, 반환 결과와 모델에 전달한 입력을 받습니다.
            result = run_intent_classifier(payload)

        # 3. 확인: 원본 입력·기존 상태·추가 항목을 결과와 비교하고, 이전 답변만 지워졌는지 확인합니다.
        self.assertEqual(request, original)
        self.assertEqual(payload.model_dump(), original_payload)
        self.assertEqual(result['intent'], intent)
        self.assertNotIn('answer', result)
        self.assertEqual(result['custom'], {'tag': '유지'})
        self.assertEqual(result['recommendation']['allergies'], [])
        self.assertFalse(result['input']['has_image'])
        self.assertNotIn('search', result)
        self.assertNotIn('preferences', result['recommendation'])
        self.assertNotIn('product_id', result['order']['items'][0])
        self.assertEqual(result['recommendation']['extra_condition'], '유지')
        self.assertEqual(result['order']['items'][0]['custom_option'], '유지')
        self.assertNotIn('session_state', result)

    def test_unknown_preserves_existing_intent_and_order(self):
        """주문 중인 상태에서 분류가 보류되면, 기존 의도·주문은 유지하고 안내 답변만 갱신하는지 확인합니다."""
        # 1. 준비: 진행 중인 주문과 이전 답변이 있는 상태를 만들고, 이번 분류는 unknown으로 설정합니다.
        intent = {'intent': 'unknown', 'confidence': 0.9}
        previous = {'intent': {'intent': 'product_order', 'confidence': None},
                    'order': {'items': [{'product_name': '라떼', 'quantity': 2}],
                              'confirmation_status': 'pending'}}
        reply = {'answer': '어떤 주문을 말씀하시나요?', 'model': 'test-model'}

        with patch('services.intent_classifier.classify_intent', return_value=intent), \
             patch('services.intent_classifier.generate_unknown_response', return_value=reply):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={**previous, 'input': {'text': '이거요'}})

        # 3. 확인: 기존 주문·의도는 같고, 확인 답변과 모델명만 이번 결과로 바뀌었는지 확인합니다.
        self.assertEqual(response.status_code, 200)

        result = response.json()

        self.assertEqual(result['intent'], {'intent': 'product_order'})
        self.assertEqual(result['order'], SessionState.model_validate(previous).model_dump(mode='json', exclude_none=True)['order'])
        self.assertEqual(result['history'], [])
        self.assertEqual(result['answer'], reply)

    def test_unknown_without_existing_intent_keeps_intent_empty(self):
        """이전 작업이 없는 요청이 분류 보류되면, 의도를 임의로 채우지 않고 확인 답변만 주는지 확인합니다."""
        # 1. 준비: 이전 의도가 없는 요청과 unknown 분류·확인 답변을 준비합니다.
        intent = {'intent': 'unknown', 'confidence': 0.9}
        reply = {'answer': '무엇을 도와드릴까요?', 'model': 'test-model'}

        with patch('services.intent_classifier.classify_intent', return_value=intent), \
             patch('services.intent_classifier.generate_unknown_response', return_value=reply):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={'input': {'text': '이거요'}})

        # 3. 확인: 결과에 임의 의도는 없고, 확인 답변과 모델명이 들어 있는지 확인합니다.
        self.assertEqual(response.status_code, 200)

        result = response.json()

        self.assertTrue(result.pop('session_id'))

        expected = SessionState(input={'text': '이거요'}, answer=reply).model_dump(mode='json', exclude_none=True)

        self.assertEqual(result, expected)
        self.assertNotIn('intent', result)
        self.assertNotIn('previous_intent', result)

    def test_previous_model_results_are_replaced_by_current_results(self):
        """이전 모델 결과가 든 상태로 분류해, 이번 의도·신뢰도로 교체하고 오래된 답변은 지우는지 확인합니다."""
        # 1. 준비: 이전 의도·답변·모델 결과가 있는 입력과 이번 분류 결과를 준비합니다.
        from services.intent_classifier import run_intent_classifier
        request = {'text': '라떼 주문해요', 'session_state': {
            'intent': {'intent': 'unknown', 'confidence': 0.5},
            'answer': {'answer': '이전 답변', 'model': 'old'},
        }}
        previous = deepcopy(request)
        intent = {'intent': 'product_order', 'confidence': 0.9}

        with patch('services.intent_classifier.classify_intent', return_value=intent):
            from schemas.session_state import SessionState

            # 2. 실행: 준비한 고객 상태로 분류 함수를 호출해, 반환 결과와 모델에 전달한 입력을 받습니다.
            result = run_intent_classifier(SessionState.model_validate({**request['session_state'], 'input': {'text': request['text']}}))

        # 3. 확인: 이번 의도·신뢰도가 반영되고, 이전 답변·모델 결과는 남지 않는지 확인합니다.
        self.assertEqual(result['intent'], intent)
        self.assertNotIn('answer', result)
        self.assertEqual(request, previous)

    def test_combined_jev_failure_is_sanitized(self):
        """Jev 분류 함수에 오류를 발생시켜, 내부 내용 없이 실패 안내만 반환하는지 확인합니다."""
        # 1. 준비: 분류 함수가 내부 오류를 내도록 바꿔, API가 보여 주는 안내만 확인합니다.
        with patch('services.intent_classifier.classify_intent', side_effect=RuntimeError('private key')):

            # 2. 실행: /intent_classifier 경로에 요청해 응답을 받습니다.
            response = self.api.post('/intent_classifier', json={'input': {'text': '이거요'}})

        # 3. 확인: 실패 응답에서 내부 오류 문구는 숨기고 분류 실패만 안내하는지 확인합니다.
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('private key', response.text)

    def test_jev_endpoint_is_removed(self):
        """예전 분류 경로를 요청하고 API 문서를 읽어, 제거된 경로가 더 이상 제공되지 않는지 확인합니다."""
        # 1. 확인: 이전 경로는 404를 반환하고, OpenAPI 문서에도 해당 경로가 없는지 확인합니다.
        self.assertEqual(self.api.post('/jev', json={'text': '라떼 주세요'}).status_code, 404)
        self.assertNotIn('/jev', self.api.get('/openapi.json').json()['paths'])

    def test_existing_routes_still_work(self):
        """기본 화면·상태 확인·API 문서 경로를 요청해, 기존 경로가 계속 응답하는지 확인합니다."""
        # 1. 확인: 기본 화면·상태 확인·API 문서가 모두 성공 응답을 반환하는지 확인합니다.
        self.assertEqual(self.api.get('/').status_code, 200)
        self.assertEqual(self.api.get('/health').json(), {'status': 'ok'})
        self.assertEqual(self.api.get('/docs').status_code, 200)


if __name__ == '__main__':
    unittest.main()
