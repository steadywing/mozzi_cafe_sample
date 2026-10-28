const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

/** 실습 이름과 스크립트를 받아 사례 선택과 대화 안내 동작을 확인합니다. */
for (const practice of ['unknown', 'order']) {
  /** 해당 실습에서 사례를 선택·수정·전송·초기화할 때 화면 표시를 확인합니다. */
  test(`${practice} 사례와 첫 안내 표시`, async () => {
    // 1. 화면 준비: 클릭과 입력, 대화 요소의 자식 목록을 기록합니다.
    class Element {
      /** 태그 이름을 받아 테스트에서 사용할 화면 상태를 만듭니다. */
      constructor(tag = 'div') {
        // 1. 상태 준비: 요소 종류와 이벤트·선택 상태를 기록할 공간을 만듭니다.
        this.tag = tag;
        this.children = [];
        this.events = {};
        this.attributes = {};
        this.value = '';
        this.textContent = '';
        this.dataset = {};
      }
      /** 이벤트 이름과 실행 함수를 받아 클릭·입력 동작에 보관합니다. */
      addEventListener(name, handler) {
        // 1. 동작 보관: 테스트에서 해당 이벤트를 직접 실행할 수 있게 합니다.
        this.events[name] = handler;
      }
      /** 자식 요소를 받아 대화 목록에 추가합니다. */
      append(...items) {
        // 1. 자식 추가: 부모와 순서를 함께 기록합니다.
        items.forEach((item) => { item.parent = this; this.children.push(item); });
      }
      /** 자식 요소를 받아 기존 대화 목록을 교체합니다. */
      replaceChildren(...items) {
        // 1. 목록 교체: 이전 자식을 지운 뒤 새 요소를 넣습니다.
        this.children = [];
        this.append(...items);
      }
      /** 속성 이름과 값을 받아 사례의 선택 상태를 기록합니다. */
      setAttribute(name, value) {
        // 1. 속성 저장: 사례 버튼의 선택 여부를 나중에 확인합니다.
        this.attributes[name] = value;
      }
      /** 선택자에 맞는 첫 자식 요소를 돌려줍니다. */
      querySelector(selector) {
        // 1. 요소 선택: 전송 버튼이나 첫 안내를 찾아 돌려줍니다.
        if (selector === 'button') return new Element('button');

        return this.children.find((item) => item.className === selector.slice(1)) || null;
      }
      /** 현재 요소를 부모의 자식 목록에서 지웁니다. */
      remove() {
        // 1. 안내 제거: 첫 실제 말풍선이 들어오면 기존 안내를 지웁니다.
        this.parent.children = this.parent.children.filter((item) => item !== this);
      }
      /** 입력창의 초점 이동 요청을 받아 테스트를 이어갑니다. */
      focus() {
        // 1. 초점 수용: 입력창의 실제 브라우저 동작은 생략합니다.
      }
    }
    const elements = new Map();
    const cases = [new Element('button'), new Element('button')];
    cases[0].dataset.case = '첫 사례';
    cases[1].dataset.case = '둘째 사례';
    /** 선택자를 받아 같은 화면 요소를 돌려줍니다. */
    const element = (selector) => {
      // 1. 화면 선택: 같은 선택자는 같은 요소를 사용합니다.
      if (!elements.has(selector)) elements.set(selector, new Element());

      return elements.get(selector);
    };
    const welcome = new Element();
    welcome.className = 'chat-welcome';
    element('#chat-messages').append(welcome);
    const trace = {
      /** 실습 이름을 받아 현재 테스트 세션을 돌려줍니다. */
      getSession: () => 'test-session',
      /** 실습의 처리 단계를 받아 화면 렌더링 요청을 받아줍니다. */
      render: () => {},
      /** 저장 기록 요청을 받아 빈 턴 목록을 돌려줍니다. */
      load: async () => [],
      /** 현재 세션 삭제 요청을 받아 초기화를 이어갑니다. */
      clear: async () => {},
      /** 실습 이름을 받아 새 테스트 세션을 돌려줍니다. */
      newSession: () => 'next-session',
    };
    const sandbox = {
      document: {querySelector: element, querySelectorAll: () => cases, createElement: (tag) => new Element(tag)},
      NotebookTrace: trace,
      /** 입력 문장을 받아 확인 답변을 포함한 테스트 결과를 돌려줍니다. */
      fetch: async () => ({ok: true, json: async () => ({state: {answer: {answer: '확인 답변'}, history: []}, steps: [], elapsed_ms: 10})}),
    };
    vm.runInNewContext(readFileSync(`static/js/notebook_${practice}.js`, 'utf8'), sandbox);
    await new Promise(setImmediate);

    // 2. 사례 선택: 버튼을 고른 뒤 직접 문장을 고치면 선택 표시가 해제되는지 확인합니다.
    cases[0].events.click();
    assert.equal(element('#chat-input').value, '첫 사례');
    assert.equal(cases[0].attributes['aria-pressed'], 'true');
    assert.equal(cases[1].attributes['aria-pressed'], 'false');
    element('#chat-input').events.input();
    assert.equal(cases[0].attributes['aria-pressed'], 'false');

    // 3. 메시지 전송: 답변을 표시할 때 첫 안내와 사례 선택 표시가 사라지는지 확인합니다.
    cases[1].events.click();
    await element('#chat-form').events.submit({preventDefault() {}});
    assert.equal(element('#chat-messages').children.some((item) => item.className === 'chat-welcome'), false);
    assert.equal(cases[1].attributes['aria-pressed'], 'false');

    // 4. 대화 초기화: 새 대화를 시작하면 첫 안내와 미선택 상태로 돌아가는지 확인합니다.
    cases[0].events.click();
    await element('#reset-chat').events.click();
    assert.equal(element('#chat-messages').children[0].className, 'chat-welcome');
    assert.equal(cases[0].attributes['aria-pressed'], 'false');
  });
}
