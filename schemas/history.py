"""대화 저장 요청에서 받을 고객·세션 ID와 메시지 목록의 형식을 정합니다."""
from pydantic import BaseModel, Field, field_validator

from schemas.session_state import HistoryMessage


class HistoryInput(BaseModel):
    """저장 요청으로 받은 고객 ID·세션 ID와 이번에 추가할 메시지 목록을 담습니다."""

    customer_id: str = Field(min_length=1, description='대화를 나눈 고객 ID')
    session_id: str = Field(min_length=1, description='대화를 구분할 세션 ID')
    messages: list[HistoryMessage] = Field(min_length=1, description='이번 턴에 저장할 고객 입력과 챗봇 답변')

    @field_validator('customer_id', 'session_id')
    @classmethod
    def check_identifier(cls, value):
        """고객·세션 ID를 받아 앞뒤 공백을 뺀 값을 돌려주고, 공백뿐인 ID는 오류로 알립니다."""
        # 1. ID 확인: 앞뒤 공백을 빼고, 남는 글자가 없는 ID는 저장하지 못하게 오류로 알립니다.
        if not value.strip():
            raise ValueError('고객과 세션 ID를 입력해주세요.')

        return value.strip()
