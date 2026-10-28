// 이 실습의 이전 상태와 대화는 브라우저에서 다음 요청까지 보관합니다.
const form = document.querySelector('#chat-form');
const input = document.querySelector('#chat-input');
const messages = document.querySelector('#chat-messages');
const flow = document.querySelector('#flow-list');
const status = document.querySelector('#chat-status');
const errorBox = document.querySelector('#chat-error');
const caseButtons = document.querySelectorAll('[data-case]');
let state = {history: []};
let sessionId = NotebookTrace.getSession('order');
const traceHistory = document.querySelector('#trace-history');
NotebookTrace.render(flow, 'order');
NotebookTrace.load('order', sessionId, flow, traceHistory).then((turns) => {
  if (!turns.length) return;
  state = turns[turns.length - 1].state || state;
  state.history = [];
  turns.forEach((turn) => {
    const question = turn.state?.input?.text;
    const answer = turn.state?.answer?.answer || turn.state?.answer?.text;
    if (question) { state.history.push({role: 'user', content: question}); appendMessage('customer', question); }
    if (answer) { state.history.push({role: 'assistant', content: answer}); appendMessage('assistant', answer); }
  });
}).catch(() => {});
let running = false;

/** 말하는 사람과 문장을 받아 화면에 말풍선으로 추가합니다. */
function appendMessage(role, text) {
  // 1. 대화 표시: 문장은 텍스트로 넣어 HTML로 해석되지 않게 합니다.
  messages.querySelector('.chat-welcome')?.remove();
  const item = document.createElement('div');
  item.className = `chat-message ${role}`;
  const label = document.createElement('span');
  label.className = 'message-label';
  label.textContent = role === 'customer' ? '나' : '챗봇';

  // ## 말풍선 본문을 만든 뒤 이름표와 함께 대화 목록에 추가합니다.
  const bubble = document.createElement('p');
  bubble.textContent = text;
  item.append(label, bubble);
  messages.append(item);
  messages.scrollTop = messages.scrollHeight;
}

/** 첫 안내 문구를 받아 새 대화창에 다시 보여줍니다. */
function showWelcome(titleText, noteText) {
  // 1. 안내 구성: 안내 제목과 입력 예시를 공통 시작 화면으로 만듭니다.
  const welcome = document.createElement('div');
  welcome.className = 'chat-welcome';
  const title = document.createElement('strong');
  title.textContent = titleText;
  const note = document.createElement('p');
  note.textContent = noteText;
  welcome.append(title, note);
  messages.replaceChildren(welcome);
}

/** 서버가 반환한 처리 단계를 역할과 실제 입력·상태로 나눠 보여줍니다. */
function showSteps(steps) {
  // 1. 단계 표시: 실제 함수 순서와 단계 후 상태를 오른쪽에 표시합니다.
  NotebookTrace.render(flow, 'order', steps);
}

/** 사례 버튼을 누르면 해당 문장을 입력창에 넣습니다. */
caseButtons.forEach((button) => {
  // 1. 사례 선택: 선택한 예시를 바로 수정하거나 전송할 수 있습니다.
  /** 선택한 사례를 입력창에 넣고 해당 버튼을 강조합니다. */
  button.addEventListener('click', () => {
    // 1. 입력 선택: 다른 사례의 강조를 지우고 선택 문장으로 바꿉니다.
    input.value = button.dataset.case;
    caseButtons.forEach((entry) => entry.setAttribute('aria-pressed', String(entry === button)));
    input.focus();
  });
});

/** 입력창을 직접 수정하면 이전 테스트 사례의 선택 표시를 해제합니다. */
input.addEventListener('input', () => {
  // 1. 선택 해제: 현재 문장이 사례 원문과 달라졌음을 표시합니다.
  caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
});

/** 문장을 서버에 보내고 답변과 처리 흐름을 화면에 표시합니다. */
form.addEventListener('submit', async (event) => {
  // 1. 요청 준비: 이전 상태와 이번 문장을 묶어 같은 대화를 이어갑니다.
  event.preventDefault();
  const text = input.value.trim();
  if (!text || running) {

    return;
  }
  running = true;
  form.querySelector('button').disabled = true;
  errorBox.hidden = true;
  status.textContent = '처리하고 있습니다…';
  const request = {...state, session_id: sessionId, input: {text, has_image: false}};

  try {
    // 2. 처리 실행: 결과가 성공한 경우에만 대화와 다음 요청 상태를 갱신합니다.
    const response = await fetch('/chatbot/order/practice', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '처리하지 못했습니다.');

    // ## 응답 상태와 대화 기록을 다음 요청에 사용할 값으로 갱신합니다.
    state = result.state;
    const answer = state.answer?.answer || state.answer?.text || '';
    state.history = [...(state.history || []), {role: 'user', content: text}];
    if (answer) state.history.push({role: 'assistant', content: answer});
    appendMessage('customer', text);
    if (answer) appendMessage('assistant', answer);

    // ## 처리 단계와 전체 요청·응답을 검사 화면에 남깁니다.
    showSteps(result.steps);
    await NotebookTrace.load('order', sessionId, flow, traceHistory).catch(() => {});
    document.querySelector('#request-json').textContent = JSON.stringify(request, null, 2);
    document.querySelector('#response-json').textContent = JSON.stringify(result, null, 2);
    document.querySelector('#flow-status').textContent = `처리 완료 · ${result.elapsed_ms} ms`;
    status.textContent = '';
    input.value = '';
    caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
  } catch (error) {
    // 3. 실패 안내: 입력을 유지해 다시 시도하도록 오류를 보여줍니다.
    errorBox.textContent = error.message || '서버에 연결할 수 없습니다.';
    errorBox.hidden = false;
    status.textContent = '다시 시도해 주세요.';
    document.querySelector('#flow-status').textContent = '이번 턴을 처리하지 못했습니다.';
  } finally {
    // 4. 입력 복구: 처리가 끝나면 다음 문장을 입력할 수 있습니다.
    running = false;
    form.querySelector('button').disabled = false;
    input.focus();
  }
});

/** 새 대화를 시작하면 이 브라우저에서 보관한 상태와 화면을 비웁니다. */
document.querySelector('#reset-chat').addEventListener('click', async () => {
  // 1. 상태 초기화: 진행 중인 요청은 유지하고 완료 후 새 대화를 시작합니다.
  if (running) {

    return;
  }
  await NotebookTrace.clear('order', sessionId);
  sessionId = NotebookTrace.newSession('order');
  state = {history: []};
  showWelcome('무엇을 도와드릴까요?', '주문할 메뉴와 수량을 입력해 주세요.');
  NotebookTrace.render(flow, 'order');
  traceHistory.replaceChildren();
  input.value = '';
  caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
  errorBox.hidden = true;
  status.textContent = '';
  document.querySelector('#flow-status').textContent = '메시지를 보내면 결과가 표시됩니다.';
  document.querySelector('#request-json').textContent = '';
  document.querySelector('#response-json').textContent = '';
});


