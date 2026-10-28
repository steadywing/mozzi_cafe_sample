"""테스트보드의 HTML 화면 경로를 한곳에 모아 제공합니다."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


router = APIRouter(tags=['테스트 화면'])
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / 'templates')


@router.get('/', response_class=HTMLResponse, summary='서비스 구현 현황 화면')
def home(request: Request):
    """첫 화면 요청을 받으면 현재 구현 흐름을 설명하는 HTML을 돌려줍니다."""
    # 1. 화면 반환: 현재 API별 처리 흐름을 보여 주는 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='index.html')


@router.get('/test/intent', response_class=HTMLResponse, summary='의도 분류 테스트 화면')
def intent_page(request: Request):
    """의도 분류 화면 요청을 받으면 분류 결과를 확인할 HTML을 돌려줍니다."""
    # 1. 화면 반환: 매 턴 분류를 실행할 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='test.html')


@router.get('/test/unknown', response_class=HTMLResponse, summary='확인 답변 테스트 화면')
def unknown_page(request: Request):
    """확인 답변 화면 요청을 받으면 독립 실습 HTML을 돌려줍니다."""
    # 1. 화면 반환: 분류가 어려운 요청의 답변을 시험할 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='notebook_unknown.html')


@router.get('/test/order', response_class=HTMLResponse, summary='기존 주문 테스트 화면')
def order_page(request: Request):
    """기존 주문 화면 요청을 받으면 주문 처리 HTML을 돌려줍니다."""
    # 1. 화면 반환: 주문 초안과 모의 접수를 확인할 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='order.html')


@router.get('/test/order/practice', response_class=HTMLResponse, summary='단계별 주문 실습 화면')
def order_practice_page(request: Request):
    """단계별 주문 화면 요청을 받으면 노트북 실습 HTML을 돌려줍니다."""
    # 1. 화면 반환: 단계별 주문 상태를 확인할 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='notebook_order.html')


@router.get('/test/recommendation', response_class=HTMLResponse, summary='상품추천 테스트 화면')
def recommendation_page(request: Request):
    """상품추천 화면 요청을 받으면 추천 조건과 결과를 볼 HTML을 돌려줍니다."""
    # 1. 화면 반환: 추천 결과를 시험할 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='notebook_recommendation.html')


@router.get('/test/search', response_class=HTMLResponse, summary='상품검색 테스트 화면')
def search_page(request: Request):
    """상품검색 화면 요청을 받으면 샘플 사진 검색 HTML을 돌려줍니다."""
    # 1. 화면 반환: 샘플 사진과 문장을 선택할 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='notebook_search.html')


@router.get('/test/consultation', response_class=HTMLResponse, summary='정보문의 테스트 화면')
def consultation_page(request: Request):
    """정보문의 화면 요청을 받으면 카페 문서 답변 HTML을 돌려줍니다."""
    # 1. 화면 반환: 문서 선택과 답변을 확인할 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='notebook_consultation.html')


@router.get('/test/points', response_class=HTMLResponse, summary='포인트 적립 테스트 화면')
def points_page(request: Request):
    """포인트 적립 화면 요청을 받으면 영수증 실습 HTML을 돌려줍니다."""
    # 1. 화면 반환: 샘플 영수증의 판독과 적립을 시험할 템플릿을 엽니다.

    return templates.TemplateResponse(request=request, name='notebook_points.html')
