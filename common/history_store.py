"""고객별 JSON 파일에 세션별 대화를 저장하고, 요청한 대화만 읽거나 삭제합니다."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

HISTORY_DIR = Path(__file__).resolve().parents[1] / 'data' / 'history'


def _history_path(customer_id):
    """고객 ID를 해시 문자열로 바꾸어, ID가 직접 드러나지 않는 대화 파일 경로를 돌려줍니다."""

    # 1. 경로 준비: 고객 식별자를 파일명에 노출하지 않도록 해시로 바꿉니다.
    key = json.dumps(customer_id, ensure_ascii=False)
    filename = hashlib.sha256(key.encode('utf-8')).hexdigest()

    return HISTORY_DIR / f'{filename}.json'


def _read_sessions(customer_id):
    """고객 ID에 해당하는 파일에서 세션별 대화를 읽고, 파일이 없으면 빈 딕셔너리를 돌려줍니다."""
    # 1. 파일 확인: 고객 기록 파일의 위치를 구하고 존재 여부를 확인합니다.
    path = _history_path(customer_id)

    # 2. 빈 기록 처리: 고객 파일이 없으면 저장된 세션이 없다는 뜻으로 빈 딕셔너리를 돌려줍니다.
    if not path.exists():

        return {}

    # 3. 자료 조회: 저장된 JSON을 세션별 데이터로 바꿉니다.

    return json.loads(path.read_text(encoding='utf-8'))


def _write_sessions(customer_id, sessions):
    """고객 ID와 세션별 대화를 받아 임시 파일에 모두 쓴 뒤, 기존 대화 파일을 교체합니다."""

    # 1. 저장 준비: 기록 폴더와 교체할 파일 경로를 준비합니다.
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _history_path(customer_id)
    temporary_path = None

    # 2. 안전한 저장: 임시 파일을 끝까지 쓴 뒤 기존 파일을 바꿉니다.
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=HISTORY_DIR, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(sessions, temporary, ensure_ascii=False, indent=2)
        os.replace(temporary_path, path)
    finally:
        # 3. 임시 파일 정리: 저장 도중 문제가 생겨도 남은 임시 파일을 지웁니다.
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def load_history(customer_id, session_id):
    """고객 ID와 세션 ID로 저장된 대화 목록을 찾고, 해당 대화가 없으면 빈 목록을 돌려줍니다."""

    # 1. 자료 조회: 고객의 세션 중 요청한 세션의 대화 기록을 꺼냅니다.
    sessions = _read_sessions(customer_id)

    return sessions.get(session_id, [])


def delete_history(customer_id, session_id):
    """고객 ID와 세션 ID에 맞는 대화만 지우고, 실제로 지웠는지 True 또는 False로 알려줍니다."""

    # 1. 삭제 확인: 해당 고객에게 요청한 세션이 없으면 파일을 바꾸지 않고 False를 돌려줍니다.
    sessions = _read_sessions(customer_id)
    if session_id not in sessions:

        return False

    # 2. 삭제 반영: 선택한 세션만 지우고 나머지 기록을 저장합니다.
    del sessions[session_id]
    _write_sessions(customer_id, sessions)

    return True


def clear_history():
    """모든 고객의 대화 JSON 파일을 지우고, 삭제한 파일이 몇 개인지 돌려줍니다."""

    # 1. 전체 삭제: 대화 기록 폴더의 JSON 파일만 삭제합니다.
    paths = list(HISTORY_DIR.glob('*.json'))
    for path in paths:
        path.unlink()

    return len(paths)


def save_history(customer_id, session_id, messages):
    """고객 ID와 세션 ID에 받은 메시지 목록을 저장하며, 해당 세션의 기존 대화는 덮어씁니다."""

    # 1. 대화 저장: 다른 세션은 그대로 두고, 선택한 세션의 메시지 목록만 받은 내용으로 바꿔 저장합니다.
    sessions = _read_sessions(customer_id)
    sessions[session_id] = messages
    _write_sessions(customer_id, sessions)
