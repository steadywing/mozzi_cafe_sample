const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

/** 저장된 두 턴을 조회해 함수별 실제 입력과 상태를 분리해 표시하는지 확인합니다. */
test('실행 흐름과 이전 턴 기록을 복원합니다', async () => {
  // 1. 화면 준비: 브라우저 요소와 세션 저장소를 작은 객체로 대체합니다.
  class Element {
    /** 이름을 받아 텍스트와 자식 목록을 보관할 요소를 만듭니다. */
    constructor(name = 'div') {
      // 1. 요소 준비: 렌더러가 바꿀 제목과 자식 목록을 보관합니다.
      this.name = name;
      this.children = [];
      this.textContent = '';
    }
    /** 자식 요소를 받아 현재 목록 뒤에 추가합니다. */
    append(...children) {
      // 1. 목록 추가: 받은 자식을 차례대로 기록합니다.
      this.children.push(...children);
    }
    /** 자식 요소를 받아 기존 목록 대신 보관합니다. */
    replaceChildren(...children) {
      // 1. 목록 교체: 화면을 다시 그릴 때 이전 자식을 지웁니다.
      this.children = children;
    }
  }
  const session = new Map();
  const sandbox = {
    window: {}, document: {createElement: (name) => new Element(name)},
    crypto: {randomUUID: () => 'new-session'},
    sessionStorage: {getItem: (key) => session.get(key), setItem: (key, value) => session.set(key, value)},
    /** 저장된 단계 두 개를 현재 실습 세션의 응답으로 돌려줍니다. */
    fetch: async () => ({ok: true, json: async () => ({turns: [
      {turn_index: 1, steps: [{step: 'generate_unknown_response', input: [{role: 'user', content: '첫 질문'}], prompt: '첫 프롬프트', model: 'test-model', state: {answer: {answer: '첫 답변'}}}]},
      {turn_index: 2, steps: [{step: 'generate_unknown_response', input: [{role: 'user', content: '둘째 질문'}], prompt: '둘째 프롬프트', model: 'test-model', state: {answer: {answer: '둘째 답변'}}}]},
    ]})}),
  };
  vm.runInNewContext(readFileSync('static/js/notebook_trace.js', 'utf8'), sandbox);
  const trace = sandbox.window.NotebookTrace;
  const current = new Element();
  const history = new Element();

  // 2. 기록 조회: 같은 세션 ID로 저장한 최신 단계와 이전 단계를 화면에 놓습니다.
  assert.equal(trace.getSession('unknown'), 'new-session');
  await trace.load('unknown', 'new-session', current, history);
  const row = current.children[0].children[0];
  const heading = row.children[0];
  const details = row.children.slice(2);

  // 3. 결과 확인: 함수명, 짧은 답변, 실제 입력·프롬프트·상태가 분리됩니다.
  assert.equal(heading.children[1].textContent, '범위 밖 질문 답변');
  assert.equal(heading.children[2].textContent, 'generate_unknown_response');
  assert.equal(row.children[1].textContent, '둘째 답변');
  assert.deepEqual(Array.from(details, (item) => item.children[0].textContent), ['실제 모델 입력', '사용 프롬프트', '사용 모델', '단계 후 저장 상태']);
  assert.equal(history.children[0].children[0].textContent, '1번째 턴 · 1단계');

  // 4. 기존 주문 화면: 실행 전 함수 순서와 실행 후 주문 결과를 같은 형식으로 표시합니다.
  const order = new Element();
  trace.render(order, 'legacy_order');
  assert.equal(order.children[0].children.length, 5);
  trace.render(order, 'legacy_order', [{step: 'create_order_draft', state: {order: {items: [{product_name: '라떼'}]}}}]);
  assert.equal(order.children[0].children[0].children[1].textContent, '주문 항목 1개를 추출했습니다.');
});
