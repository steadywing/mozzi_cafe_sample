"""노트북 기능의 단계 상태를 세션별 메모리에 보관합니다."""
from copy import deepcopy
from threading import Lock

FEATURES = {'intent', 'unknown', 'order', 'recommendation', 'search', 'consultation', 'points'}
step_store = {}
step_lock = Lock()


def save_turn(feature: str, session_id: str, steps: list[dict], state: dict) -> int:
    """기능·세션과 단계 결과를 받아 각 상태의 독립된 복사본을 저장하고 턴 번호를 돌려줍니다."""
    # 1. 기록 준비: 기존 턴 뒤에 이번 실행의 단계와 최종 상태를 복사해 붙입니다.
    with step_lock:
        turns = step_store.setdefault(feature, {}).setdefault(session_id, [])
        turn_index = len(turns) + 1
        turns.append({'turn_index': turn_index, 'steps': deepcopy(steps), 'state': deepcopy(state)})

    # 2. 번호 반환: 화면에서 이번 실행을 구분할 순번을 돌려줍니다.

    return turn_index


def get_trace(feature: str, session_id: str) -> list[dict]:
    """기능·세션을 받아 저장된 턴과 단계 상태의 독립된 복사본을 돌려줍니다."""
    # 1. 기록 조회: 화면이 받은 값을 바꿔도 저장소에 영향을 주지 않도록 복사합니다.
    with step_lock:
        turns = deepcopy(step_store.get(feature, {}).get(session_id, []))

    # 2. 결과 반환: 세션에 기록이 없으면 빈 목록을 돌려줍니다.

    return turns


def clear_trace(feature: str, session_id: str) -> bool:
    """기능·세션을 받아 해당 실습의 단계 기록만 지우고 삭제 여부를 돌려줍니다."""
    # 1. 선택 삭제: 다른 기능과 세션의 기록은 남겨 둡니다.
    with step_lock:
        deleted = step_store.get(feature, {}).pop(session_id, None) is not None

    # 2. 결과 반환: 실제 기록이 있었는지 돌려줍니다.

    return deleted


def record_result(feature: str, session_id: str, result: dict) -> dict:
    """기능 실행 결과와 세션 ID를 받아 단계 상태를 저장하고 조회 정보를 응답에 붙여 돌려줍니다."""
    # 1. 상태 저장: 실행이 끝난 각 단계의 스냅샷을 한 턴으로 보관합니다.
    result['state']['session_id'] = session_id
    turn_index = save_turn(feature, session_id, result['steps'], result['state'])

    # 2. 결과 반환: 화면에서 이번 세션과 저장된 턴을 확인할 수 있게 합니다.
    result['session_id'] = session_id
    result['turn_index'] = turn_index

    return result
