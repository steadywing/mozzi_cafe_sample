"""고객 선택 API를 요청해, 이름·ID만 제공하고 연락처 등 다른 정보는 숨기는지 확인합니다."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class CustomerListTests(TestCase):
    def test_customer_list_excludes_contact_and_other_details(self):
        """연락처가 든 고객 파일을 조회해도, 선택 목록에는 고객 ID와 이름만 나오는지 확인합니다."""
        # 고객 파일에 다른 정보가 있어도 선택에 필요한 값만 돌려줍니다.
        # 1. 준비: 연락처까지 들어 있는 임시 고객 파일을 만들어, 실제 고객 목록 대신 읽게 합니다.
        with TemporaryDirectory() as temporary:
            data = Path(temporary) / 'data'
            data.mkdir()
            (data / 'customers.json').write_text(json.dumps([
                {'customer_id': 'customer-1', 'name': '고객 1', 'phone': 'private'}
            ]), encoding='utf-8')

            with patch('routers.testboard.BASE_DIR', Path(temporary)):

                # 2. 실행: /test/api/customers 경로에 요청해 응답을 받습니다.
                response = TestClient(app).get('/test/api/customers')

        # 3. 확인: 응답이 성공하고, 고객 ID와 이름 두 항목만 포함하는지 비교합니다.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'customers': [{'customer_id': 'customer-1', 'name': '고객 1'}]})
