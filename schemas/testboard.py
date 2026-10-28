"""화면에서 받은 모델 지침이 비어 있지 않은지 확인할 입력 형식을 정합니다."""
from pydantic import BaseModel, Field, field_validator


class PromptInput(BaseModel):
    """테스트 화면에서 수정한 모델 지침을 받아, 저장할 내용이 있는지 확인합니다."""

    content: str = Field(min_length=1, max_length=50000, description='테스트보드에서 저장할 프롬프트 내용')

    @field_validator('content')
    @classmethod
    def check_content(cls, value):
        """저장할 지침을 받아 내용이 있으면 그대로 돌려주고, 공백뿐이면 오류로 알립니다."""
        # 1. 내용 확인: 모델에게 보낼 지침이 사라지지 않도록, 공백뿐인 내용은 오류로 알립니다.
        if not value.strip():
            raise ValueError('프롬프트 내용을 입력해주세요.')

        return value
