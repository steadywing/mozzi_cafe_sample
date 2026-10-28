"""이미지 검색 API의 샘플 제한과 단계별 결과를 확인합니다."""
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.search import router
from routers.test_samples import router as test_samples_router

app = FastAPI()
app.include_router(router)
app.include_router(test_samples_router)


class SearchApiTests(unittest.TestCase):
    def test_search_cases_and_sample_images(self):
        """준비한 사진 사례를 조회하고, 허용된 사진만 이미지로 받는지 확인합니다."""
        # 1. 사례 확인: 실제 사진 이름과 기대하는 확인 내용이 함께 제공됩니다.
        client = TestClient(app)
        cases = client.get('/test/api/search/cases').json()['cases']
        self.assertEqual(len(cases), 8)
        case = next(item for item in cases if item['sample'] == 'search_cafe_latte.png')
        self.assertIn('drink_cafe_latte', case['expected'])

        # 2. 사진 확인: 목록의 PNG는 열리고 목록 밖의 파일은 거부합니다.
        response = client.get('/test/api/search/images/search_cafe_latte.png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(client.get('/test/api/search/images/drinks-prompts.md').status_code, 404)
        self.assertEqual(client.get('/test/api/search/images/%2e%2e%2fmenu.json').status_code, 404)

    def test_rejects_arbitrary_path(self):
        """허용 샘플이 아닌 경로를 보내면 모델 호출 전에 거부하는지 확인합니다."""
        # 1. 경로 확인: 상위 폴더를 가리키는 파일 이름을 거부합니다.
        response = TestClient(app).post('/chatbot/search', json={'text':'찾아줘', 'sample':'../../secret.png'})
        self.assertEqual(response.status_code, 422)

    def test_search_steps_use_actual_candidates(self):
        """대체 임베딩과 검색 결과를 받아 각 처리 단계를 반환하는지 확인합니다."""
        # 1. 모델 대체: 사진 검색과 답변을 재현 가능한 결과로 바꿉니다.
        with patch('services.notebook_search.create_image_embedding', return_value=[0.1]), patch('services.notebook_search.search_similar_menu', return_value=[{'menu_id':'drink_cafe_latte','score':0.8,'menu':{'name':'카페라떼'}}]), patch('services.notebook_search.ask_model', return_value='카페라떼를 확인해 주세요.'):
            response = TestClient(app).post('/chatbot/search', json={'text':'찾아줘', 'sample':'search_cafe_latte.png'})
        # 2. 단계 확인: 검색 결과와 답변이 응답에 들어갑니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual([step['step'] for step in response.json()['steps']], ['create_image_embedding', 'search_similar_menu', 'generate_search_response'])
        self.assertEqual(response.json()['state']['search']['candidate_menu_ids'], ['drink_cafe_latte'])
        self.assertEqual(response.json()['steps'][0]['input']['image_sample'], 'search_cafe_latte.png')
        self.assertEqual(response.json()['steps'][1]['input']['vector_dimensions'], 1)
        self.assertEqual(response.json()['steps'][1]['candidate_count'], 1)
