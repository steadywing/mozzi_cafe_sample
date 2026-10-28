"""테스트 화면에서 고를 검색 사진과 영수증 자료를 제공합니다."""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from services.notebook_points import CASES, SAMPLES
from services.notebook_search import ROOT, sample_names


router = APIRouter(prefix='/test/api', tags=['테스트 예시 자료'])


@router.get('/search/samples')
def search_samples():
    """검색 실습에 준비된 샘플 사진의 이름 목록을 돌려줍니다."""
    # 1. 목록 반환: 실제 허용된 파일명만 화면에 전달합니다.

    return {'samples': sample_names()}


@router.get('/search/cases')
def search_cases():
    """준비된 검색 사례와 확인할 기대 결과를 화면에 돌려줍니다."""
    # 1. 사례 조회: 사진이 실제로 있는 사례만 선택할 수 있게 전달합니다.
    cases = json.loads((ROOT / 'tests/fixtures/search_cases.json').read_text(encoding='utf-8'))
    available = set(sample_names())

    return {'cases': [case for case in cases if case['sample'] in available]}


@router.get('/search/images/{sample}')
def search_sample_image(sample: str):
    """허용된 샘플 사진 이름을 받아 화면에서 볼 PNG를 돌려줍니다."""
    # 1. 사진 확인: 서버가 확인한 샘플 이름만 이미지로 제공합니다.
    if sample not in sample_names():

        return JSONResponse(status_code=404, content={'detail': '샘플 사진을 찾을 수 없습니다.'})

    return FileResponse(ROOT / 'data/search_images' / sample, media_type='image/png')


@router.get('/points/cases')
def receipt_cases():
    """준비된 영수증 사례와 미리보기 주소를 돌려줍니다."""
    # 1. 사례 반환: 각 이미지가 판독할 샘플과 같은 이름을 사용합니다.

    return {'cases': [{**case, 'image_url': f"/test/api/points/samples/{case['sample']}"} for case in CASES]}


@router.get('/points/samples/{sample}')
def receipt_sample(sample: str):
    """허용된 샘플 이름을 받아 해당 영수증 이미지를 돌려줍니다."""
    # 1. 이미지 확인: 정해진 목록에 없는 이름과 존재하지 않는 파일은 거절합니다.
    path = SAMPLES.get(sample)
    if path is None or not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=404, detail='샘플 영수증을 찾을 수 없습니다.')

    return FileResponse(path, media_type='image/png')
