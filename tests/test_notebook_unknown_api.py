"""unknown 노트북의 독립 API를 대체 모델로 확인합니다."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.unknown import router


class UnknownNotebookApiTests(unittest.TestCase):
    """확인 질문 API가 노트북의 입력과 출력을 유지하는지 확인합니다."""

    def test_unknown_response_contains_actual_input_and_answer(self):
        """고객 입력을 보내 대체 모델의 답변과 처리 단계가 반환되는지 확인합니다."""
        # 1. 준비: 모델 응답과 독립 라우터를 시험용으로 준비합니다.
        app = FastAPI()
        app.include_router(router)
        response = SimpleNamespace(output_text='무엇을 먼저 도와드릴까요?', model='fake-model')
        client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response))

        # 2. 실행: 현재 입력을 모델에 보내 확인 질문을 만듭니다.
        with patch('services.notebook_unknown.get_openai_client', return_value=client):
            result = TestClient(app).post('/chatbot/unknown', json={'input': {'text': '추천과 주차를 알려주세요'}})

        # 3. 확인: 고객 답변과 실행 단계가 함께 반환됩니다.
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['state']['answer']['answer'], '무엇을 먼저 도와드릴까요?')
        self.assertEqual(result.json()['steps'][0]['step'], 'generate_unknown_response')


if __name__ == '__main__':
    unittest.main()
