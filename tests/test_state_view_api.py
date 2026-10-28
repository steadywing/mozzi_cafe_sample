"""상태 조회 API를 요청해, 선택한 고객·세션의 턴 기록만 반환하는지 확인합니다."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from common.state_store import save_state
from main import app


class StateViewApiTests(unittest.TestCase):
    def setUp(self):
        """상태 저장소를 임시 폴더로 바꾸고, 저장된 턴을 조회할 API 클라이언트를 준비합니다."""
        # 1. 준비: 상태 저장소를 임시 폴더로 바꾸고, 저장된 턴을 조회할 API 클라이언트를 준비합니다.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch('common.state_store.STATE_DIR', Path(directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.api = TestClient(app)

    def test_returns_only_selected_customer_and_session_records(self):
        """여러 상태 기록을 저장한 뒤 조회해, 선택한 고객·세션의 턴만 순서대로 반환하는지 확인합니다."""
        # 1. 준비: 같은 세션의 두 턴과 다른 고객의 기록을 준비해, 조회 범위를 비교합니다.
        first = {'steps': [{'step': 'input', 'state': {'input': {'text': '첫 요청'}}}]}
        second = {'steps': [{'step': 'input', 'state': {'input': {'text': '다음 요청'}}}]}

        # 2. 실행: 비교할 상태 기록을 저장한 뒤, 한 고객·세션의 기록을 조회합니다.
        save_state('c1', 's1', first)
        save_state('c1', 's1', second)
        save_state('c2', 's1', {'steps': []})
        response = self.api.get('/test/api/states', params={'customer_id': 'c1', 'session_id': 's1'})

        # 3. 확인: 선택한 세션은 두 턴을 순서대로, 기록 없는 세션은 빈 목록으로 반환하는지 확인합니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'states': [first, second]})

        empty = self.api.get('/test/api/states', params={'customer_id': 'c1', 'session_id': 'new'})

        self.assertEqual(empty.json(), {'states': []})

    def test_rejects_missing_or_blank_identifiers(self):
        """상태 조회에 고객·세션 ID를 빼거나 공백으로 보내면, 입력 오류를 반환하는지 확인합니다."""
        # 1. 준비: 고객·세션 ID를 누락하거나 빈칸으로 만든 조회 조건들을 준비합니다.
        for params in [{}, {'customer_id': 'c1'}, {'customer_id': '', 'session_id': 's1'},
                       {'customer_id': 'c1', 'session_id': '   '}]:
            with self.subTest(params=params):

                # 2. 확인: 고객·세션을 식별할 수 없는 조회 조건마다 422를 반환하는지 확인합니다.
                self.assertEqual(self.api.get('/test/api/states', params=params).status_code, 422)

    def test_read_failure_returns_public_error(self):
        """상태 조회 함수에 파일 오류를 발생시켜, 내부 경로 대신 공개 오류 안내를 반환하는지 확인합니다."""
        # 1. 준비: 상태 읽기 함수가 내부 경로를 담은 파일 오류를 내도록 설정합니다.
        with patch('routers.testboard.load_state', side_effect=OSError('private-path')):

            # 2. 실행: /test/api/states 경로에 요청해 응답을 받습니다.
            response = self.api.get('/test/api/states', params={'customer_id': 'c1', 'session_id': 's1'})

        # 3. 확인: 응답 코드가 500이며, 정해 둔 공개 안내만 반환하는지 확인합니다.
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'detail': '상태 기록을 읽을 수 없습니다.'})
