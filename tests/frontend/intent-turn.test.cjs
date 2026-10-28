const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

/** 의도 분류 화면에 대체 서버 응답을 전달해 답변과 처리 단계를 확인합니다. */
test('unknown 답변과 일반 의도의 처리 단계를 표시합니다', async () => {
  // 1. 화면 준비: 스크립트가 사용하는 요소와 이벤트를 간단한 객체로 만듭니다.
  class Element {
    /** 빈 입력값과 자식 목록을 가진 화면 요소를 만듭니다. */
    constructor() {
      // 1. 요소 준비: 테스트에서 바꿀 값과 이벤트·자식 목록을 초기화합니다.
      this.value = '';
      this.children = [];
      this.events = {};
      this.textContent = '';
    }
    /** 이벤트 이름에 실행할 함수를 보관합니다. */
    addEventListener(type, handler) {
      // 1. 이벤트 보관: 이벤트 이름으로 실행 함수를 저장합니다.
      this.events[type] = handler;
    }
    /** 전달한 요소들을 자식 목록에 추가합니다. */
    append(...children) {
      // 1. 자식 추가: 전달받은 요소를 목록 뒤에 넣습니다.
      this.children.push(...children);
    }
    /** 자식 목록을 전달한 요소들로 교체합니다. */
    replaceChildren(...children) {
      // 1. 자식 교체: 기존 목록 대신 새 요소들을 보관합니다.
      this.children = children;
    }
    /** 테스트 케이스 목록에서 버튼 자식을 돌려줍니다. */
    querySelectorAll() {
      // 1. 목록 선택: 테스트에서 조회할 자식 요소 목록을 돌려줍니다.

      return this.children;
    }
    /** 선택 상태 설정을 테스트 화면에서 받아줍니다. */
    setAttribute() {
      // 1. 호출 수용: 이 테스트에서는 속성값을 별도로 저장하지 않습니다.
    }
    /** 입력창의 초점 이동을 테스트 화면에서 받아줍니다. */
    focus() {
      // 1. 호출 수용: 실제 브라우저 초점 이동은 실행하지 않습니다.
    }
    /** 환영 문구 삭제를 테스트 화면에서 받아줍니다. */
    remove() {
      // 1. 호출 수용: 이 테스트에서는 실제 화면 삭제를 실행하지 않습니다.
    }
  }
  const elements = new Map();
  /** 선택자에 해당하는 화면 요소를 만들거나 기존 요소를 돌려줍니다. */
  const element = (selector) => {
    // 1. 요소 선택: 같은 선택자는 같은 객체를 사용합니다.
    if (!elements.has(selector)) elements.set(selector, new Element());

    return elements.get(selector);
  };

  // 2. 응답 준비: 첫 턴은 확인 답변이 있고 두 번째 턴은 일반 의도입니다.
  /** 의도 이름을 받아 해당 턴의 상태와 실행 단계 응답을 만듭니다. */
  const responses = ['unknown', 'product_order'].map((intent) => {
    // 1. 응답 구성: unknown일 때만 답변 생성 단계를 포함합니다.
    const state = {input: {text: '입력', has_image: false}, previous_intent: null, history: [], intent: {intent, confidence: 0.9}, answer: null};
    const steps = [{step: 'prepare_state', state}, {step: 'classify_intent', state}];
    if (intent === 'unknown') {
      state.answer = {answer: '어떤 도움이 필요하신가요?', model: 'test-model'};
      steps.push({step: 'generate_unknown_response', state, model: 'test-model', input: [{role: 'user', content: '입력'}], prompt: '확인 지침'});
    }
    steps.push({step: 'save_state', state});

    return {state, steps, model: 'jev-test', prompt: '분류 지침', elapsed_ms: 10};
  });
  const sandbox = {
    document: {querySelector: element, createElement: () => new Element()},
    crypto: {randomUUID: () => 'test-session'},
    /** 사례 조회와 턴 요청에 준비한 대체 응답을 반환합니다. */
    fetch: async (url) => {
      // 1. 요청 구분: 사례 목록과 분류 결과를 외부 연결 없이 제공합니다.
      const data = url === '/test/api/intent-turn/cases' ? {cases: []} : responses.shift();

      return {ok: true, json: async () => data};
    },
  };
  vm.runInNewContext(readFileSync('static/js/intent-turn.js', 'utf8'), sandbox);
  await new Promise(setImmediate);

  // 3. 첫 턴: 확인 답변 말풍선과 답변 생성의 모델·입력·지침을 확인합니다.
  element('#chat-input').value = '네';
  await element('#chat-form').events.submit({preventDefault() {}});
  const bubbles = element('#chat-messages').children;
  assert.equal(bubbles[2].className, 'chat-message assistant');
  assert.equal(bubbles[2].children[1].textContent, '어떤 도움이 필요하신가요?');
  assert.match(element('#answer-summary').textContent, /test-model/);
  assert.equal(element('#answer-prompt').textContent, '확인 지침');
  assert.match(element('#answer-input').textContent, /입력/);

  // 4. 다음 턴: 일반 의도에는 답변 생성이 없음을 보여주고 이전 상세 내용을 지웁니다.
  element('#chat-input').value = '커피 주세요';
  await element('#chat-form').events.submit({preventDefault() {}});
  assert.match(element('#answer-summary').textContent, /실행하지 않았습니다/);
  assert.equal(element('#answer-prompt').textContent, '이번 턴에는 실행하지 않았습니다.');
  assert.equal(element('#chat-messages').children.length, 5);
});
