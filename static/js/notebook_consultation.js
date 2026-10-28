// 이 화면의 대화는 브라우저에서 유지하고 매 질문에 함께 전달합니다.
const form = document.querySelector('#form');
const input = document.querySelector('#input');
const messages = document.querySelector('#messages');
const status = document.querySelector('#status');
const flowStatus = document.querySelector('#flow-status');
const steps = document.querySelector('#steps');
const initialMessages = messages.innerHTML;
const traceHistory = document.querySelector('#trace-history');
let sessionId = NotebookTrace.getSession('consultation');
NotebookTrace.render(steps, 'consultation');
NotebookTrace.load('consultation', sessionId, steps, traceHistory).then((turns) => {
  turns.forEach((turn) => {
    const question = turn.state?.input?.text;
    const answer = turn.state?.answer?.text;
    if (question) { history.push({role: 'user', content: question}); addMessage('customer', question); }
    if (answer) { history.push({role: 'assistant', content: answer}); addMessage('notice', answer); }
  });
}).catch(() => {});
const caseButtons = [...document.querySelectorAll('[data-case]')];
const controls = [input, form.querySelector('button'), document.querySelector('#reset'), ...caseButtons];
let history = [];
let busy = false;

/** 고객 또는 챗봇의 문장을 대화 영역에 추가합니다. */
function addMessage(role, text) {
  // 1. 대화 표시: HTML을 실행하지 않도록 텍스트로 표시합니다.
  const item = document.createElement('div');
  item.className = `chat-message ${role}`;
  const label = document.createElement('span');
  label.className = 'message-label';
  label.textContent = role === 'customer' ? '나' : '모찌카페';

  // ## 말풍선 본문을 만든 뒤 이름표와 함께 대화 목록에 추가합니다.
  const bubble = document.createElement('p');
  bubble.textContent = text;
  item.append(label, bubble);
  messages.querySelector('.chat-welcome')?.remove();
  messages.append(item);
}

/** 실제 문서 처리 단계를 입력·프롬프트·상태로 나누어 표시합니다. */
function showSteps(items) {
  // 1. 단계 표시: 문서 선택부터 답변까지 실행 순서대로 보여줍니다.
  NotebookTrace.render(steps, 'consultation', items);
}

/** 테스트 사례를 선택하면 질문 입력창에 문장을 채웁니다. */
caseButtons.forEach((button) => {
  // 1. 사례 연결: 버튼을 눌렀을 때 선택한 질문과 강조 표시를 바꿉니다.
  button.setAttribute('aria-pressed', 'false');
  button.addEventListener('click', () => { input.value = button.dataset.case; caseButtons.forEach((entry) => entry.setAttribute('aria-pressed', String(entry === button))); input.focus(); });
});

/** 질문을 직접 고치면 선택한 테스트 사례의 강조를 해제합니다. */
input.addEventListener('input', () => {
  // 1. 선택 해제: 수정한 질문을 기존 사례로 표시하지 않습니다.
  caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
});

/** 고객 질문을 서버에 보내 근거 기반 답변과 처리 단계를 보여줍니다. */
form.addEventListener('submit', async (event) => {
  // 1. 요청 준비: 현재 문장과 이전 대화를 함께 보냅니다.
  event.preventDefault();
  const text = input.value.trim();
  if (!text || busy) {

    return;
  }
  busy = true;
  controls.forEach((control) => { control.disabled = true; });
  status.textContent = '문서를 선택하고 답변을 생성하고 있습니다…';
  try {
    // 2. 처리 실행: 성공하면 고객 질문과 답변을 대화에 추가합니다.
    const response = await fetch('/chatbot/consultation', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: sessionId, input: {text, has_image: false}, history})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '처리에 실패했습니다.');
    addMessage('customer', text);
    addMessage('notice', data.state.answer.text);
    history.push({role: 'user', content: text}, {role: 'assistant', content: data.state.answer.text});
    showSteps(data.steps);
    await NotebookTrace.load('consultation', sessionId, steps, traceHistory).catch(() => {});
    input.value = '';
    caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
    flowStatus.textContent = `처리 완료 · ${data.elapsed_ms} ms`;
    status.textContent = '';
  } catch (error) {
    // 3. 오류 안내: 입력은 유지해 다시 시도할 수 있게 합니다.
    status.textContent = error.message || '서버에 연결할 수 없습니다.';
  } finally {
    // ## 요청 처리가 끝나면 다음 입력을 받을 수 있게 잠금을 해제합니다.
    busy = false;
    controls.forEach((control) => { control.disabled = false; });
    input.focus();
  }
});

/** 새 대화를 시작하면 화면의 문장과 이전 기록을 비웁니다. */
document.querySelector('#reset').addEventListener('click', async () => {
  // 1. 대화 초기화: 처리 중에는 기존 대화를 유지합니다.
  if (busy) {

    return;
  }
  await NotebookTrace.clear('consultation', sessionId);
  sessionId = NotebookTrace.newSession('consultation');
  history = [];
  messages.innerHTML = initialMessages;
  NotebookTrace.render(steps, 'consultation');
  traceHistory.replaceChildren();
  status.textContent = '';
  input.value = '';
  caseButtons.forEach((button) => button.setAttribute('aria-pressed', 'false'));
  flowStatus.textContent = '질문을 보내면 각 단계의 입력과 결과가 표시됩니다.';
});
