"""Jev와 OpenAI 연결을 필요할 때 만들고, 서버가 종료될 때까지 같은 연결을 재사용합니다."""
import os
from threading import Lock

from openai import OpenAI
from typesafe_sdk import RetryPolicy, TypeSafeClient


_jev_client = None
_openai_client = None
_jev_lock = Lock()
_openai_lock = Lock()


def get_jev_client():
    """Jev 연결이 필요하면 처음 한 번 만들고, 다음 호출부터는 같은 연결을 돌려줍니다."""
    global _jev_client

    # 1. 동시 요청 제어: 동시에 첫 요청이 들어와도 클라이언트는 하나만 만듭니다.
    with _jev_lock:
        if _jev_client is None:
            # 2. 연결 생성: 환경변수의 API 키와 모델명으로 Jev 연결을 만들고, 키가 없으면 오류로 알립니다.
            api_key = os.getenv('TYPESAFE_API_KEY', '').strip()
            if not api_key:
                raise RuntimeError('TYPESAFE_API_KEY가 설정되지 않았습니다.')

            ## 키를 확인한 뒤 설정된 모델명으로 재사용할 연결을 만듭니다.
            _jev_client = TypeSafeClient(
                api_key=api_key,
                model=os.getenv('TYPESAFE_MODEL', 'jev-latest').strip() or 'jev-latest',
                timeout=20,
                retry=RetryPolicy(max_retries=0),
            )

        return _jev_client


def get_openai_client():
    """OpenAI 연결이 필요하면 처음 한 번 만들고, 다음 호출부터는 같은 연결을 돌려줍니다."""
    global _openai_client

    # 1. 연결 재사용: 여러 요청이 겹쳐도 OpenAI 연결을 한 번만 만들고, 키가 없으면 오류로 알립니다.
    with _openai_lock:
        if _openai_client is None:
            if not os.getenv('OPENAI_API_KEY', '').strip():
                raise RuntimeError('OPENAI_API_KEY가 설정되지 않았습니다.')

            ## 키가 있으면 다음 요청에서도 사용할 연결을 보관합니다.
            _openai_client = OpenAI()

        return _openai_client


def close_clients():
    """서버가 종료되면 만들어 둔 Jev와 OpenAI 연결을 닫고 보관한 참조를 비웁니다."""
    global _jev_client, _openai_client
    try:
        with _jev_lock:
            if _jev_client is not None:
                # 1. Jev 연결 종료: 보관한 연결을 비운 뒤 닫아, 나중에 필요하면 새로 만들게 합니다.
                client = _jev_client
                _jev_client = None
                client.close()
    finally:
        # 2. OpenAI 연결 종료: Jev 연결을 닫다가 오류가 나더라도 OpenAI 연결은 따로 닫습니다.
        with _openai_lock:
            if _openai_client is not None:
                client = _openai_client
                _openai_client = None
                client.close()
