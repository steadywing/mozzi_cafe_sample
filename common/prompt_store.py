"""모델 지침 파일을 메모리에 읽어 두고, 조회하거나 수정한 지침을 저장합니다."""
from pathlib import Path
from threading import Lock

PROMPT_DIR = Path(__file__).resolve().parents[1] / 'prompts'
_prompts = {}
_loaded = False
_lock = Lock()


def _load_prompts():
    """파일에서 모델 지침을 모두 읽는 데 성공하면, 메모리에 보관한 지침을 새 내용으로 바꿉니다."""
    global _prompts, _loaded

    # 1. 자료 조회: 중간에 읽기가 실패하면 기존 메모리 내용은 그대로 남습니다.
    loaded = {path.name: path.read_text(encoding='utf-8') for path in PROMPT_DIR.glob('*.md')}
    _prompts = loaded
    _loaded = True


def load_prompts():
    """서버가 시작될 때 지침 파일을 읽어 메모리에 보관해, 요청마다 파일을 다시 읽지 않게 합니다."""

    # 1. 프롬프트 준비: 다른 요청과 겹치지 않도록 잠근 뒤 파일을 읽습니다.
    with _lock:
        _load_prompts()


def get_prompt(filename: str):
    """지침 파일명을 받아 메모리의 내용을 돌려주며, 아직 읽지 않았다면 먼저 파일을 읽습니다."""
    # 1. 조회 준비: 다른 요청이 지침을 바꾸는 도중에 읽지 않도록 잠금을 겁니다.
    with _lock:
        # 2. 최초 읽기: 서버 시작 준비를 거치지 않았어도, 메모리에 지침이 없으면 파일부터 읽습니다.
        if not _loaded:
            _load_prompts()

        # 3. 지침 반환: 전달받은 경로에서 파일명만 꺼내, 메모리에 보관한 해당 지침을 돌려줍니다.

        return _prompts[Path(filename).name]


def save_prompt(filename: str, content: str):
    """파일명과 수정한 지침을 받아 저장하고, 파일 저장이 성공한 경우에만 메모리도 바꿉니다."""
    # 1. 저장 준비: 잠금 안에서 초기 지침과 저장할 파일명을 확인합니다.
    with _lock:
        if not _loaded:
            _load_prompts()
        name = Path(filename).name
        if name not in _prompts:
            raise FileNotFoundError(name)

        # 2. 지침 저장: 파일 쓰기가 끝난 뒤에만 메모리도 바꿔, 저장 실패 시 이전 지침을 유지합니다.
        (PROMPT_DIR / name).write_text(content, encoding='utf-8')
        _prompts[name] = content
