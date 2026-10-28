"""노트북 실습의 단계별 저장 기록을 읽고 초기화합니다."""
from fastapi import APIRouter, HTTPException

from common.notebook_step_store import FEATURES, clear_trace, get_trace

router = APIRouter(prefix='/test/api', tags=['테스트 실행 기록'])


@router.get('/traces/{feature}/{session_id}')
def read_notebook_trace(feature: str, session_id: str):
    """기능과 세션 ID를 받아 저장된 턴별 처리 단계와 상태를 돌려줍니다."""
    # 1. 기능 확인: 준비된 노트북 기능의 기록만 조회합니다.
    if feature not in FEATURES:
        raise HTTPException(status_code=404, detail='실습 기능을 찾을 수 없습니다.')

    # 2. 기록 반환: 세션에 저장한 턴과 단계 상태를 복사해 돌려줍니다.

    return {'session_id': session_id, 'feature': feature, 'turns': get_trace(feature, session_id)}


@router.delete('/traces/{feature}/{session_id}')
def delete_notebook_trace(feature: str, session_id: str):
    """기능과 세션 ID를 받아 해당 실습의 단계 기록만 지웁니다."""
    # 1. 기능 확인: 다른 경로의 기록을 잘못 지우지 않도록 기능 이름을 제한합니다.
    if feature not in FEATURES:
        raise HTTPException(status_code=404, detail='실습 기능을 찾을 수 없습니다.')

    # 2. 기록 삭제: 선택한 기능과 세션의 턴 목록만 지웁니다.

    return {'deleted': clear_trace(feature, session_id)}
