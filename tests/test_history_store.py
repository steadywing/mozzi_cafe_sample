"""대화를 고객 파일의 세션별로 저장·조회하고, 쓰기 실패에도 기존 대화를 보존하는지 확인합니다."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from common import history_store


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        """대화 저장 위치를 임시 폴더로 바꾸고, 테스트가 끝나면 폴더와 설정을 정리하도록 등록합니다."""
        # 1. 준비: 대화 저장 위치를 임시 폴더로 바꾸고, 테스트가 끝나면 폴더와 설정을 정리하도록 등록합니다.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        patcher = patch('common.history_store.HISTORY_DIR', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_saves_messages_under_session_id_key(self):
        """같은 고객의 두 세션 대화를 저장해, 한 고객 파일 안에서 세션별로 읽을 수 있는지 확인합니다."""
        # 같은 고객의 세션은 한 파일 안에서 각각의 키로 구분합니다.
        # 1. 준비: 한 고객의 서로 다른 세션에 저장할 두 대화 목록을 만듭니다.
        first = [{'role': 'user', 'content': '안녕하세요'}]
        second = [{'role': 'user', 'content': '다른 대화'}]

        # 2. 실행: 같은 고객의 두 세션에 각각의 대화를 저장하고, 생성된 고객 파일을 찾습니다.
        history_store.save_history('customer-1', 'session-1', first)
        history_store.save_history('customer-1', 'session-2', second)

        paths = list(self.path.glob('*.json'))

        # 3. 확인: 고객 파일은 하나이며, 두 세션의 대화가 각각 저장·조회되는지 확인합니다.
        self.assertEqual(len(paths), 1)
        self.assertEqual(json.loads(paths[0].read_text(encoding='utf-8')), {
            'session-1': first, 'session-2': second,
        })
        self.assertEqual(history_store.load_history('customer-1', 'session-1'), first)
        self.assertEqual(history_store.load_history('customer-1', 'session-2'), second)
        self.assertEqual(history_store.load_history('customer-1', 'missing'), [])

    def test_customer_records_are_separate_and_session_key_is_not_a_path(self):
        """두 고객에게 같은 세션 ID를 넣어도, 고객 파일이 분리되고 세션 ID는 경로가 되지 않는지 확인합니다."""
        # 같은 세션 ID라도 고객이 다르면 다른 파일에 기록합니다.
        # 1. 준비: 두 고객의 대화와 경로처럼 생긴 세션 ID를 준비합니다.
        first = [{'role': 'user', 'content': '첫 고객'}]
        second = [{'role': 'user', 'content': '다른 고객'}]

        # 2. 실행: 서로 다른 고객에게 같은 세션 ID로 대화를 저장합니다.
        history_store.save_history('customer-1', '../session', first)
        history_store.save_history('customer-2', '../session', second)

        # 3. 확인: 고객 파일은 두 개이고, 같은 세션 키로 조회해도 각 고객의 대화만 나오는지 확인합니다.
        self.assertEqual(len(list(self.path.glob('*.json'))), 2)
        self.assertEqual(history_store.load_history('customer-1', '../session'), first)
        self.assertEqual(history_store.load_history('customer-2', '../session'), second)

    def test_write_failure_preserves_previous_history(self):
        """대화 파일 교체 중 오류를 발생시켜, 기존 고객의 모든 세션 대화가 그대로 남는지 확인합니다."""
        # 쓰기 실패 시 다른 세션을 포함한 고객 파일을 그대로 유지합니다.
        # 1. 준비: 두 세션의 기존 대화를 저장한 뒤, 새 파일로 교체하는 단계만 실패시킵니다.
        messages = [{'role': 'user', 'content': '이전 메시지'}]

        # 2. 실행: 기존 대화를 저장한 뒤 파일 교체 오류를 발생시켜, 새 대화를 저장하지 못하게 합니다.
        history_store.save_history('customer-1', 'session-1', messages)
        history_store.save_history('customer-1', 'session-2', messages)
        with patch('common.history_store.os.replace', side_effect=OSError('write failed')):
            with self.assertRaises(OSError):
                history_store.save_history('customer-1', 'session-1', messages + [{'role': 'assistant', 'content': '새 답변'}])

        # 3. 확인: 실패 전 두 세션의 대화가 남고, 쓰다 만 임시 파일은 지워졌는지 확인합니다.
        self.assertEqual(history_store.load_history('customer-1', 'session-1'), messages)
        self.assertEqual(history_store.load_history('customer-1', 'session-2'), messages)
        self.assertEqual(len(list(self.path.iterdir())), 1)
