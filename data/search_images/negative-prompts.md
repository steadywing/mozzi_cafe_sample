# 상품검색 음성 사례 생성 프롬프트

- 생성 방식: built-in `image_gen`, 각 이미지별 개별 호출
- 요청 크기: 1024×1024 PNG
- 실제 출력: 두 파일 모두 1254×1254 PNG. 생성 원본을 그대로 저장했으며 리사이즈하지 않음.
- 저장 방식: 각 생성 직후 프로젝트 경로에 복사. 기존 파일 덮어쓰기 없음.
- 시각 확인: 치즈케이크는 옅은 노랑 크림치즈와 갈색 비스킷 바닥, 흰 접시·포크·사용한 냅킨이 있는 일상 카페 사진. 고양이는 카페 의자 위에 앉은 모습이며 음식이 없음. 두 이미지 모두 글자·로고·워터마크 없음.

## search_not_on_menu_cheesecake.png

```text
Use case: photorealistic-natural
Asset type: customer smartphone photo for cafe image-search negative test. Square 1:1 PNG, request 1024x1024 pixels.
Subject: exactly one slice of New York cheesecake, dense pale yellow cream-cheese filling and a clearly visible thin brown biscuit crumb base, on a plain matte white ceramic plate. Absolutely no strawberry, mochi, waffle, bread, latte or other menu products, no additional food or toppings.
Scene: small everyday cafe wooden table. A plain metal fork and slightly crumpled used paper napkin sit casually beside the plate. Photograph from a customer's ordinary high diagonal angle, like a casual Instagram smartphone snapshot before eating. Modest imperfect framing, natural indoor daylight, realistic phone-camera contrast and texture, most of the table and food in focus.
Constraints: believable everyday phone photograph, no professional advertising lighting, no overly polished styling, no dramatic bokeh, no text, letters, labels, logos or watermark.
```

## search_not_food_cat.png

```text
Use case: photorealistic-natural
Asset type: customer smartphone photo for image-search non-food negative test. Square 1:1 PNG, request 1024x1024 pixels.
Subject: one healthy realistic domestic tabby cat sitting naturally on the seat of a simple cafe chair, alert relaxed expression, realistic eyes, ears, whiskers, paws and anatomy.
Scene: an ordinary quiet cafe corner, visible chair, plain wall and table legs in the background. The cat is photographed casually by a seated customer from their seated eye level, slightly looking down, like an unplanned everyday smartphone snap. Natural interior daylight, moderate phone-camera detail, believable imperfect framing and ordinary surroundings. Background remains reasonably clear.
Constraints: no food, drinks, plates, bowls, cups, menus or food imagery anywhere. No humans or hands, no accessories on the cat. No advertising look, dramatic studio lighting, extreme bokeh, text, letters, logos or watermark.
```
