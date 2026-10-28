"""화면, 챗봇 처리, 테스트 자료의 경로가 역할별로 모였는지 확인합니다."""
import unittest

from fastapi.testclient import TestClient

from main import app


class RouteMapTests(unittest.TestCase):
    """현재 화면과 API가 새 경로로만 열리는지 확인합니다."""

    def test_explicit_test_pages_replace_mixed_paths(self):
        """기능별 화면을 고정된 주소로 열고 이전 포괄 경로가 사라졌는지 확인합니다."""
        # 1. 화면 확인: 모든 테스트 화면이 이름이 드러나는 주소에서 HTML을 돌려줍니다.
        client = TestClient(app)
        paths = app.openapi()['paths']
        pages = (
            '/test/intent', '/test/unknown', '/test/order', '/test/order/practice',
            '/test/recommendation', '/test/search', '/test/consultation', '/test/points',
        )
        for path in pages:
            with self.subTest(path=path):
                self.assertIn(path, paths)
                self.assertIn('get', paths[path])
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('text/html', response.headers['content-type'])

        # 2. 이전 경로 확인: 화면 GET을 중복 등록하거나 임의 기능 이름을 받지 않습니다.
        for path in ('/test', '/test/notebook/unknown', '/test/notebook/order',
                     '/test/notebook/{feature}', '/test/{feature}'):
            self.assertNotIn(path, paths)

    def test_processing_and_test_data_use_separate_prefixes(self):
        """챗봇 처리와 테스트 자료의 새 주소를 확인하고 이전 주소를 제외합니다."""
        # 1. 처리 확인: 기능별 실행은 /chatbot 아래에서만 받습니다.
        paths = app.openapi()['paths']
        expected = {
            '/chatbot/intent/turn': 'post',
            '/chatbot/intent/turn/{session_id}': 'delete',
            '/chatbot/order': 'post',
            '/chatbot/order/practice': 'post',
            '/chatbot/history': 'post',
            '/chatbot/unknown': 'post',
            '/chatbot/recommendation': 'post',
            '/chatbot/search': 'post',
            '/chatbot/consultation': 'post',
            '/chatbot/points/start': 'post',
            '/chatbot/points/confirm': 'post',
            '/chatbot/points/{session_id}': 'delete',
            '/test/api/order/cases': 'get',
            '/test/api/order/prompts': 'get',
            '/test/api/intent-turn/cases': 'get',
            '/test/api/search/cases': 'get',
            '/test/api/search/images/{sample}': 'get',
            '/test/api/points/cases': 'get',
            '/test/api/points/samples/{sample}': 'get',
            '/test/api/traces/{feature}/{session_id}': 'get',
            '/test/api/sessions': 'delete',
        }
        for path, method in expected.items():
            with self.subTest(path=path, method=method):
                self.assertIn(path, paths)
                self.assertIn(method, paths[path])

        # 2. 접두어 확인: 화면과 서버 상태 확인 외 JSON 경로는 두 범주로만 나눕니다.
        page_paths = {'/', '/health', '/test/intent', '/test/unknown', '/test/order',
                      '/test/order/practice', '/test/recommendation', '/test/search',
                      '/test/consultation', '/test/points'}
        for path in paths:
            if path in page_paths:
                continue
            with self.subTest(path=path):
                self.assertTrue(path.startswith('/chatbot/') or path.startswith('/test/api/'))
                self.assertNotIn('/notebook', path)

        # 3. 이전 주소 확인: 예전 처리·자료 경로는 별칭으로 남기지 않습니다.
        for path in ('/intent_classifier/turn', '/product_order', '/history',
                     '/test/order/cases', '/notebook/order', '/notebook/search',
                     '/notebook/traces/{feature}/{session_id}'):
            self.assertNotIn(path, paths)

    def test_feature_routers_only_register_chatbot_processing(self):
        """검색과 포인트 라우터에서 샘플 조회를 분리해 처리 경로만 남기는지 확인합니다."""
        # 1. 라우터 확인: 기능 라우터가 테스트 자료 GET까지 등록하지 않는지 확인합니다.
        from routers.points import router as points_router
        from routers.search import router as search_router

        for router in (points_router, search_router):
            with self.subTest(router=router.tags[0]):
                self.assertTrue(all(route.path.startswith('/chatbot/') for route in router.routes))
