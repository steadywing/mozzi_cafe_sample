"""주문 테스트보드의 화면·프롬프트·예제를 조회해, 실습에 필요한 자료만 제공하는지 확인합니다."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from main import app
from schemas.product_order import OrderDraft


class OrderTestboardTests(unittest.TestCase):
    def setUp(self):
        """화면·자료 조회 요청을 보낼 API 테스트 클라이언트를 준비합니다."""
        # 1. 준비: 테스트 자료 조회 API만 호출할 클라이언트를 만듭니다.
        self.api = TestClient(app)

    def test_order_page_uses_order_template(self):
        """주문 테스트 화면을 요청해, 주문 전용 입력·실행 요소가 표시되는지 확인합니다."""
        # 1. 준비: 화면 파일 작성과 별개로 라우터의 템플릿 연결을 확인합니다.
        with patch('routers.test_pages.templates.TemplateResponse', return_value=HTMLResponse('상품 주문')) as render:
            response = self.api.get('/test/order')

        # 2. 확인: 주문 전용 HTML 화면으로 요청을 전달합니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(render.call_args.kwargs['name'], 'order.html')

    def test_order_prompts_return_cached_persona_and_order_text(self):
        """주문 프롬프트 API를 조회해, 공통 말투와 주문 지침을 저장소에서 가져오는지 확인합니다."""
        # 1. 준비: 공통 저장소가 반환할 지침을 대체합니다.
        prompts = {'prompts/persona.md': '공통 말투', 'prompts/order_extraction.md': '주문 추출 지침'}
        with patch('routers.testboard.get_prompt', side_effect=prompts.__getitem__):
            response = self.api.get('/test/api/order/prompts')

        # 2. 확인: 의도 분류 지침과 섞이지 않은 주문용 지침을 돌려줍니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'persona': {'prompt_file': 'prompts/persona.md', 'content': '공통 말투'},
            'order': {'prompt_file': 'prompts/order_extraction.md', 'content': '주문 추출 지침'},
        })

    def test_order_cases_return_messages_without_preloaded_order(self):
        """주문 예제 목록을 조회해, 미리 채운 주문 상태 없이 고객 메시지만 제공하는지 확인합니다."""
        # 1. 실행: 실제 예제 파일과 API의 반환값을 비교합니다.
        cases = json.loads((Path(__file__).parent / 'fixtures/order_cases.json').read_text(encoding='utf-8'))
        response = self.api.get('/test/api/order/cases')

        # 2. 확인: 모든 사례는 새 입력 문장이며 확정 주문을 미리 주입하지 않습니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'cases': cases})
        self.assertIn('yes', [case['input']['text'] for case in cases])
        self.assertIn('no', [case['input']['text'] for case in cases])
        for case in cases:
            self.assertEqual(case['input']['session_state'], {})
            self.assertFalse(case['input']['has_image'])

    def test_order_case_read_failure_returns_public_error(self):
        """주문 예제 파일을 읽을 때 오류를 발생시켜, 내부 정보 없이 공개 안내만 반환하는지 확인합니다."""
        # 1. 준비: 자료가 없는 임시 위치로 테스트보드 기준 경로를 바꿉니다.
        with TemporaryDirectory() as temporary, patch('routers.testboard.BASE_DIR', Path(temporary)):
            response = self.api.get('/test/api/order/cases')

        # 2. 확인: 로컬 경로 정보 대신 자료를 읽지 못했다는 메시지를 돌려줍니다.
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {'detail': '주문 테스트 사례를 읽을 수 없습니다.'})

    def test_order_trace_saves_actual_model_input_prompt_and_menu_data(self):
        """실제 주문 함수를 대체 모델로 실행해 모델 입력·프롬프트와 메뉴 조회 정보를 저장하는지 확인합니다."""
        # 1. 자료 준비: 임시 메뉴·옵션과 모델이 반환할 주문 초안을 만듭니다.
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            menu_file = root / 'menu.json'
            options_file = root / 'order_options.json'
            menu_file.write_text(json.dumps([{'menu_id': 'americano', 'name': '아메리카노', 'aliases': ['아아'], 'price': 4500, 'temperatures': ['HOT', 'ICE'], 'available': True}]), encoding='utf-8')
            options_file.write_text(json.dumps({'샷 추가': {'price': 500, 'menu_ids': ['americano']}}), encoding='utf-8')
            draft = OrderDraft(items=[{'product_name': '아아', 'quantity': 1, 'temperature': 'ICE', 'options': []}], order_type='포장', payment_method='카드', total_price=None, confirmation_status='pending', needs_clarification=False, question=None)
            client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: SimpleNamespace(output_parsed=draft, model='test-model')))
            saved = []

            def capture_state(customer_id, session_id, turn):
                """고객과 세션의 주문 기록을 받아 테스트용 목록에 보관합니다."""
                # 1. 기록 보관: 서비스가 넘긴 턴을 검사할 수 있도록 남깁니다.
                saved.append(turn)

            # 2. 주문 실행: 실제 단계 함수와 프롬프트 조합을 실행하고 모델 응답만 대체합니다.
            with patch.multiple('services.product_order', MENU_FILE=menu_file, OPTIONS_FILE=options_file), \
                 patch('services.product_order.get_openai_client', return_value=client), \
                 patch('services.product_order.load_history', return_value=[]), \
                 patch('services.product_order.save_state', side_effect=capture_state):
                response = self.api.post('/chatbot/order', json={'customer_id': 'customer-1', 'session_id': 'trace-order', 'input': {'text': '아아 한 잔 포장할게요'}})

            # 3. 저장 확인: 모델 단계와 Python 단계의 실제 입력과 사용 자료가 상태와 함께 남습니다.
            self.assertEqual(response.status_code, 200, response.text)
            steps = {item['step']: item for item in saved[0]['steps']}
            model_step = steps['create_order_draft']
            self.assertEqual(model_step['input'][0]['content'], model_step['prompt'])
            self.assertEqual(json.loads(model_step['input'][-1]['content'])['input']['text'], '아아 한 잔 포장할게요')
            self.assertEqual(model_step['model'], 'test-model')
            self.assertEqual(model_step['data']['menu_count'], 1)
            self.assertEqual(model_step['data']['option_count'], 1)
            menu_step = steps['match_menu_and_fill_prices']
            self.assertEqual(menu_step['input']['order']['items'][0]['product_name'], '아아')
            self.assertEqual(menu_step['input']['menu_count'], 1)
            self.assertEqual(menu_step['input']['menu_file'], 'menu.json')
            self.assertEqual(steps['check_order']['input']['order']['items'][0]['product_id'], 'americano')
