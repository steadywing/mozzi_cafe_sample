const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

const scenarios = [
  {name: 'intent', config: {}, endpoint: '/intent_classifier', casesUrl: '/test/cases', promptsUrl: '/test/prompts', promptKeys: ['jev', 'persona', 'unknown']},
  {name: 'order', config: {endpoint: '/product_order', casesUrl: '/test/order/cases', promptsUrl: '/test/order/prompts', promptKeys: 'persona,order'}, endpoint: '/product_order', casesUrl: '/test/order/cases', promptsUrl: '/test/order/prompts', promptKeys: ['persona', 'order']},
];

for (const scenario of scenarios) {
/** 의도 분류·주문 화면에서 사례를 두 번 보내, 같은 세션에 대화와 처리 기록이 쌓이는지 확인합니다. */
test(`${scenario.name}: cases keep the current session and accumulate turns`, async () => {
  // 1. 화면 대체: 브라우저 없이 실행할 수 있도록 버튼·입력창에 필요한 동작만 만듭니다.
  class Element {
    /** 입력값·자식 요소·선택 항목을 비워, 테스트에 쓸 화면 요소를 만듭니다. */
    constructor() { this.value = ''; this.children = []; this.events = {}; this.options = []; }
    /** 이벤트 이름과 실행할 함수를 받아, 테스트에서 직접 호출할 수 있게 보관합니다. */
    addEventListener(type, handler) { this.events[type] = handler; }
    /** 새 자식 요소를 받아, 기존 화면 내용을 그 요소들로 교체합니다. */
    replaceChildren(...children) { this.children = children; }
    /** 전달받은 요소들을 기존 자식 목록 뒤에 추가합니다. */
    append(...children) { this.children.push(...children); }
    /** 고객 선택 항목을 추가하고, 선택값이 없으면 첫 항목을 선택합니다. */
    add(option) { this.options.push(option); if (!this.value) this.value = option.value; }
    /** 이 테스트에서 사례 버튼으로 사용하는 자식 요소 목록을 돌려줍니다. */
    querySelectorAll() { return this.children; }
    /** 속성 지정 호출을 받아 주며, 이 테스트에서는 속성값을 따로 저장하지 않습니다. */
    setAttribute() {}
    /** 입력창 초점 이동 호출을 받아 주며, 실제 브라우저 초점은 만들지 않습니다. */
    focus() {}
    /** 환영 문구 삭제 호출을 받아 주며, 이 테스트에서는 화면에서 삭제하지 않습니다. */
    remove() {}
  }
  const elements = new Map();
  /** 선택자로 화면 요소를 찾아 돌려주며, 처음 찾는 선택자라면 빈 요소를 만들어 보관합니다. */
  const element = selector => {
    // 1. 요소 조회: 같은 선택자는 같은 객체를 돌려줘 앞서 바꾼 화면 값을 확인할 수 있게 합니다.
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };

  // 2. 서버 대체: 요청 목록과 세션별 대화·처리 기록을 메모리에 저장합니다.
  const requests = [];
  const turns = new Map();
  const histories = new Map();
  const sandbox = {
    document: {body: {dataset: scenario.config}, querySelector: element, createElement: () => new Element()},
    Option: class { /** 고객 이름과 ID를 받아, 선택 상자에 넣을 표시값과 선택값을 보관합니다. */ constructor(text, value) { this.text = text; this.value = value; } },
    URLSearchParams,
    /** 요청 주소에 맞는 가짜 응답을 돌려주고, 처리 요청과 대화 저장은 세션별로 기록합니다. */
    fetch: async (url, options) => {
      // 1. 응답 선택: 고객·사례·프롬프트 조회는 준비된 값을, 처리 요청은 갱신된 세션 상태를 돌려줍니다.
      let data;
      if (url === '/test/customers') data = {customers: [{customer_id: 'c1', name: '고객'}]};
      else if (url === scenario.casesUrl) data = {cases: [{title: '사례', input: {text: '안녕하세요', has_image: false}}]};
      else if (url === scenario.promptsUrl) data = Object.fromEntries(scenario.promptKeys.map((key) => [key, {content: `${key} prompt`} ]));
      else if (url === scenario.endpoint) {
        const request = JSON.parse(options.body);
        requests.push(request);
        const session = request.session_id || `session-${requests.length}`;
        turns.set(session, [...(turns.get(session) || []), {steps: []}]);
        data = {...request, session_id: session, intent: null, answer: {answer: '안녕하세요'}};
      } else if (url === '/history') {
        const request = JSON.parse(options.body);
        const history = [...(histories.get(request.session_id) || []), ...request.messages];
        histories.set(request.session_id, history);
        data = {history};
      }
      else if (url.startsWith('/test/states?')) data = {states: turns.get(new URLSearchParams(url.split('?')[1]).get('session_id'))};
      else throw new Error(`Unexpected URL: ${url}`);
      // 2. 응답 반환: 화면 코드가 실제 fetch 응답처럼 성공 여부와 JSON 본문을 읽게 합니다.
      return {ok: true, json: async () => data};
    },
  };

  // 3. 화면 실행: 실제 화면 스크립트를 대체 브라우저에서 실행하고 초기 조회가 끝나길 기다립니다.
  vm.runInNewContext(readFileSync('static/js/intent-test.js', 'utf8'), sandbox);
  await new Promise(setImmediate);
  for (const key of scenario.promptKeys) assert.equal(element(`#${key}-prompt`).textContent, `${key} prompt`);
  const pickCase = () => element('#case-list').children[0].events.click();
  const submit = () => element('#chat-form').events.submit({preventDefault() {}});
  // 4. 첫 요청: 사례를 보내고, 이전 대화가 없는 새 세션으로 시작했는지 확인합니다.
  pickCase();
  await submit();
  assert.deepEqual(requests[0].history, []);
  // 5. 후속 요청: 같은 사례를 다시 보내도 세션이 유지되고 앞선 대화 두 문장이 포함되는지 확인합니다.
  pickCase();
  await submit();
  assert.equal(requests[1].session_id, 'session-1');
  assert.deepEqual(requests[1].history, [
    {role: 'user', content: '안녕하세요'},
    {role: 'assistant', content: '안녕하세요'},
  ]);
  assert.equal(turns.get('session-1').length, 2);
  assert.equal(element('#state-records-status').textContent, '총 2턴 저장됨');
});
}
