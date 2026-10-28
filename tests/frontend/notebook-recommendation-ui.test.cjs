const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

/** 추천 사례를 선택하고 전송·초기화할 때 강조와 시작 안내가 바뀌는지 확인합니다. */
test('추천 사례 선택과 대화 안내를 일관되게 표시합니다', async () => {
  // 1. 화면 준비: 버튼 선택과 대화창 변경을 기록할 요소를 만듭니다.
  class Element {
    /** 테스트에서 사용할 값과 자식 요소·이벤트·속성을 비워 둡니다. */
    constructor() {
      // 1. 요소 초기화: 화면에서 바뀌는 값을 테스트가 읽을 수 있게 보관합니다.
      this.value = '';
      this.children = [];
      this.events = {};
      this.attributes = {};
      this.hidden = false;
      this.removed = false;
    }
    /** 이벤트 종류와 함수를 받아 나중에 직접 호출할 수 있게 보관합니다. */
    addEventListener(type, handler) {
      // 1. 이벤트 보관: 클릭·입력·전송·초기화 함수를 이름별로 기록합니다.
      this.events[type] = handler;
    }
    /** 속성 이름과 값을 받아 선택 표시 상태를 기록합니다. */
    setAttribute(name, value) {
      // 1. 속성 보관: 버튼의 선택 여부를 다음 확인에서 읽습니다.
      this.attributes[name] = value;
    }
    /** 화면 요소를 받아 대화창의 자식 목록에 추가합니다. */
    append(...items) {
      // 1. 목록 추가: 새 안내나 말풍선을 현재 대화 뒤에 붙입니다.
      this.children.push(...items);
    }
    /** 화면 요소를 받아 대화창의 기존 자식을 교체합니다. */
    replaceChildren(...items) {
      // 1. 목록 교체: 새 대화의 이전 말풍선을 지웁니다.
      this.children = items;
    }
    /** 입력창 초점 이동을 받아 테스트에서 호출 오류를 막습니다. */
    focus() {
      // 1. 초점 수용: 실제 브라우저 초점은 만들지 않습니다.
    }
    /** 안내 요소를 삭제했다고 표시합니다. */
    remove() {
      // 1. 삭제 기록: 첫 말풍선 전에 기존 안내가 지워졌는지 확인합니다.
      this.removed = true;
    }
    /** 전송 폼에서 사용할 버튼을 돌려줍니다. */
    querySelector() {
      // 1. 버튼 반환: 전송 중 잠금에 쓰는 버튼을 제공합니다.

      return sendButton;
    }
  }
  const elements = new Map();
  const caseButtons = [new Element(), new Element()];
  const sendButton = new Element();
  /** 선택자에 맞는 요소를 만들어 보관하거나 이전 요소를 돌려줍니다. */
  const element = (selector) => {
    // 1. 요소 조회: 같은 선택자는 같은 요소를 사용합니다.
    if (!elements.has(selector)) elements.set(selector, new Element());

    return elements.get(selector);
  };
  caseButtons[0].dataset = {case: '상큼한 메뉴가 좋아요'};
  caseButtons[1].dataset = {case: '알레르기는 없어요'};

  // 2. 처리 대체: 화면 코드를 실행하되 서버와 저장소는 고정 결과를 돌려줍니다.
  const sandbox = {
    document: {
      querySelector: element,
      querySelectorAll: () => caseButtons,
      createElement: () => new Element(),
    },
    NotebookTrace: {
      getSession: () => 'first-session',
      newSession: () => 'next-session',
      render() {},
      load: async () => [],
      clear: async () => {},
    },
    /** 추천 입력을 받으면 검사에 쓸 답변과 실행 기록을 돌려줍니다. */
    fetch: async () => ({ok: true, json: async () => ({state: {answer: {text: '추천 결과'}}, steps: [], elapsed_ms: 10})}),
  };
  vm.runInNewContext(readFileSync('static/js/notebook_recommendation.js', 'utf8'), sandbox);

  // 3. 선택 확인: 한 사례를 누르면 다른 사례의 강조가 해제됩니다.
  caseButtons[0].events.click();
  assert.equal(caseButtons[0].attributes['aria-pressed'], 'true');
  caseButtons[1].events.click();
  assert.equal(caseButtons[0].attributes['aria-pressed'], 'false');
  assert.equal(caseButtons[1].attributes['aria-pressed'], 'true');

  // 4. 실행 확인: 첫 답변 앞에서 시작 안내를 지우고 선택 표시를 해제합니다.
  await element('#chat-form').events.submit({preventDefault() {}});
  assert.equal(element('#chat-welcome').removed, true);
  assert.equal(caseButtons[1].attributes['aria-pressed'], 'false');

  // 5. 초기화 확인: 새 대화에는 말풍선 대신 시작 안내가 다시 나타납니다.
  await element('#reset-chat').events.click();
  assert.equal(element('#chat-messages').children[0].className, 'chat-welcome');
});
