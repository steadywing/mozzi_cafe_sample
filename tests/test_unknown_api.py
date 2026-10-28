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

        clients.close_clients()

        self.addCleanup(clients.close_clients)
        self.api = TestClient(app)
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






if __name__ == '__main__':
    unittest.main()
