"""현재 테스트보드에서 사용하는 경로만 의도 분류 API로 노출하는지 확인합니다."""
import unittest
from fastapi.testclient import TestClient
from main import app


class ActiveRoutesTests(unittest.TestCase):
    def test_old_intent_routes_are_not_registered(self):
        """기존 의도 분류 경로를 요청해 현재 서버에서 노출하지 않는지 확인합니다."""
        # 1. 경로 확인: 새 경로는 유지하고 이전 테스트보드 경로는 등록하지 않습니다.
        paths = app.openapi()['paths']
        self.assertIn('/chatbot/intent/turn', paths)
        for path in ['/intent_classifier', '/test/cases', '/test/prompt', '/test/prompts']:
            self.assertNotIn(path, paths)
