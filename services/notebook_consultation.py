"""카페 문서 선택부터 근거 기반 답변까지 실습 흐름을 실행합니다."""
import json
import os
from pathlib import Path
from time import perf_counter

from typesafe_sdk import Choice
from common.client import get_jev_client, get_openai_client
from common.prompt_store import get_prompt
from schemas.session_state import SessionState

DOCUMENT_DIR = Path(__file__).resolve().parents[1] / 'data' / 'cafe_docs'


def document_catalog():
    """카페 정보 폴더에서 읽을 수 있는 문서 이름과 제목을 돌려줍니다."""
    # 1. 목록 준비: 서버가 정한 폴더의 마크다운 파일만 선택 대상으로 만듭니다.

    return {path.name: path.stem for path in sorted(DOCUMENT_DIR.glob('*.md')) if path.is_file()}


def generate_document_selection(state: SessionState, catalog: dict):
    """고객 질문과 허용 문서 목록으로 Jev에 관련 문서를 선택해 상태에 담습니다."""
    # 1. 선택 입력: 문서별 선택지와 고객 질문, 대화 기록을 준비합니다.
    prompt = get_prompt('prompts/consultation_query.md')
    model_input = {'text': state.input.text, 'history': [item.model_dump(mode='json') for item in state.history], 'document_catalog': catalog}
    questions = {f'document_{i}': Choice(instructions=f'{prompt}\n문서: {name} ({title})', criteria={'relevant': '질문에 답하는 데 필요한 문서입니다.', 'irrelevant': '질문과 관련 없는 문서입니다.'}) for i, (name, title) in enumerate(catalog.items())}

    # 2. 문서 선택: 문서가 없으면 외부 모델 없이 빈 선택을 남깁니다.
    selected = []
    if questions:
        response = get_jev_client().system_one(state=model_input, questions=questions)
        selected = [name for i, name in enumerate(catalog) if response.answers[f'document_{i}'].choice == 'relevant']
    state.consultation = {'selected_documents': selected, 'documents': {}}

    return state, {'input': model_input, 'prompt': prompt, 'questions': {name: question.model_dump(mode='json') for name, question in questions.items()}, 'model': os.getenv('TYPESAFE_MODEL', 'jev-latest') if questions else None}


def load_cafe_documents(state: SessionState, catalog: dict):
    """선택된 허용 문서의 원문을 읽어 상태에 담아 돌려줍니다."""
    # 1. 원문 조회: 허용 목록에 있는 파일만 읽어 출처와 함께 보관합니다.
    state.consultation['documents'] = {name: (DOCUMENT_DIR / name).read_text(encoding='utf-8') for name in state.consultation['selected_documents'] if name in catalog}

    return state


def generate_consultation_response(state: SessionState):
    """질문과 선택된 원문으로 답변을 만들고 사용한 입력과 지침을 돌려줍니다."""
    # 1. 자료 확인: 선택된 원문이 없으면 모델 없이 확인 불가를 안내합니다.
    documents = state.consultation['documents']
    prompt = get_prompt('prompts/consultation_response.md')
    model_input = {'question': state.input.text, 'history': [item.model_dump(mode='json') for item in state.history], 'documents': documents}
    if not documents:
        state.answer = {'text': '관련 자료를 찾지 못해 확인할 수 없습니다.', 'model': '자료 없음'}

        return state, {'input': model_input, 'prompt': prompt, 'model': None}

    # 2. 답변 생성: 실제 문서와 질문만 답변 지침과 함께 모델에 전달합니다.
    model = os.getenv('OPENAI_MODEL', 'gpt-5-nano').strip() or 'gpt-5-nano'
    response = get_openai_client().responses.create(model=model, instructions=prompt, input=json.dumps(model_input, ensure_ascii=False))
    if not response.output_text.strip():
        raise ValueError('모델이 답변을 반환하지 않았습니다.')
    state.answer = {'text': response.output_text.strip(), 'model': response.model}

    return state, {'input': model_input, 'prompt': prompt, 'model': response.model}


def run_consultation(state: SessionState):
    """고객 질문을 받아 문서 선택과 답변 과정을 순서대로 실행해 기록을 돌려줍니다."""
    # 1. 실행 준비: 요청 상태를 복사하고 서버의 문서 목록을 조회합니다.
    started = perf_counter()
    state = state.model_copy(deep=True)
    catalog = document_catalog()
    state, selection = generate_document_selection(state, catalog)
    steps = [{'step': 'generate_document_selection', 'state': state.model_dump(mode='json'), **selection}]

    # 2. 근거와 답변: 선택한 원문을 읽고 답변을 만들어 각 결과를 기록합니다.
    selected_documents = list(state.consultation['selected_documents'])
    state = load_cafe_documents(state, catalog)
    steps.append({'step': 'load_cafe_documents', 'input': {'selected_documents': selected_documents, 'document_directory': 'data/cafe_docs'}, 'state': state.model_dump(mode='json'), 'loaded_documents': list(state.consultation['documents'])})

    ## 읽어 둔 원문으로 답변을 만든 뒤 실제 입력과 결과 상태를 기록합니다.
    state, answer = generate_consultation_response(state)
    steps.append({'step': 'generate_consultation_response', 'state': state.model_dump(mode='json'), **answer})

    return {'state': state.model_dump(mode='json'), 'steps': steps, 'elapsed_ms': round((perf_counter() - started) * 1000, 2)}
