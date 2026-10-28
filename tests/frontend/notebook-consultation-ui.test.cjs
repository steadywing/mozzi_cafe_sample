const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

/** 문의 사례를 선택하고 입력을 수정하거나 전송·초기화할 때 선택 표시가 맞게 바뀌는지 확인합니다. */
test('문의 사례 선택 표시는 직접 수정·전송·새 대화에서 해제됩니다', async () => {
  // 1. 화면 준비: 사례 버튼과 문의 화면의 입력 요소를 가상 화면에 만듭니다.
  class Element {
    /** 화면 요소를 만들면 입력값과 이벤트·속성 저장소를 준비합니다. */
    constructor() {
      // 1. 초기 상태: 사례 표시와 입력 내용을 확인할 값을 보관합니다.
      this.value = '';
      this.textContent = '';
      this.innerHTML = '';
      this.events = {};
      this.attributes = {};
      this.children = [];
      this.disabled = false;
      this.dataset = {};
    }
    /** 이벤트 이름과 함수를 받으면 나중에 호출할 수 있게 저장합니다. */
    addEventListener(name, callback) {
      // 1. 이벤트 저장: 테스트에서 클릭과 전송을 직접 실행할 수 있게 합니다.
      this.events[name] = callback;
    }
    /** 속성 이름과 값을 받으면 선택 표시 상태를 저장합니다. */
    setAttribute(name, value) {
      // 1. 속성 저장: 사례 버튼의 aria-pressed 값을 확인합니다.
      this.attributes[name] = value;
    }
    /** 자식 요소를 받으면 화면 목록에 추가합니다. */
    append(...items) {
      // 1. 자식 추가: 대화 말풍선을 화면 목록에 넣습니다.
      this.children.push(...items);
    }
    /** 자식 목록을 비우면 이전 처리 기록을 지웁니다. */
    replaceChildren() {
      // 1. 목록 초기화: 새 대화에서 이전 처리 기록을 비웁니다.
      this.children = [];
    }
    /** 요소를 찾으면 대화창의 첫 안내를 지울 대상을 돌려줍니다. */
    querySelector(selector) {
      // 1. 자식 조회: 전송 버튼과 첫 안내 삭제 호출을 지원합니다.
      if (selector === 'button') return submitButton;

      return {remove() {}};
    }
    /** 입력창에 초점을 요청하면 테스트에서는 값만 그대로 둡니다. */
    focus() {
      // 1. 초점 수용: 가상 화면에서 브라우저 초점 이동을 생략합니다.
    }
  }
  const elements = new Map();
  const submitButton = new Element();
  const caseButtons = [new Element(), new Element()];
  caseButtons[0].dataset.case = '주말 영업시간';
  caseButtons[1].dataset.case = '알레르기 정보';
  /** 선택자를 받으면 같은 화면 요소를 계속 돌려줍니다. */
  const element = selector => {
    // 1. 요소 조회: 입력과 상태가 이벤트 사이에 유지되게 합니다.
    if (!elements.has(selector)) elements.set(selector, new Element());

    return elements.get(selector);
  };
  const sandbox = {
    document: {
      querySelector: element,
      querySelectorAll: () => caseButtons,
      createElement: () => new Element(),
    },
    NotebookTrace: {
      getSession: () => 'session-1',
      render() {},
      load: async () => [],
      clear: async () => {},
      newSession: () => 'session-2',
    },
    fetch: async () => ({ok: true, json: async () => ({state: {answer: {text: '안내입니다.'}}, steps: [], elapsed_ms: 1})}),
  };

  // 2. 사례 선택: 선택한 버튼만 강조되고 입력창에는 해당 문장이 들어갑니다.
  vm.runInNewContext(readFileSync('static/js/notebook_consultation.js', 'utf8'), sandbox);
  caseButtons[0].events.click();
  assert.equal(element('#input').value, '주말 영업시간');
  assert.equal(caseButtons[0].attributes['aria-pressed'], 'true');
  assert.equal(caseButtons[1].attributes['aria-pressed'], 'false');
  caseButtons[1].events.click();
  assert.equal(caseButtons[0].attributes['aria-pressed'], 'false');
  assert.equal(caseButtons[1].attributes['aria-pressed'], 'true');

  // 3. 직접 수정: 사례 문장을 고치면 선택 표시를 해제하고 다시 선택할 수 있습니다.
  element('#input').value = '직접 수정한 질문';
  element('#input').events.input();
  assert.equal(caseButtons[1].attributes['aria-pressed'], 'false');
  caseButtons[1].events.click();

  // 4. 전송과 초기화: 사례를 처리하거나 새 대화를 시작하면 강조가 사라집니다.
  await element('#form').events.submit({preventDefault() {}});
  assert.equal(caseButtons[1].attributes['aria-pressed'], 'false');
  assert.equal(element('#flow-status').textContent, '처리 완료 · 1 ms');
  assert.equal(element('#status').textContent, '');
  caseButtons[0].events.click();
  await element('#reset').events.click();
  assert.equal(caseButtons[0].attributes['aria-pressed'], 'false');
  assert.equal(element('#flow-status').textContent, '질문을 보내면 각 단계의 입력과 결과가 표시됩니다.');
});
