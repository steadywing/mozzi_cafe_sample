"""카페 정보 문의 API의 문서 선택과 근거 기반 답변 흐름을 확인합니다."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers.consultation import router


class ConsultationTests(unittest.TestCase):
    """대체 모델과 임시 문서 목록으로 정보 문의 처리를 확인합니다."""

    def test_selected_document_and_answer_are_recorded(self):
        """관련 문서가 선택되면 실제 원문과 답변을 단계별로 돌려주는지 확인합니다."""
        # 1. 준비: 문서 선택과 답변 모델이 정해진 결과를 돌려주도록 만듭니다.
        app = FastAPI()
        app.include_router(router)
        choice = SimpleNamespace(choice='relevant')
        calls = []
        def choose_documents(**kwargs):
            """문서 선택에 전달된 입력을 보관하고 관련 문서 선택을 돌려줍니다."""
            # 1. 호출 기록: 실제 전달한 질문을 나중에 화면 기록과 비교합니다.
            calls.append(kwargs)

            return SimpleNamespace(answers={'document_0': choice})
        jev = SimpleNamespace(system_one=choose_documents)
        answer = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(output_text='주말에는 운영합니다.', model='test-model')))
        with patch('services.notebook_consultation.document_catalog', return_value={'02_영업시간과_위치.md': '영업시간'}), patch('services.notebook_consultation.get_jev_client', return_value=jev), patch('services.notebook_consultation.get_openai_client', return_value=answer):
            # 2. 실행: 고객 질문을 API로 전달합니다.
            response = TestClient(app).post('/chatbot/consultation', json={'input': {'text': '주말 영업시간은?'}})

        # 3. 확인: 선택된 실제 원문과 생성 답변이 각각 결과에 남습니다.
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual([step['step'] for step in result['steps']], ['generate_document_selection', 'load_cafe_documents', 'generate_consultation_response'])
        self.assertEqual(result['state']['answer']['text'], '주말에는 운영합니다.')
        self.assertIn('02_영업시간과_위치.md', result['state']['consultation']['documents'])
        self.assertEqual(result['steps'][1]['input']['selected_documents'], ['02_영업시간과_위치.md'])
        self.assertEqual(result['steps'][0]['questions'], {key: question.model_dump(mode='json') for key, question in calls[0]['questions'].items()})
        self.assertEqual(result['steps'][0]['questions']['document_0']['criteria'], {'relevant': '질문에 답하는 데 필요한 문서입니다.', 'irrelevant': '질문과 관련 없는 문서입니다.'})

    def test_no_documents_does_not_call_models(self):
        """선택 가능한 문서가 없으면 모델 호출 없이 확인 불가를 안내하는지 확인합니다."""
        # 1. 준비와 실행: 빈 문서 목록에서 API를 호출합니다.
        app = FastAPI()
        app.include_router(router)
        with patch('services.notebook_consultation.document_catalog', return_value={}), patch('services.notebook_consultation.get_jev_client') as jev, patch('services.notebook_consultation.get_openai_client') as answer:
            response = TestClient(app).post('/chatbot/consultation', json={'input': {'text': '영업시간은?'}})

        # 2. 확인: 두 모델 모두 부르지 않고 자료가 없다고 답합니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state']['answer']['model'], '자료 없음')
        jev.assert_not_called()
        answer.assert_not_called()

    def test_missing_input_is_rejected(self):
        """고객 입력이 없으면 외부 모델을 부르지 않고 요청을 거절합니다."""
        # 1. 요청 확인: 입력 없이 전달한 요청은 422 응답을 받습니다.
        app = FastAPI()
        app.include_router(router)
        self.assertEqual(TestClient(app).post('/chatbot/consultation', json={}).status_code, 422)
