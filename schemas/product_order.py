"""주문 모델이 상품·수량·옵션을 같은 형식으로 돌려주도록 출력 형식을 정합니다."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DraftItem(BaseModel):
    """모델이 고객 문장에서 읽은 상품 이름·수량·온도·옵션을 담으며, 실제 메뉴 확인 전 값입니다."""

    model_config = ConfigDict(extra='forbid')

    product_name: str | None = Field(description='주문 상품명; 알 수 없으면 null')
    quantity: float | None = Field(description='고객이 말한 수량; 알 수 없으면 null')
    temperature: Literal['HOT', 'ICE'] | None = Field(description='선택한 상품 온도; 미확인 또는 해당 없으면 null')
    options: list[str] | None = Field(description='상품별 옵션; 미확인 null, 옵션 없음 []')


class OrderDraft(BaseModel):
    """모델이 읽은 주문 내용과 추가 확인할 질문을 담아, 고객 확인 전 주문 상태로 옮길 때 사용합니다."""

    model_config = ConfigDict(extra='forbid')

    items: list[DraftItem] = Field(description='주문 상품별 정보')
    order_type: Literal['매장', '포장'] | None = Field(description='매장 이용 또는 포장; 미확인 null')
    payment_method: Literal['카드', '현금', '간편결제'] | None = Field(description='결제 방식; 미확인 null')
    total_price: int | None = Field(description='최종 결제금액; 모델은 null로 두고 코드에서 계산')
    confirmation_status: Literal['pending'] = Field(description='모델이 만드는 초안은 항상 고객 확인 전 pending')
    needs_clarification: bool = Field(description='필수 정보가 빠졌거나 모호하여 추가 확인이 필요한지 여부')
    question: str | None = Field(description='고객에게 확인할 질문; 필요 없으면 null')
