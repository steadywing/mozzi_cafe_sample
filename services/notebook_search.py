"""샘플 사진으로 이미지 임베딩과 메뉴 후보 검색을 실행합니다."""
import json
import os
from functools import lru_cache
from pathlib import Path
from time import perf_counter

from common.client import get_openai_client
from common.prompt_store import get_prompt

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = 'google/embeddinggemma-2'


def sample_names():
    """검색 사진 폴더에서 선택할 수 있는 PNG 파일 이름을 돌려줍니다."""
    # 1. 목록 조회: 서버에 준비한 샘플 사진만 선택지로 노출합니다.

    return sorted(path.name for path in (ROOT / 'data/search_images').glob('*.png') if path.is_file() and not path.is_symlink())


@lru_cache(maxsize=1)
def load_embedding_model():
    """처음 검색할 때 로컬에 설치된 임베딩 모델을 불러와 돌려줍니다."""
    # 1. 모델 준비: 사용 가능한 연산 장치를 고르고 다운로드 없이 로컬 모델을 엽니다.
    import torch
    from sentence_transformers import SentenceTransformer
    device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'

    return SentenceTransformer(MODEL_ID, device=device, config_kwargs={'audio_config': None}, model_kwargs={'torch_dtype': torch.float32}, local_files_only=True)


def create_image_embedding(image_path, text):
    """샘플 사진과 고객 문장을 받아 정규화된 임베딩 벡터를 돌려줍니다."""
    # 1. 벡터 생성: 노트북과 같은 검색용 입력으로 사진과 문장을 결합합니다.
    vector = load_embedding_model().encode({'image': str(image_path), 'text': text}, prompt_name='SearchQuery', normalize_embeddings=True)

    return vector.tolist()


def search_similar_menu(vector, top_k=3):
    """검색 벡터를 받아 FAISS의 메뉴 후보와 유사도를 돌려줍니다."""
    # 1. 인덱스 확인: 저장된 모델과 메뉴 순서, 벡터 차원을 비교합니다.
    import faiss
    import numpy as np
    metadata = json.loads((ROOT / 'data/embeddings/menu_images.json').read_text(encoding='utf-8'))
    menu = json.loads((ROOT / 'data/menu.json').read_text(encoding='utf-8'))
    index = faiss.read_index(str(ROOT / 'data/embeddings/menu_images.faiss'))
    if metadata['model_id'] != MODEL_ID or len(metadata['menu_ids']) != index.ntotal or len(vector) != index.d:
        raise ValueError('임베딩 모델과 인덱스가 일치하지 않습니다.')

    # 2. 후보 검색: 판매 중인 메뉴만 순서와 유사도를 함께 남깁니다.
    scores, positions = index.search(np.ascontiguousarray([vector], dtype='float32'), min(top_k, index.ntotal))
    products = {product['menu_id']: product for product in menu if product.get('available')}
    candidates = []

    ## 검색 순서대로 판매 중인 메뉴만 골라 유사도와 원본 메뉴를 함께 보관합니다.
    for score, position in zip(scores[0], positions[0]):
        if position >= 0:
            menu_id = metadata['menu_ids'][int(position)]
            if menu_id in products:
                candidates.append({'menu_id': menu_id, 'score': float(score), 'menu': products[menu_id]})

    return candidates


def ask_model(prompt, model_input):
    """검색 후보와 지침을 받아 모델의 안내 문장을 돌려줍니다."""
    # 1. 답변 생성: 검색된 후보만 모델에 전달합니다.
    response = get_openai_client().responses.create(model=os.getenv('OPENAI_MODEL', 'gpt-4.1-mini'), instructions=prompt, input=json.dumps(model_input, ensure_ascii=False))

    return response.output_text


def run_search(text, sample):
    """고객 문장과 허용된 샘플 사진으로 후보 검색과 답변 단계를 돌려줍니다."""
    # 1. 입력 준비: 샘플 목록에 있는 파일만 사용합니다.
    if sample not in sample_names():
        raise ValueError('준비된 샘플 사진을 선택해 주세요.')

    ## 허용된 사진과 고객 문장을 벡터로 만들고 검색 전 상태를 기록합니다.
    started = perf_counter()
    vector = create_image_embedding(ROOT / 'data/search_images' / sample, text)
    state = {'input': {'text': text, 'has_image': True}, 'search': {'image_sample': sample, 'image_vector': vector}}
    steps = [{'step': 'create_image_embedding', 'input': {'text': text, 'image_sample': sample, 'model_id': MODEL_ID}, 'state': json.loads(json.dumps(state)), 'vector_dimensions': len(vector)}]

    # 2. 후보 검색: 이미지 벡터로 실제 메뉴와 유사도를 확인합니다.
    candidates = search_similar_menu(vector)
    state['search']['candidates'] = candidates
    state['search']['candidate_menu_ids'] = [item['menu_id'] for item in candidates]
    steps.append({'step': 'search_similar_menu', 'input': {'vector_dimensions': len(vector), 'index_file': 'data/embeddings/menu_images.faiss', 'menu_file': 'data/menu.json', 'top_k': 3}, 'state': json.loads(json.dumps(state)), 'candidate_count': len(candidates)})

    # 3. 답변 생성: 후보가 없는 경우에는 모델을 부르지 않습니다.
    detail = {'executed': False}
    if candidates:
        prompt = get_prompt('prompts/search_response.md')
        model_input = {'text': text, 'candidates': candidates}
        answer = ask_model(prompt, model_input)
        state['answer'] = {'text': answer, 'model': os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}
        detail = {'executed': True, 'prompt': prompt, 'input': model_input}
    else:
        state['answer'] = {'text': '비슷한 메뉴를 찾지 못했습니다. 다른 사진을 올려 주세요.', 'model': 'python'}

    ## 모델 실행 여부를 마지막 단계에 남겨 답변과 검색 과정을 함께 보여줍니다.
    steps.append({'step': 'generate_search_response', 'input': {'text': text, 'candidate_menu_ids': state['search']['candidate_menu_ids']}, 'state': json.loads(json.dumps(state)), **detail})

    return {'state': state, 'steps': steps, 'elapsed_ms': round((perf_counter() - started) * 1000, 2)}
