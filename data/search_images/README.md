# 상품검색 테스트 사진

실제 고객이 휴대폰으로 찍은 상황을 모사한 AI 생성 이미지다. 메뉴 대표 사진과 다른 각도·배경·조명·섭취 상태를 사용한다. 실제 고객 사진은 포함하지 않는다.

내장 imagegen으로 생성했다. 1024×1024를 요청했지만 실제 출력은 1254×1254 PNG이며, 생성 원본을 그대로 저장했다.

## 이미지와 확인할 내용

| 파일 | 장면 | 기대 메뉴 또는 동작 |
|---|---|---|
| [search_cafe_latte.png](search_cafe_latte.png) | 창가에서 낮은 각도로 찍은 절반 마신 라떼 | `drink_cafe_latte` 후보 포함 |
| [search_flat_white.png](search_flat_white.png) | 노트북 옆 작은 잔, 위에서 촬영 | `drink_flat_white` 후보 포함 |
| [search_matcha_latte_dim.png](search_matcha_latte_dim.png) | 저녁 실내의 어두운 말차 라떼 | `drink_matcha_latte` 후보 포함 |
| [search_strawberry_mochi_bitten.png](search_strawberry_mochi_bitten.png) | 손에 든 한입 베어 문 딸기 모찌 | `dessert_strawberry_mochi` 후보 포함 |
| [search_injeolmi_mochi_box.png](search_injeolmi_mochi_box.png) | 포장 상자 안 인절미 모찌 4개 | `dessert_injeolmi_mochi` 후보 포함 |
| [search_mochi_waffle_side.png](search_mochi_waffle_side.png) | 야외 테라스에서 옆으로 찍은 와플 | `dessert_mochi_waffle` 후보 포함 |
| [search_not_on_menu_cheesecake.png](search_not_on_menu_cheesecake.png) | 메뉴에 없는 뉴욕 치즈케이크 | 적합한 메뉴가 없다고 안내하는지 확인 |
| [search_not_food_cat.png](search_not_food_cat.png) | 카페 의자의 고양이, 음식 없음 | 음식 검색 결과를 억지로 제시하지 않는지 확인 |

## 사용 시 참고

- 위 표는 테스트 목표이며 실제 검색 실행 결과가 아니다. 검색 모델·후보 수·유사도 기준을 정한 뒤 결과를 기록한다.
- 사진만으로 비슷한 메뉴나 재료를 확정하기 어렵다. 카페라떼·플랫화이트와 모찌·일반 와플 등의 혼동도 함께 확인한다.
- 메뉴에 없는 이미지도 최근접 검색에서는 후보가 나올 수 있다. 후보 없음 처리는 별도의 판단 기준이 필요하다.
- 이미지에서 알레르기나 정확한 재료를 추정하지 않고 `data/menu.json`을 조회한다.
- 합성 이미지로 확인한 뒤에는 사용 권한이 있는 실제 휴대폰 사진으로도 검증한다.
- 실제 생성 프롬프트는 같은 폴더의 `drinks-prompts.md`, `desserts-prompts.md`, `negative-prompts.md`에 보관한다.
