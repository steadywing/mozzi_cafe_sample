"""턴별 상태를 고객·세션별로 쌓아 읽고, 쓰기 실패에도 이전 기록을 보존하는지 확인합니다."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from common import state_store


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        """상태 저장 위치를 임시 폴더로 바꾸고, 테스트가 끝나면 폴더와 설정을 정리하도록 등록합니다."""
        # 1. 준비: 상태 저장 위치를 임시 폴더로 바꾸고, 테스트가 끝나면 폴더와 설정을 정리하도록 등록합니다.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        patcher = patch('common.state_store.STATE_DIR', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_and_load_turns_under_session_id_key(self):
        """같은 세션에 두 턴을 저장해, 고객 파일의 세션 키 아래 입력 순서대로 쌓이는지 확인합니다."""
        # 1. 준비: 한 세션에 순서대로 추가할 첫 요청과 다음 요청의 상태를 준비합니다.
        first = {'steps': [{'step': 'input', 'state': {'input': {'text': '첫 요청'}}}]}
        second = {'steps': [{'step': 'input', 'state': {'input': {'text': '다음 요청'}}}]}

        # 2. 실행: 한 세션에 두 턴을 추가하고, 다른 세션에도 첫 턴을 저장합니다.
        state_store.save_state('c1', 's1', first)
        state_store.save_state('c1', 's1', second)
        state_store.save_state('c1', 's2', first)

        # 3. 확인: 같은 세션의 두 턴은 입력 순서로, 다른 세션의 턴은 별도 목록으로 읽히는지 확인합니다.
        self.assertEqual(state_store.load_state('c1', 's1'), [first, second])
        self.assertEqual(state_store.load_state('c1', 's2'), [first])

        paths = list(self.path.glob('*.json'))

        self.assertEqual(len(paths), 1)
        self.assertEqual(json.loads(paths[0].read_text(encoding='utf-8')), {
            's1': [first, second], 's2': [first],
        })

    def test_customer_and_session_are_separate_and_paths_are_safe(self):
        """경로처럼 생긴 세션 ID로 저장해도, 고객·세션 기록이 분리되고 파일 경로로 쓰이지 않는지 확인합니다."""
        # 1. 확인: 경로처럼 생긴 세션 ID를 사용해도 고객별 기록과 다른 세션이 섞이지 않는지 확인합니다.
        self.assertEqual(state_store.load_state('c1', 's1'), [])

        state_store.save_state('c1', '../same', {'steps': [{'state': {'value': 1}}]})
        state_store.save_state('c2', '../same', {'steps': [{'state': {'value': 2}}]})
        state_store.save_state('c1', 'other', {'steps': []})

        self.assertEqual(state_store.load_state('c1', '../same'), [{'steps': [{'state': {'value': 1}}]}])
        self.assertEqual(state_store.load_state('c2', '../same'), [{'steps': [{'state': {'value': 2}}]}])
        self.assertEqual(state_store.load_state('c1', 'other'), [{'steps': []}])
        self.assertEqual(len(list(self.path.glob('*.json'))), 2)

    def test_write_failure_keeps_existing_state(self):
        """상태 파일 교체 중 오류를 발생시켜, 기존 세션 기록과 다른 세션 기록이 남는지 확인합니다."""
        # 1. 실행: 두 세션의 상태를 저장한 뒤 파일 교체 오류를 발생시켜, 새 상태 저장을 실패시킵니다.
        state_store.save_state('c1', 's1', {'steps': [{'state': {'value': 1}}]})
        state_store.save_state('c1', 's2', {'steps': []})
        with patch('common.state_store.os.replace', side_effect=OSError('write failed')):
            with self.assertRaises(OSError):
                state_store.save_state('c1', 's1', {'steps': [{'state': {'value': 2}}]})

        # 2. 확인: 두 세션의 이전 상태가 그대로이고, 쓰다 만 임시 파일은 남지 않았는지 확인합니다.
        self.assertEqual(state_store.load_state('c1', 's1'), [{'steps': [{'state': {'value': 1}}]}])
        self.assertEqual(state_store.load_state('c1', 's2'), [{'steps': []}])
        self.assertEqual(len(list(self.path.iterdir())), 1)
