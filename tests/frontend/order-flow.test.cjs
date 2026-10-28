const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

/** 파일에 저장된 주문 단계 두 턴을 현재 흐름과 이전 기록으로 보여주는지 확인합니다. */
test('기존 상품 주문의 단계와 이전 턴을 표시합니다', async () => {
  // 1. 화면 준비: 주문 화면이 쓰는 요소와 이벤트만 메모리 객체로 대체합니다.
  class Element {
    /** 입력값과 자식 목록을 가진 화면 요소를 만듭니다. */
    constructor() {
      // 1. 요소 준비: 렌더 결과와 선택값을 저장합니다.
      this.children = [];
      this.events = {};
      this.value = '';
      this.options = this.children;
    }
    /** 화면 이벤트를 받아 테스트에서 호출할 수 있게 보관합니다. */
    addEventListener(name, callback) {
      // 1. 이벤트 보관: 이벤트 종류에 따라 함수를 기록합니다.
      this.events[name] = callback;
    }
    /** 자식을 받아 화면 요소의 목록에 추가합니다. */
    append(...items) {
      // 1. 자식 추가: 현재 목록 뒤에 요소를 둡니다.
      this.children.push(...items);
    }
    /** 자식을 받아 기존 목록을 교체합니다. */
    replaceChildren(...items) {
      // 1. 목록 교체: 새로 표시할 요소만 남깁니다.
      this.children = items;
      this.options = this.children;
    }
    /** 고객 선택값을 받아 선택 목록에 추가합니다. */
    add(item) {
      // 1. 고객 추가: 첫 고객은 기본 선택값으로 둡니다.
      this.children.push(item);
      if (!this.value) this.value = item.value;
    }
    /** 사례 버튼이 없는 테스트 화면에서 빈 목록을 돌려줍니다. */
    querySelectorAll() {
      // 1. 빈 사례: 단계 표시와 무관한 사례 버튼은 만들지 않습니다.

      return [];
    }
  }
  const elements = new Map();
  const get = (selector) => {
    if (!elements.has(selector)) elements.set(selector, new Element());

    return elements.get(selector);
  };
  const turns = [
    {elapsed_ms: 10, steps: [{step: 'input', state: {input: {text: '라떼 한 잔'}}}, {step: 'response', state: {input: {text: '라떼 한 잔'}, answer: {answer: '온도를 알려주세요.'}}}]},
    {elapsed_ms: 12, steps: [{step: 'create_order_draft', state: {order: {items: [{product_name: '라떼'}]}}}, {step: 'check_order', state: {answer: {answer: '이대로 주문할까요?'}}}]},
  ];
  const sandbox = {
    window: {}, document: {body: {dataset: {}}, querySelector: get, createElement: () => new Element()},
    URLSearchParams, sessionStorage: {getItem: () => null, setItem() {}, removeItem() {}},
    Option: class { constructor(label, value) { this.textContent = label; this.value = value; } },
    /** 화면 준비 요청과 저장된 주문 턴 조회를 파일 대신 메모리에서 돌려줍니다. */
    fetch: async (url) => {
      // 1. 응답 선택: 고객·사례·프롬프트·단계 기록에 맞는 값을 돌려줍니다.
      if (url === '/test/api/customers') return {ok: true, json: async () => ({customers: [{name: '고객', customer_id: 'cust_001'}]})};
      if (url === '/test/api/order/cases') return {ok: true, json: async () => ({cases: []})};
      if (url === '/test/api/order/prompts') return {ok: true, json: async () => ({persona: {content: '성격'}, order: {content: '주문 지침'}})};
      if (url.startsWith('/test/api/states?')) return {ok: true, json: async () => ({states: turns})};
      throw new Error(`예상하지 못한 요청: ${url}`);
    },
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(readFileSync('static/js/notebook_trace.js', 'utf8'), context);
  context.NotebookTrace = context.window.NotebookTrace;
  vm.runInContext(readFileSync('static/js/intent-test.js', 'utf8'), context);

  // 2. 단계 조회: 현재 주문 세션의 두 턴을 저장 API에서 읽습니다.
  await vm.runInContext('loadStateRecords("cust_001", "session-a")', context);

  // 3. 결과 확인: 최근 턴 단계와 턴별 저장 목록이 따로 표시됩니다.
  assert.equal(get('#flow-current').children[0].children.length, 2);
  assert.equal(get('#flow-current').children[0].children[0].children[1].textContent, '주문 항목 1개를 추출했습니다.');
  assert.equal(get('#state-records').children.length, 2);
  assert.equal(get('#state-records').children[0].children[0].textContent, '1번째 턴 · 10 ms');
  assert.equal(get('#state-records-status').textContent, '총 2턴 저장됨');
});
