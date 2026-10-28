"""세션 삭제 API를 요청해, 선택한 고객·세션의 대화와 상태만 지워지는지 확인합니다."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from common.history_store import load_history, save_history
from common.state_store import load_state, save_state
from main import app


class DeleteSessionApiTests(unittest.TestCase):
    def setUp(self):
        """대화·상태 저장소를 임시 폴더로 바꾸고, 세션 삭제 API에 요청할 클라이언트를 준비합니다."""
        # 1. 준비: 대화·상태 저장소를 임시 폴더로 바꾸고, 세션 삭제 API에 요청할 클라이언트를 준비합니다.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.root = root

        for target, path in [('common.history_store.HISTORY_DIR', root / 'history'),
                             ('common.state_store.STATE_DIR', root / 'state')]:
            patcher = patch(target, path)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.api = TestClient(app)

    def test_deletes_only_selected_customer_and_session(self):
        """여러 고객·세션을 저장한 뒤 하나를 삭제해, 선택한 대화·상태만 지워지는지 확인합니다."""
        # 1. 준비: 다른 고객과 다른 세션을 함께 저장해, 선택 대상만 삭제되는지 비교합니다.
        for customer, session in [('c1', 's1'), ('c2', 's1'), ('c1', 's2')]:

            # 2. 실행: 비교할 고객·세션별로 대화와 상태를 저장한 뒤, 선택한 세션의 삭제를 요청합니다.
            save_history(customer, session, [{'role': 'user', 'content': '대화'}])
            save_state(customer, session, {'steps': []})
        response = self.api.delete('/test/api/session', params={'customer_id': 'c1', 'session_id': 's1'})

        # 3. 확인: 선택한 기록은 비고, 다른 고객·세션의 기록과 고객 파일은 남는지 확인합니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'deleted': {'history': True, 'state': True}})
        self.assertEqual(load_history('c1', 's1'), [])
        self.assertEqual(load_state('c1', 's1'), [])

        ## 삭제하지 않은 고객과 세션의 대화·상태가 남아 있는지 확인합니다.
        for customer, session in [('c2', 's1'), ('c1', 's2')]:
            self.assertTrue(load_history(customer, session))
            self.assertTrue(load_state(customer, session))
        # 고객 파일은 남기고 요청한 세션 키만 제거해야 합니다.
        for folder in ['history', 'state']:
            records = [json.loads(path.read_text(encoding='utf-8'))
                       for path in (self.root / folder).glob('*.json')]

            self.assertEqual(len(records), 2)
            self.assertCountEqual([list(record) for record in records], [['s1'], ['s2']])

        ## 같은 세션을 다시 삭제하면 추가로 지운 기록이 없다고 알려야 합니다.
        repeated = self.api.delete('/test/api/session', params={'customer_id': 'c1', 'session_id': 's1'})

        self.assertEqual(repeated.json(), {'deleted': {'history': False, 'state': False}})

    def test_missing_or_blank_identifiers_cannot_delete_records(self):
        """고객·세션 ID를 빼거나 공백으로 보내면, 삭제를 거절하고 기존 기록을 유지하는지 확인합니다."""
        # 1. 실행: 기존 상태를 저장하고, 고객·세션 ID가 부족한 삭제 요청을 준비합니다.
        save_state('c1', 's1', {'steps': []})
        for params in [{}, {'session_id': 's1'}, {'customer_id': 'c1'},
                       {'customer_id': ' ', 'session_id': 's1'}, {'customer_id': 'c1', 'session_id': ''}]:
            with self.subTest(params=params):

                # 2. 확인: 각 요청이 422를 반환하고, 미리 저장한 상태는 남아 있는지 확인합니다.
                self.assertEqual(self.api.delete('/test/api/session', params=params).status_code, 422)

        self.assertTrue(load_state('c1', 's1'))
