"""전체 초기화 API를 요청해, 다른 자료를 보존하고 대화·상태 기록만 비우는지 확인합니다."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from common.history_store import load_history, save_history
from common.state_store import load_state, save_state
from main import app


class ResetAllApiTests(unittest.TestCase):
    def setUp(self):
        """대화·상태 저장소를 임시 폴더로 바꾸고, 전체 초기화 API를 시험할 클라이언트를 준비합니다."""
        # 1. 준비: 대화·상태 저장소를 임시 폴더로 바꾸고, 전체 초기화 API를 시험할 클라이언트를 준비합니다.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for target, path in [('common.history_store.HISTORY_DIR', self.root / 'history'),
                             ('common.state_store.STATE_DIR', self.root / 'state')]:
            patcher = patch(target, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.api = TestClient(app)

    def test_reset_removes_all_customers_and_sessions_but_keeps_other_data(self):
        """전체 초기화를 요청해, 모든 대화·상태만 삭제하고 고객 자료는 남기는지 확인합니다."""
        # 1. 준비: 임시 고객 자료와 여러 고객·세션의 대화·상태를 저장해, 삭제 범위를 비교합니다.
        customers = self.root / 'customers.json'
        customers.write_text('[]')
        for customer, session in [('c1', 's1'), ('c1', 's2'), ('c2', 's1')]:
            save_history(customer, session, [{'role': 'user', 'content': '테스트'}])
            save_state(customer, session, {'steps': []})
        # 2. 실행: 전체 초기화 API를 호출해, 대화·상태 기록을 한꺼번에 지웁니다.
        response = self.api.delete('/test/api/sessions')

        # 3. 확인: 기록은 없어지고 고객 자료는 남으며, 다시 삭제하면 0건을 반환하는지 확인합니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'deleted': {'history': 2, 'state': 2}})
        for customer, session in [('c1', 's1'), ('c1', 's2'), ('c2', 's1')]:
            self.assertEqual(load_history(customer, session), [])
            self.assertEqual(load_state(customer, session), [])
        self.assertEqual(customers.read_text(), '[]')
        self.assertEqual(self.api.delete('/test/api/sessions').json(), {'deleted': {'history': 0, 'state': 0}})

    def test_reset_is_safe_when_record_folders_do_not_exist(self):
        """기록 폴더가 없는 상태로 초기화해도, 오류 없이 삭제 건수 0을 반환하는지 확인합니다."""
        # 1. 실행과 확인: 기록 폴더를 만들지 않고 초기화를 요청해, 성공 응답과 삭제 건수 0을 비교합니다.
        response = self.api.delete('/test/api/sessions')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'deleted': {'history': 0, 'state': 0}})
