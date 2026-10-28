const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

/** 영수증 확인 뒤 잘못된 포인트를 고쳐 다시 적립할 수 있는지 확인합니다. */
test('잘못된 포인트를 수정하고 다시 확인합니다', async () => {
  // 1. 화면 준비: 스크립트에서 사용하는 요소와 요청을 대체합니다.
  class Element {
    /** 이벤트와 값을 보관할 화면 요소를 만듭니다. */
    constructor() {
      // 1. 요소 준비: 테스트에서 바꿀 값과 이벤트·자식 목록을 초기화합니다.
      this.value = '';
      this.children = [];
      this.events = {};
      this.disabled = false;
      this.textContent = '';
    }
    /** 이벤트 이름과 실행 함수를 보관합니다. */
    addEventListener(name, callback) {
      // 1. 이벤트 보관: 이벤트 이름으로 실행 함수를 저장합니다.
      this.events[name] = callback;
    }
    /** 자식 요소를 뒤에 추가합니다. */
    append(...items) {
      // 1. 자식 추가: 전달받은 요소를 목록 뒤에 넣습니다.
      this.children.push(...items);
    }
    /** 기존 자식 요소를 교체합니다. */
    replaceChildren(...items) {
      // 1. 자식 교체: 기존 목록 대신 새 요소들을 보관합니다.
      this.children = items;
    }
  }
  const elements = new Map();
  /** 선택자에 해당하는 화면 요소를 돌려줍니다. */
  const element = selector => {
    // 1. 요소 선택: 같은 선택자는 같은 객체를 사용합니다.
    if (!elements.has(selector)) elements.set(selector, new Element());

    return elements.get(selector);
  };
  const requests = [];
  const sandbox = {
    document: {querySelector: element, createElement: () => new Element()},
    crypto: {randomUUID: () => 'test-session'},
    NotebookTrace: {getSession: () => 'test-session', render() {}, load: async () => [], clear: async () => {}, newSession: () => 'next-session'},
    /** 판독과 적립 요청에 맞는 대체 응답을 돌려줍니다. */
    fetch: async (url, options) => {
      // 1. 요청 기록: 판독 성공과 적립 성공을 각각 반환합니다.
      if (url === '/test/api/points/cases') {

        return {ok: true, json: async () => ({cases: [
        {sample: 'mochi-receipt-01', title: '회원 주문과 일치', customer_id: 'cust_001', expected: '주문 일치', image_url: '/test/api/points/samples/mochi-receipt-01'},
        {sample: 'mochi-receipt-03', title: '다른 회원의 주문', customer_id: 'cust_005', expected: '주문 일치', image_url: '/test/api/points/samples/mochi-receipt-03'},
        ]})};
      }
      requests.push({url, options});
      const receipt = {verification: 'passed', status: url.endsWith('/confirm') ? 'completed' : 'pending'};

      return {ok: true, json: async () => ({state: {receipt, answer: {text: '확인했습니다.'}}, steps: [], elapsed_ms: 12.5})};
    },
  };
  vm.runInNewContext(readFileSync('static/js/notebook_points.js', 'utf8'), sandbox);
  await new Promise(setImmediate);

  // 2. 사례 선택: 미리보는 영수증과 고객이 실제 판독 요청에 함께 들어갑니다.
  element('#sample').value = 'mochi-receipt-03';
  element('#sample').events.change();
  assert.equal(element('#receipt-image').src, '/test/api/points/samples/mochi-receipt-03');
  assert.equal(element('#customer').value, 'cust_005');

  // 3. 잘못된 입력: 서버에 적립을 요청하지 않고 수정할 수 있어야 합니다.
  await element('#start').events.click();
  assert.equal(JSON.parse(requests[0].options.body).sample, 'mochi-receipt-03');
  assert.equal(JSON.parse(requests[0].options.body).customer_id, 'cust_005');
  assert.equal(element('#flow-status').textContent, '처리 완료 · 12.5 ms');
  element('#points').value = '0';
  await element('#confirm').events.click();
  assert.equal(requests.length, 1);
  assert.equal(element('#confirm').disabled, false);
  assert.match(element('#status').textContent, /양의 정수/);

  // 4. 수정 후 확인: 정상 포인트로 같은 영수증을 다시 판독하지 않고 적립합니다.
  element('#points').value = '100';
  await element('#confirm').events.click();
  assert.equal(requests.length, 2);
  assert.equal(requests[1].url, '/chatbot/points/confirm');
  assert.equal(element('#confirm').disabled, true);
  assert.match(element('#status').textContent, /새 대화/);
  assert.equal(element('#flow-status').textContent, '처리 완료 · 12.5 ms');

  // 5. 기록 초기화: 새 대화는 서버의 적립 세션과 단계 기록을 함께 지웁니다.
  await element('#reset').events.click();
  assert.equal(requests[2].url, '/chatbot/points/test-session');
  assert.equal(requests[2].options.method, 'DELETE');
  assert.equal(element('#flow-status').textContent, '영수증을 확인하면 단계별 결과가 표시됩니다.');
});
