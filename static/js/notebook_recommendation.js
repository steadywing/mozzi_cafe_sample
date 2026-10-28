// 추천 조건은 이 화면의 대화 상태에 보관하고 새 대화에서 초기화합니다.
const form = document.querySelector('#chat-form');
const input = document.querySelector('#chat-input');
const messages = document.querySelector('#chat-messages');
const steps = document.querySelector('#flow-steps');
const traceHistory = document.querySelector('#trace-history');
let sessionId = NotebookTrace.getSession('recommendation');
NotebookTrace.render(steps, 'recommendation');
NotebookTrace.load('recommendation', sessionId, steps, traceHistory).then((turns) => {
  if (turns.length) state = turns[turns.length - 1].state || state;
}).catch(() => {});
const status = document.querySelector('#chat-status');
const errorBox = document.querySelector('#chat-error');
const caseButtons = document.querySelectorAll('[data-case]');
let state = {};
let running = false;

/** 새 대화를 시작하면 메뉴 추천 안내를 대화창 가운데 다시 보여줍니다. */
function showWelcome() {
  // 1. 안내 구성: 처음 화면과 같은 제목과 설명을 만듭니다.
  const welcome = document.createElement('div');
  welcome.id = 'chat-welcome';
  welcome.className = 'chat-welcome';
  const title = document.createElement('strong');
  title.textContent = '어떤 메뉴를 찾고 계신가요?';
  const note = document.createElement('p');
  note.textContent = '알레르기나 선호를 알려주시면 메뉴를 추천합니다.';
  welcome.append(title, note);

  // 2. 안내 표시: 이전 대화 대신 새 안내를 놓습니다.
  messages.replaceChildren(welcome);
}

/** 말하는 사람과 문장을 받아 대화 영역에 표시합니다. */
function appendMessage(role, text) {
  // 1. 시작 안내 정리: 첫 말풍선을 넣기 전에 안내 문구를 지웁니다.
  document.querySelector('#chat-welcome')?.remove?.();

  // 2. 대화 표시: 입력을 텍스트로 넣어 화면에 안전하게 보여줍니다.
  const message = document.createElement('div');
  message.className = `chat-message ${role}`;
  const label = document.createElement('span');
  label.className = 'message-label';
  label.textContent = role === 'customer' ? '나' : '챗봇';

  // ## 말풍선 본문을 만든 뒤 이름표와 함께 대화 목록에 추가합니다.
  const bubble = document.createElement('p');
  bubble.textContent = text;
  message.append(label, bubble);
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
}

/** 서버가 반환한 추천 처리 단계를 실제 입력·프롬프트·상태로 표시합니다. */
function showSteps(data) {
  // 1. 단계 표시: 단계별 결과를 갱신하고 이전 턴은 별도 목록에 보존합니다.
  NotebookTrace.render(steps, 'recommendation', data.steps);
  document.querySelector('#flow-status').textContent = `처리 시간 ${data.elapsed_ms} ms`;
}

/** 예시 버튼의 문장을 입력창에 넣어 보낼 수 있게 합니다. */
caseButtons.forEach((button) => {
  // 1. 사례 연결: 버튼을 누르면 문장을 넣고 선택한 사례만 강조합니다.
  button.setAttribute('aria-pressed', 'false');
  /** 추천 사례를 선택하면 문장을 입력창에 넣고 선택한 버튼을 표시합니다. */
  button.addEventListener('click', () => {
    // 1. 입력 선택: 선택한 사례의 문장을 이번 요청에 사용합니다.
    input.value = button.dataset.case;
    caseButtons.forEach((entry) => entry.setAttribute('aria-pressed', String(entry === button)));
    input.focus();
  });
});

/** 사례 문장을 직접 고치면 선택 강조를 해제합니다. */
input.addEventListener('input', () => {
  // 1. 선택 해제: 편집한 문장이 원래 사례와 다름을 버튼에 반영합니다.
  caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
});

/** 입력을 서버에 보내고 추천 조건과 답변을 현재 대화에 반영합니다. */
form.addEventListener('submit', async (event) => {
  // 1. 요청 준비: 이전 추천 상태를 유지하고 이번 문장을 바꿉니다.
  event.preventDefault();
  const text = input.value.trim();
  if (!text || running) {

    return;
  }
  running = true;
  form.querySelector('button').disabled = true;
  status.textContent = '추천 조건을 확인하고 있습니다…';
  errorBox.hidden = true;
  try {
    // 2. 처리 요청: 성공 시 응답 상태와 실제 처리 단계를 함께 표시합니다.
    const response = await fetch('/chatbot/recommendation', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...state, session_id: sessionId, input: {text, has_image: false}})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '추천을 실행하지 못했습니다.');
    state = data.state;
    appendMessage('customer', text);
    appendMessage('notice', state.answer.text);
    showSteps(data);
    await NotebookTrace.load('recommendation', sessionId, steps, traceHistory).catch(() => {});
    input.value = '';
    caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
    status.textContent = '';
  } catch (error) {
    // 3. 실패 안내: 입력을 유지해 다시 보낼 수 있게 합니다.
    errorBox.textContent = error.message;
    errorBox.hidden = false;
    status.textContent = '';
  } finally {
    // ## 요청 처리가 끝나면 입력 잠금과 실행 중 표시를 해제합니다.
    running = false;
    form.querySelector('button').disabled = false;
  }
});

/** 새 대화를 시작하면 이전 추천 조건과 화면 결과를 비웁니다. */
document.querySelector('#reset-chat').addEventListener('click', async () => {
  // 1. 상태 초기화: 처리 중에는 상태를 바꾸지 않습니다.
  if (running) {

    return;
  }
  await NotebookTrace.clear('recommendation', sessionId);
  sessionId = NotebookTrace.newSession('recommendation');
  state = {};
  showWelcome();
  NotebookTrace.render(steps, 'recommendation');
  traceHistory.replaceChildren();
  document.querySelector('#flow-status').textContent = '메시지를 보내면 결과가 표시됩니다.';
  errorBox.hidden = true;
  status.textContent = '';
  input.value = '';
  caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
});
