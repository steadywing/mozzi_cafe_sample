# 의도 분류 테스트보드 구현 계획

목표: test 라우터에서 의도 분류를 실행하고, 개발자가 같은 API를 화면과 노트북에서 확인한다.

확정 규격: 사용자가 제공한 TypeSafe 공식 빠른 시작 문서에 따라 typesafe-sdk의 Choice를 사용한다. 기본 모델은 jev-latest, 키는 TYPESAFE_API_KEY다. state와 다섯 의도+unknown 기준을 전송하고 실제 choice·confidence·probabilities를 검증한다. 자유 텍스트 생성 대신 unknown의 확인 질문을 서버에서 구성한다.

인터페이스:
- GET /test: 의도 분류 테스트보드 HTML.
- GET /test/cases: 다섯 의도의 예제 요청과 기대 의도.
- POST /test/jev: text, has_image, session_state를 받아 의도를 분류한다.
- 성공 응답: result(intent, needs_clarification, question), trace(model, prompt_file, system_prompt, user_input, elapsed_ms).
- 실패: 입력 검증 422, 모델 미설정 503, 외부 실행 실패 502 또는 타임아웃 504. 비밀키를 응답·로그에 포함하지 않는다.

담당과 파일 경계:
- Codex 본체: main.py, routers/test.py, 의도 분류 처리 함수, 설정, 백엔드 검증과 통합. 모델 계약 확정 후 실제 호출을 연결한다.
- 테스트보드 담당: templates/test.html, static/js/intent-test.js, static/css/intent-test.css.
- 학습 자료 담당: notebooks/01_의도분류.ipynb, tests/fixtures/intent_cases.json. 다섯 의도별 한 사례. 저장된 실제 API 출력이나 비밀키를 넣지 않는다.

검증:
- 관련 API 계약 테스트를 먼저 작성하고 실패를 확인한 뒤 구현한다.
- 예제 JSON·노트북 구조·구문을 검증한다. 외부 모델 호출은 사용자 제공 규격 연결 후 별도로 확인한다.
- 가짜 클라이언트의 응답 검증과 실제 모델 정확도 측정을 구분한다.
- 화면은 실제 엔드포인트를 호출하고 입력·결과·실행 기록·오류를 표시한다.
- 커밋·푸시는 하지 않는다.

완료 검증:
- 자동 API 검증 10개 통과. 실제 SDK에 대체 HTTP 응답을 공급해 계약·실패 경로를 확인했다.
- 실제 TypeSafe API 호출에서 예제 5개 모두 기대 의도와 일치했다. 당시 반환 모델은 jev-1.14.0이다. 전체 모델 정확도의 추정치로 사용하지 않는다.
- 노트북 기본 전체 코드 셀 실행, nbformat 검증, 저장 출력 없음 확인. 기본 실행에서는 외부 API를 호출하지 않는다.
- 화면·서버·노트북은 동일 POST /test/jev와 프롬프트 파일을 사용한다.
