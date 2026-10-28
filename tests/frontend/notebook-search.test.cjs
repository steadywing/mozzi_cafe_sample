const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

/** 선택한 테스트 사진이 미리보기와 실제 검색 요청에 함께 쓰이는지 확인합니다. */
test('선택한 검색 사례의 사진과 요청이 일치합니다', async () => {
  // 1. 화면 준비: 선택창과 입력창, 버튼에 필요한 브라우저 동작을 준비합니다.
  class Element {
    /** 빈 입력값과 이벤트·자식 목록을 가진 테스트용 화면 요소를 만듭니다. */
    constructor() {
      // 1. 요소 준비: 테스트에서 바꿀 값과 이벤트·자식 목록을 초기화합니다.
      this.value = '';
      this.children = [];
      this.events = {};
      this.innerHTML = '';
    }
    /** 이벤트 이름과 실행 함수를 받아 테스트에서 호출할 수 있게 보관합니다. */
    addEventListener(name, fn) {
      // 1. 이벤트 보관: 이벤트 이름으로 실행 함수를 저장합니다.
      this.events[name] = fn;
    }
    /** 전달한 요소를 자식 목록에 추가합니다. */
    append(...items) {
      // 1. 자식 추가: 전달받은 요소를 목록 뒤에 넣습니다.
      this.children.push(...items);
      if (!this.value && items[0]?.value) this.value = items[0].value;
    }
    /** 자식 목록을 전달받은 요소로 교체합니다. */
    replaceChildren(...items) {
      // 1. 자식 교체: 기존 목록 대신 새 요소들을 보관합니다.
      this.children = items;
      this.value = '';
    }
    /** 테스트 화면의 전송 버튼을 돌려줍니다. */
    querySelector() {
      // 1. 버튼 선택: 이 테스트에서 사용하는 전송 버튼을 돌려줍니다.

      return button;
    }
    /** 속성 이름을 받아 테스트 화면에서 해당 속성을 지웁니다. */
    removeAttribute(name) {
      // 1. 속성 삭제: 전달받은 이름의 속성을 요소에서 지웁니다.
      delete this[name];
    }
  }
  const elements = new Map();
  const button = new Element();
  /** 선택자에 해당하는 테스트 화면 요소를 만들거나 기존 요소를 돌려줍니다. */
  const get = (name) => {
    // 1. 요소 선택: 같은 선택자는 같은 객체를 사용합니다.
    if (!elements.has(name)) elements.set(name, new Element());

    return elements.get(name);
  };
  const requests = [];
  const cases = [
    {sample: 'search_cafe_latte.png', title: '카페라떼', expected: '라떼 후보 확인'},
    {sample: 'search_not_food_cat.png', title: '고양이', expected: '음식 후보를 억지로 제시하지 않는지 확인'},
  ];

  // 2. 서버 대체: 사례 목록과 검색 응답을 외부 연결 없이 제공합니다.
  const sandbox = {
    document: {querySelector: get, createElement: () => new Element()},
    NotebookTrace: {getSession: () => 'search-session', render() {}, load: async () => [], clear: async () => {}, newSession: () => 'next-session'},
    /** 요청 주소를 받아 사례 목록 또는 검색 결과를 돌려주고 검색 입력을 기록합니다. */
    fetch: async (url, options) => {
      // 1. 서버 대체: 사례 조회와 실제 검색 요청을 구분하여 기록합니다.
      if (url === '/test/api/search/cases') {

        return {ok: true, json: async () => ({cases})};
      }
      requests.push(JSON.parse(options.body));

      return {ok: true, json: async () => ({state: {answer: {text: '검색 결과'}}, steps: [], elapsed_ms: 10})};
    },
  };
  vm.runInNewContext(readFileSync('static/js/notebook_search.js', 'utf8'), sandbox);
  await new Promise(setImmediate);

  // 3. 사례 선택과 실행: 선택한 사진 주소와 전송된 사진 이름이 같은지 확인합니다.
  get('#sample').value = 'search_not_food_cat.png';
  get('#sample').events.change();
  assert.equal(get('#sample-image').src, '/test/api/search/images/search_not_food_cat.png');
  assert.match(get('#sample-expected').textContent, /음식 후보/);
  get('#chat-input').value = '이 사진을 찾아주세요';
  await get('#chat-form').events.submit({preventDefault() {}});
  assert.equal(requests[0].sample, 'search_not_food_cat.png');
  assert.equal(requests[0].session_id, 'search-session');
});
