"""샘플 영수증을 읽고 가상 포인트를 적립하는 API를 제공합니다."""
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictBool, StrictInt
from services.notebook_points import start_points, confirm_points, reset_points
from common.notebook_step_store import clear_trace, record_result

router = APIRouter(tags=['챗봇 포인트 적립'])


class PointStart(BaseModel):
    """가상 세션과 샘플 영수증, 가상 고객을 담습니다."""
    session_id: str = Field(min_length=1, max_length=100, description='가상 세션 식별자')
    sample: Literal['receipt-001', 'receipt-002', 'receipt-003', 'mochi-receipt-01', 'mochi-receipt-02', 'mochi-receipt-03'] = Field(description='서버에서 제공하는 샘플 영수증')
    customer_id: str = Field(min_length=1, max_length=100, description='주문 자료와 비교할 가상 고객 ID')


class PointConfirmation(BaseModel):
    """고객 확인 여부와 실습용 적립 포인트를 담습니다."""
    session_id: str = Field(min_length=1, max_length=100, description='가상 세션 식별자')
    confirmed: StrictBool = Field(description='고객이 영수증 정보를 확인했는지 여부')
    points_to_add: StrictInt = Field(description='적립 기준 대신 직접 지정한 실습용 포인트')


@router.post('/chatbot/points/start')
def start(payload: PointStart):
    """샘플 영수증을 읽고 가상 주문과 비교한 결과를 돌려줍니다."""
    # 1. 판독 실행: 외부 판독 오류는 연결 확인 안내로 전달합니다.
    try:

        return record_result('points', payload.session_id, start_points(payload.session_id, payload.sample, payload.customer_id))
    except Exception:
        raise HTTPException(status_code=502, detail='영수증 판독에 실패했습니다. Gemini 설정과 샘플 자료를 확인해 주세요.')


@router.post('/chatbot/points/confirm')
def confirm(payload: PointConfirmation):
    """고객 확인과 실습 포인트로 서버의 가상 세션을 갱신합니다."""
    # 1. 확인 처리: 세션이 없으면 영수증 판독부터 시작하도록 안내합니다.
    try:

        return record_result('points', payload.session_id, confirm_points(payload.session_id, payload.confirmed, payload.points_to_add))
    except KeyError:
        raise HTTPException(status_code=404, detail='영수증 확인부터 시작해 주세요.')


@router.delete('/chatbot/points/{session_id}')
def reset(session_id: str):
    """가상 세션을 지우고 이미 처리한 영수증 기록은 보존합니다."""
    # 1. 세션 삭제: 현재 세션만 지우고 처리 이력은 유지합니다.

    deleted = reset_points(session_id)
    clear_trace('points', session_id)

    return {'deleted': deleted}
