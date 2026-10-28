"""화면에서 대화 저장 API를 호출했을 때, 고객·세션별 기록과 다음 분류 입력이 바뀌는지 확인합니다."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class HistoryApiTests(unittest.TestCase):
    def setUp(self):
        """대화·상태 저장소를 임시 폴더로 바꾸고, 대화 저장 API에 요청할 클라이언트를 준비합니다."""
        # 1. 준비: 대화·상태 저장소를 임시 폴더로 바꾸고, 대화 저장 API에 요청할 클라이언트를 준비합니다.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        patcher = patch('common.history_store.HISTORY_DIR', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        state_patcher = patch('common.state_store.STATE_DIR', self.path / 'state')
        state_patcher.start()
        self.addCleanup(state_patcher.stop)
        self.api = TestClient(app)

    def test_appends_frontend_input_and_output_by_customer_and_session(self):
        """화면에서 보낸 대화를 저장 API에 추가해, 고객·세션별로 기존 대화 뒤에 붙는지 확인합니다."""
        # 1. 준비: 고객·세션 ID와 화면에서 보낼 대화 목록을 준비합니다.
        messages = [{'role': 'user', 'content': '안녕하세요'}, {'role': 'assistant', 'content': '무엇을 도와드릴까요?'}]

        # 2. 실행: /chatbot/history 경로에 요청해 응답을 받습니다.
        response = self.api.post('/chatbot/history', json={'customer_id': 'c1', 'session_id': 's1', 'messages': messages})

        # 3. 확인: 추가 대화의 순서가 맞고, 다른 고객·세션의 기록에는 영향을 주지 않는지 확인합니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'history': messages})

        more = [{'role': 'user', 'content': '추천해 주세요'}]

        response = self.api.post('/chatbot/history', json={'customer_id': 'c1', 'session_id': 's1', 'messages': more})

        self.assertEqual(response.json(), {'history': messages + more})

        from common.history_store import load_history

        self.assertEqual(load_history('c1', 's1'), messages + more)
        self.assertEqual(load_history('c2', 's1'), [])

    def test_empty_identifiers_and_messages_are_rejected(self):
        """고객·세션 ID나 메시지 목록이 비어 있으면, 저장 API가 입력 오류를 반환하는지 확인합니다."""
        # 1. 준비: 고객·세션 ID나 메시지 목록이 비어 있는 요청들을 준비합니다.
        for payload in [
            {'customer_id': '', 'session_id': 's1', 'messages': [{'role': 'user', 'content': '안녕하세요'}]},
            {'customer_id': 'c1', 'session_id': ' ', 'messages': [{'role': 'user', 'content': '안녕하세요'}]},
            {'customer_id': 'c1', 'session_id': 's1', 'messages': []},
        ]:
            with self.subTest(payload=payload):

                # 2. 확인: 잘못된 저장 요청이 422를 반환하고, 대화 파일을 만들지 않는지 확인합니다.
                self.assertEqual(self.api.post('/chatbot/history', json=payload).status_code, 422)

        self.assertEqual(list(self.path.glob('*.json')), [])


    def test_storage_failure_returns_error_without_private_details(self):
        """대화 저장 중 파일 오류를 발생시켜, 내부 경로 없이 오류 안내만 반환하는지 확인합니다."""
        # 1. 준비: 대화 저장 함수가 내부 경로를 담은 오류를 내도록 설정합니다.
        with patch('routers.history.save_history', side_effect=OSError('private path')):

            # 2. 실행: /chatbot/history 경로에 요청해 응답을 받습니다.
            response = self.api.post('/chatbot/history', json={
                'customer_id': 'c1', 'session_id': 's1',
                'messages': [{'role': 'user', 'content': '안녕하세요'}],
            })

        # 3. 확인: 공개 오류만 반환하고, 내부 경로는 응답에 들어 있지 않은지 확인합니다.
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'detail': '대화 기록을 저장하지 못했습니다.'})
