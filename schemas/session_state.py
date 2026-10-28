"""고객 입력부터 작업 결과까지, 한 대화에서 주고받고 저장할 데이터의 형식을 정합니다."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, field_validator


class PurchaseStatistics(BaseModel):
    """저장된 주문에서 계산한 주문 수·결제액·구매 수량을 담으며, 취소·환불 여부는 구분하지 않습니다."""

    order_count: int = Field(default=0, description='고객의 고유 주문 ID 개수')
    total_spent: int = Field(default=0, description='저장 주문의 최종 결제금액 합계(원); 옵션·할인을 다시 계산하지 않음')
    menu_quantities: dict[str, int] = Field(default_factory=dict, description='메뉴 ID별 구매 수량 합계')
    category_quantities: dict[str, int] = Field(default_factory=dict, description='현재 메뉴 자료에서 확인된 카테고리별 구매 수량 합계')
    temperature_quantities: dict[str, int] = Field(default_factory=dict, description='HOT·ICE별 구매 수량 합계; 온도가 없는 상품은 제외')


class CustomerProfile(BaseModel):
    """서버 고객 자료에서 가져온 이름·알레르기·구매 통계 등, 고객 응대에 쓸 정보를 담습니다."""

    customer_id: str = Field(description='고객 자료에서 조회한 고객 ID')
    name: str | None = Field(default=None, description='고객 이름; 미등록이면 null')
    birth_year: int | None = Field(default=None, description='고객 출생연도; 미등록이면 null')
    membership_level: str | None = Field(default=None, description='고객 회원등급; 미등록이면 null')
    allergies: list[str] | None = Field(default=None, description='저장된 알레르기 재료: 미확인 null, 없음 []')
    points: StrictInt | None = Field(default=None, ge=0, description='고객 자료에 명시된 현재 보유 적립금(원); 미확인 null')
    stamps: StrictInt | None = Field(default=None, ge=0, description='고객 자료에 명시된 현재 보유 스탬프 개수; 누적 발생량이 아니며 미확인 null')
    preferences: PurchaseStatistics | None = Field(default=None, description='저장 주문 기준 구매 통계; 조회 전 null, 구매가 없으면 빈 통계')


class CustomerInput(BaseModel):
    """이번 요청에서 받은 고객 문장과 이미지가 첨부됐는지를 함께 담습니다."""

    text: str = Field(min_length=1, max_length=4000, description='고객이 입력한 요청')
    has_image: bool = Field(default=False, strict=True, description='이미지 첨부 여부')

    @field_validator('text')
    @classmethod
    def check_text(cls, value):
        """고객 문장의 앞뒤 공백을 뺀 값을 돌려주고, 내용 없이 공백만 입력했으면 오류로 알립니다."""
        # 1. 문장 확인: 앞뒤 공백을 빼고, 내용이 남지 않으면 분류할 수 없으므로 오류로 알립니다.
        if not value.strip():
            raise ValueError('고객 요청을 입력해주세요.')

        return value.strip()


class CustomerRequest(BaseModel):
    """고객이 보낸 세션 ID와 고객 정보, 이번 입력을 담습니다."""

    session_id: str = Field(description='대화를 이어갈 세션 ID')
    customer_info: CustomerProfile | None = Field(default=None, description='이번 세션의 고객 정보; 없으면 기존 정보를 유지')
    input: CustomerInput = Field(description='이번 턴의 고객 입력')


class SearchState(BaseModel):
    """검색 후 고객에게 보여 준 메뉴 ID를 표시한 순서대로 보관합니다."""

    model_config = ConfigDict(extra='allow')

    # None은 검색 전이고 빈 목록은 검색했지만 후보가 없는 경우입니다.
    candidate_menu_ids: list[str] | None = Field(default=None, description='고객에게 보여준 메뉴 ID 순서')


class RecommendationState(BaseModel):
    """고객에게 확인한 알레르기·선호 조건과 추천해 보여 준 메뉴 ID를 보관합니다."""

    model_config = ConfigDict(extra='allow')

    # None은 확인 전이고, 빈 목록은 고객이 없다고 확인한 경우입니다.
    allergies: list[str] | None = Field(default=None, description='알레르기 재료: 미확인 null, 없음 []')
    preferences: list[str] | None = Field(default=None, description='선호 조건: 미확인 null, 없음 []')
    # 고객이 "첫 번째 메뉴"라고 말할 수 있으므로 표시한 순서를 유지합니다. None이면 아직 후보를 보여 주지 않았습니다.
    candidate_menu_ids: list[str] | None = Field(default=None, description='고객에게 보여준 메뉴 ID 순서')


class CouponState(BaseModel):
    """쿠폰 사진에서 읽은 값과 고객 확인·처리 상태를 보관하며, 실제 적립 자료는 별도로 관리합니다."""

    model_config = ConfigDict(extra='allow')

    coupon_id: str | None = Field(default=None, description='인식하거나 정정한 쿠폰 ID')
    # 사진을 읽은 모델이 stamp_count로 돌려준 개수를, 대화 상태에서는 stamps에 담습니다.
    stamps: StrictInt | None = Field(default=None, description='인식하거나 정정한 스탬프 수')
    verification: Literal['passed', 'failed'] | None = Field(default=None, description='쿠폰 검증 결과')
    customer_confirmed: StrictBool | None = Field(default=None, description='고객이 인식 내용을 확인했는지 여부')
    participation_status: Literal['pending', 'completed', 'failed'] | None = Field(
        default=None, description='가상 스탬프 쿠폰 처리 상태'
    )


class ReceiptState(BaseModel):
    """영수증에서 읽은 거래 정보와 확인·포인트 적립 상태를 보관합니다."""

    image_path: str | None = Field(default=None, description='실습에 사용할 영수증 이미지 경로')
    store_name: str | None = Field(default=None, description='영수증에서 읽은 매장 이름')
    receipt_number: str | None = Field(default=None, description='영수증에서 읽은 주문번호 또는 거래번호')
    purchased_at: str | None = Field(default=None, description='영수증에서 읽은 결제 일시')
    payment_amount: StrictInt | None = Field(default=None, ge=0, description='영수증에서 읽은 결제금액(원)')
    verification: Literal['passed', 'failed'] | None = Field(default=None, description='영수증 검증 결과; 검증 전이면 null')
    reason: str | None = Field(default=None, description='검증 실패 또는 처리 보류 이유')
    customer_confirmed: StrictBool | None = Field(default=None, description='고객이 영수증 정보를 확인했는지 여부')
    points_to_add: StrictInt | None = Field(default=None, ge=0, description='확정된 적립 포인트; 기준 미정 또는 미확인이면 null')
    status: Literal['pending', 'completed', 'failed'] | None = Field(default=None, description='포인트 처리 대기·완료·실패 상태')


class OrderItem(BaseModel):
    """주문 상품 한 개의 이름·수량·옵션과, 메뉴에서 확인한 ID·가격을 보관합니다."""

    model_config = ConfigDict(extra='allow')

    product_id: str | None = Field(default=None, description='메뉴 데이터에서 확인한 상품 ID')
    product_name: str | None = Field(default=None, description='주문 상품명')
    # 아직 검증 전인 초안이므로 0이나 소수도 보존하고 처리 함수에서 확인합니다.
    quantity: StrictInt | StrictFloat | None = Field(default=None, description='고객이 말한 수량')
    temperature: Literal['HOT', 'ICE'] | None = Field(default=None, description='선택한 상품 온도; 미확인 또는 해당 없으면 null')
    options: list[str] | None = Field(default=None, description='고객이 요청한 옵션; 미확인 null, 옵션 없음 []')
    price: StrictInt | None = Field(default=None, ge=0, description='메뉴 데이터에서 확인한 상품 기본 가격(원)')


class OrderState(BaseModel):
    """주문 상품 목록과 이용·결제 방식, 고객 확인 여부 및 접수 결과를 함께 보관합니다."""

    model_config = ConfigDict(extra='allow')

    items: list[OrderItem] = Field(default_factory=list, description='주문 상품 목록')
    order_type: Literal['매장', '포장'] | None = Field(default=None, description='매장 이용 또는 포장; 미확인 null')
    payment_method: Literal['카드', '현금', '간편결제'] | None = Field(default=None, description='고객이 선택한 결제 방식; 미확인 null')
    total_price: StrictInt | None = Field(default=None, ge=0, description='주문 API가 반환한 최종 결제금액(원); 미확인 null')
    order_id: str | None = Field(default=None, description='주문 API가 반환한 접수 주문번호; 미접수 null')
    confirmation_status: Literal['pending', 'awaiting_revision', 'confirmed'] | None = Field(
        default=None, description='고객 확인 대기, 수정 내용 대기 또는 접수 완료'
    )
    needs_clarification: bool = Field(default=False, description='주문 정보의 추가 확인이 필요한지 여부')
    question: str | None = Field(default=None, description='고객에게 확인할 주문 질문; 필요 없으면 null')


class IntentResult(BaseModel):
    """고객이 요청한 기능의 이름과, Jev가 그 선택에 대해 반환한 신뢰도를 담습니다."""

    intent: Literal[
        'product_search', 'event_participation', 'product_recommendation',
        'product_consultation', 'product_order', 'point_accumulation', 'unknown'
    ] = Field(description='분류된 의도')
    confidence: float | None = Field(default=None, ge=0, le=1, description='Jev 신뢰도; 확인 전이면 null')


class HistoryMessage(BaseModel):
    """고객이나 챗봇이 한 번 말한 내용과, 누가 말했는지를 함께 담습니다."""

    role: Literal['user', 'assistant'] = Field(description='문장을 말한 고객 또는 챗봇')
    content: str = Field(description='고객 또는 챗봇의 대화 내용')


class SessionState(BaseModel):
    """한 대화에서 받은 입력·고객 정보·작업 상태·대화 기록·최종 답변을 함께 보관합니다."""

    # 테스트 중에 추가한 상태도 다음 단계로 전달합니다.
    model_config = ConfigDict(extra='allow')

    # 식별자는 상태를 구분하는 값이며 인증이나 고객 신원 확인을 대신하지 않습니다.
    session_id: str | None = Field(default=None, description='대화를 구분할 세션 ID')
    customer_id: str | None = Field(default=None, description='확인된 고객 ID')
    customer: CustomerProfile | None = Field(default=None, description='서버 고객 자료에서 조회한 프로필; 조회되지 않으면 null')
    input: CustomerInput | None = Field(default=None, description='이번 턴의 고객 입력')
    intent: IntentResult | None = Field(default=None, description='현재 작업 의도와 신뢰도; 분류 보류 시 기존 값을 유지하고 미정이면 null')
    previous_intent: str | None = Field(default=None, description='직전 턴에서 분류한 의도; 첫 대화이면 null')
    history: list[HistoryMessage] = Field(default_factory=list, description='고객과 챗봇이 주고받은 대화 기록')
    search: SearchState | None = Field(default=None, description='상품검색 후보')
    recommendation: RecommendationState | None = Field(default=None, description='상품추천 조건과 후보')
    # 입력에 완료 상태가 있어도 바로 믿지 않고, 쿠폰 검증과 주문 승인은 실제 처리 함수에서 다시 확인합니다.
    coupon: CouponState | None = Field(default=None, description='쿠폰 확인과 스탬프 적립·혜택 사용 상태')
    order: OrderState | None = Field(default=None, description='주문 초안과 확인 상태')
    receipt: ReceiptState | None = Field(default=None, description='영수증 정보와 포인트 적립 상태')
    answer: dict[str, str] | None = Field(default=None, description='분류 보류 시 생성한 답변과 모델')
