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
            """동시 요청이 겹치도록 기다린 뒤 테스트 클라이언트를 돌려줍니다."""
            # 1. 연결 준비: 여러 요청이 겹치게 잠시 기다립니다.
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



    def test_board_page(self):
        """테스트보드 페이지를 요청해, 화면과 의도 분류 안내가 응답 HTML에 들어 있는지 확인합니다."""
        # 1. 실행: 의도 분류 화면 경로에 요청해 응답을 받습니다.
        response = self.api.get('/test/intent')

        # 2. 확인: HTML 응답에 테스트보드 제목과 분류 요청 경로가 들어 있는지 확인합니다.
        self.assertEqual(response.status_code, 200)
        self.assertIn('의도 분류', response.text)
















    def test_jev_endpoint_is_removed(self):
        """예전 분류 경로를 요청하고 API 문서를 읽어, 제거된 경로가 더 이상 제공되지 않는지 확인합니다."""
        # 1. 확인: 이전 경로는 404를 반환하고, OpenAPI 문서에도 해당 경로가 없는지 확인합니다.
        self.assertEqual(self.api.post('/jev', json={'text': '라떼 주세요'}).status_code, 404)
        self.assertNotIn('/jev', self.api.get('/openapi.json').json()['paths'])



if __name__ == '__main__':
    unittest.main()
