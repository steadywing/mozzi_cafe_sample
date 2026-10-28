"""추천 노트북 API의 조건 누적과 알레르기 제외를 확인합니다."""
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.recommendation import router

app = FastAPI()
app.include_router(router)


class RecommendationApiTests(unittest.TestCase):
    def test_missing_allergies_asks_before_recommendation(self):
        """알레르기 미확인 입력을 받아 추천보다 확인 질문이 먼저 나오는지 확인합니다."""
        # 1. 모델 대체: 선호만 확인하고 알레르기는 미확인으로 둡니다.
        with patch('services.notebook_recommendation.ask_model', return_value='{"allergies":null,"preferences":["상큼"],"needs_clarification":false}'):
            result = TestClient(app).post('/chatbot/recommendation', json={'input': {'text': '상큼한 음료'}})
        # 2. 결과 확인: 후보 없이 필요한 질문이 나타나는지 확인합니다.
        self.assertEqual(result.status_code, 200)
        self.assertIn('알레르기', result.json()['state']['answer']['text'])
        self.assertIsNone(result.json()['state']['recommendation']['candidate_menu_ids'])
        self.assertEqual(result.json()['steps'][1]['input']['conditions']['preferences'], ['상큼'])
        self.assertGreater(result.json()['steps'][1]['input']['menu_count'], 0)

    def test_allergen_filtered_and_unconfirmed_ingredients_excluded(self):
        """우유 알레르기가 있는 조건으로 재료 미확인과 우유 메뉴를 제외하는지 확인합니다."""
        # 1. 조건 준비: 우유가 포함된 상품과 미확인 상품을 준비합니다.
        from services.notebook_recommendation import filter_recommendation_menu
        from schemas.session_state import SessionState, RecommendationState
        state = SessionState(recommendation=RecommendationState(allergies=['우유'], preferences=[]))
        menu = [{'menu_id':'a','available':True,'category':'음료','ingredients':['우유'],'allergens':['우유']}, {'menu_id':'b','available':True,'category':'음료','ingredients':None,'allergens':[]}, {'menu_id':'c','available':True,'category':'음료','ingredients':['차'],'allergens':[]}]
        # 2. 필터 확인: 안전 정보가 확인된 후보만 남깁니다.
        result = filter_recommendation_menu(state, menu)
        self.assertEqual(result.recommendation.candidate_menu_ids, ['c'])
