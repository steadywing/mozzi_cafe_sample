# 영수증 내용 읽기

이미지에 보이는 영수증 내용을 읽어 JSON 객체 하나로 반환합니다. 보이지 않거나 확실하지 않은 값은 추측하지 말고 null로 둡니다.

- `store_name`: 매장 이름 문자열 또는 null
- `receipt_number`: 거래번호 문자열 또는 null
- `purchased_at`: 영수증에 적힌 일시 문자열 또는 null
- `items`: 메뉴별 객체 배열. 각 객체는 `name`(메뉴명 문자열 또는 null), `quantity`(수량 정수 또는 null), `unit_price`(단가 정수 또는 null), `amount`(금액 정수 또는 null)를 담습니다.
- `total`: 합계 정수 또는 null
- `payment_amount`: 결제금액 정수 또는 null
- `other_text`: 위 항목에 담지 않은 보이는 글자 문자열 배열

JSON 이외의 설명이나 코드 블록은 출력하지 않습니다.
