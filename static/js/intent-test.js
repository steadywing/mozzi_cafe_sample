// 화면에 보여줄 대화 문장과 다음 API 요청에 보낼 업무 상태를 따로 보관합니다.
const pageConfig = document.body.dataset;
const endpoint = pageConfig.endpoint || '/chatbot/order';
const casesUrl = pageConfig.casesUrl || '/test/api/order/cases';
const promptsUrl = pageConfig.promptsUrl || '/test/api/order/prompts';
const promptKeys = (pageConfig.promptKeys || 'persona,order').split(',');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#chat-input');
const sendButton = document.querySelector('#send-message');
const resetButton = document.querySelector('#reset-chat');
const messages = document.querySelector('#chat-messages');
const status = document.querySelector('#chat-status');
const errorBox = document.querySelector('#chat-error');
const retryHistoryButton = document.querySelector('#retry-history');
const requestViewer = document.querySelector('#request-json');
const responseViewer = document.querySelector('#response-json');
const stateRecords = document.querySelector('#state-records');
const flowCurrent = document.querySelector('#flow-current');
const flowStatus = document.querySelector('#flow-status');
NotebookTrace.render(flowCurrent, 'legacy_order');
const stateRecordsStatus = document.querySelector('#state-records-status');
const caseList = document.querySelector('#case-list');
const caseNote = document.querySelector('#case-note');
const customerSelect = document.querySelector('#customer-select');
let cases = [];
let selectedCase = null;
let sessionState = {};
let running = false;
let pendingHistory = null;

/** 고객 ID와 세션 ID로 저장 기록을 불러와, 단계별 결과와 이전 턴 상태를 보여줍니다. */
async function loadStateRecords(customerId, sessionId) {
  // 1. 기록 조회: 이번 고객과 세션에 저장된 주문 처리 턴을 읽습니다.
  stateRecords.replaceChildren();
  stateRecordsStatus.textContent = '저장 기록을 불러오는 중입니다…';
  try {
    const query = new URLSearchParams({customer_id: customerId, session_id: sessionId});
    const data = await readResponse(await fetch(`/test/api/states?${query}`));
    if (!Array.isArray(data.states)) throw new Error('상태 기록 형식이 올바르지 않습니다.');
    stateRecordsStatus.textContent = `총 ${data.states.length}턴 저장됨`;

    // 2. 최신 흐름: 오른쪽 상단에는 가장 최근 턴의 실제 실행 함수만 표시합니다.
    const latest = data.states[data.states.length - 1];
    if (latest) {
      const currentSteps = Array.isArray(latest.steps) ? latest.steps : [{step: 'response', state: latest}];
      NotebookTrace.render(flowCurrent, 'legacy_order', currentSteps);
      flowStatus.textContent = `최근 턴 · ${currentSteps.length}단계${typeof latest.elapsed_ms === 'number' ? ` · ${latest.elapsed_ms.toLocaleString()} ms` : ''}`;
    } else {
      NotebookTrace.render(flowCurrent, 'legacy_order');
      flowStatus.textContent = '메시지를 보내면 각 단계의 결과가 표시됩니다.';
    }

    // 3. 턴별 기록: 과거 턴과 최신 턴을 각각 펼쳐 전체 실행 경로를 조회하게 합니다.
    data.states.forEach((turn, index) => {
      const entry = document.createElement('details');
      entry.className = 'trace-turn';
      entry.open = index === data.states.length - 1;
      const heading = document.createElement('summary');
      heading.textContent = `${index + 1}번째 턴${typeof turn.elapsed_ms === 'number' ? ` · ${turn.elapsed_ms.toLocaleString()} ms` : ''}`;
      const body = document.createElement('div');
      const turnSteps = Array.isArray(turn.steps) ? turn.steps : [{step: 'response', state: turn}];
      NotebookTrace.render(body, 'legacy_order', turnSteps);
      entry.append(heading, body);
      stateRecords.append(entry);
    });

    return data.states;
  } catch (error) {
    stateRecordsStatus.textContent = `저장 기록 조회 실패: ${error.message}`;

    return [];
  }
}

/** 선택한 고객의 브라우저 세션 ID로 저장된 주문 턴과 대화를 다시 보여줍니다. */
async function restoreOrderSession() {
  // 1. 세션 확인: 해당 고객이 마지막으로 사용한 실습 세션만 조회합니다.
  const customerId = customerSelect.value;
  const sessionId = sessionStorage.getItem(`order-session-${customerId}`);
  if (!customerId || !sessionId) return;
  const turns = await loadStateRecords(customerId, sessionId);
  if (!turns.length || customerSelect.value !== customerId) return;

  // 2. 상태 복원: 마지막 단계의 상태를 다음 요청에 이어서 사용합니다.
  const latest = turns[turns.length - 1];
  const latestState = latest.steps?.[latest.steps.length - 1]?.state;
  sessionState = latestState || {};
  sessionState.history = [];
  messages.replaceChildren();
  turns.forEach((turn) => {
    const finalState = turn.steps?.[turn.steps.length - 1]?.state;
    const question = finalState?.input?.text;
    const answer = finalState?.answer?.answer;
    if (question) { sessionState.history.push({role: 'user', content: question}); appendMessage('customer', question); }
    if (answer) { sessionState.history.push({role: 'assistant', content: answer}); appendMessage('assistant', answer); }
  });
}

/** 요청·대화 저장 상태에 맞춰 입력 허용 여부를 조절하고, 저장할 대화가 남아 있으면 재시도 버튼을 보여줍니다. */
function updateChatControls() {
  // 1. 입력 제어: 요청 처리나 대화 저장이 끝나기 전에는 다음 메시지를 보낼 수 없게 합니다.
  const blocked = running || pendingHistory !== null;
  sendButton.disabled = blocked || !customerSelect.value;
  resetButton.disabled = blocked;
  customerSelect.disabled = blocked || customerSelect.options.length === 0;
  input.disabled = blocked;
  /** 요청 중이거나 대화를 저장하지 못했으면 사례 버튼도 누를 수 없게 합니다. */
  caseList.querySelectorAll('button').forEach((button) => {
    // 1. 버튼 제어: 처리 중에 다른 사례로 입력이 바뀌지 않도록 버튼을 잠급니다.
    button.disabled = blocked;
  });
  retryHistoryButton.hidden = pendingHistory === null;
  retryHistoryButton.disabled = running;
}

/** 저장을 기다리는 대화 문장을 서버에 보내고, 성공하면 저장된 대화를 상태에 반영합니다. */
async function savePendingHistory() {
  // 1. 기록 저장: 이미 생성한 입력과 답변을 대화 저장 API에 보내며, 모델을 다시 호출하지 않습니다.
  const data = await readResponse(await fetch('/chatbot/history', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(pendingHistory),
  }));

  // 2. 저장 완료: 저장된 대화를 다음 요청에 사용할 상태에 넣고, 저장 대기 표시를 없앱니다.
  sessionState.history = data.history;
  pendingHistory = null;
  errorBox.hidden = true;
  status.textContent = '';
}

/** 서버의 고객 목록으로 선택 상자를 채우고, 조회에 실패하면 메시지 전송을 막습니다. */
async function loadCustomers() {
  // 1. 고객 조회: 대화 기록을 고객별로 저장할 수 있도록 등록된 고객을 서버에서 가져옵니다.
  try {
    const data = await readResponse(await fetch('/test/api/customers'));
    if (!Array.isArray(data.customers) || data.customers.length === 0) throw new Error('등록된 고객이 없습니다.');

    // 2. 고객 표시: 고객 이름은 화면에, 고객 ID는 선택값에 넣고 메시지 전송을 허용합니다.
    customerSelect.replaceChildren();
    data.customers.forEach((customer) => customerSelect.add(new Option(customer.name, customer.customer_id)));
    customerSelect.disabled = false;
    sendButton.disabled = false;
    await restoreOrderSession();
  } catch (error) {
    customerSelect.replaceChildren(new Option('고객을 불러오지 못했습니다', ''));
    errorBox.textContent = `고객 목록을 불러오지 못했습니다: ${error.message}`;
    errorBox.hidden = false;
    sendButton.disabled = true;
  }
}

/** 말한 사람의 역할과 문장을 받아, 이름표가 붙은 말풍선을 대화 화면에 추가합니다. */
function appendMessage(role, content) {
  // 1. 문장 구성: 말한 사람에 맞는 이름표를 만들고, 입력에 HTML이 있어도 실행되지 않게 텍스트로 넣습니다.
  const message = document.createElement('div');
  message.className = `chat-message ${role}`;
  const label = document.createElement('span');
  label.className = 'message-label';
  label.textContent = role === 'customer' ? '나' : role === 'assistant' ? '모찌카페' : '안내';

  // 2. 문장 표시: 문장을 말풍선으로 추가하고, 스크롤을 내려 새 메시지가 보이게 합니다.
  const bubble = document.createElement('p');
  bubble.textContent = content;
  message.append(label, bubble);
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
}

/** 서버 응답을 JSON으로 돌려주며, 실패 응답이면 서버의 안내 문장을 담은 오류를 냅니다. */
async function readResponse(response) {
  // 1. 응답 확인: 응답 내용을 읽고, HTTP 실패 상태이면 호출한 곳에서 처리할 오류로 바꿉니다.
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `요청에 실패했습니다. (HTTP ${response.status})`);

  return data;
}

/** 현재 페이지가 사용하는 프롬프트를 서버에서 불러와, 각 모델 입력 영역에 원문을 보여줍니다. */
async function loadPrompts() {
  // 1. 프롬프트 조회: 페이지 설정의 조회 주소로 요청해, 서버에서 사용하는 지침 원문을 가져옵니다.
  try {
    const response = await fetch(promptsUrl);
    const data = await readResponse(response);

    // 2. 프롬프트 표시: 페이지 설정에 있는 프롬프트 이름에 맞춰 각 표시 영역에 원문을 넣습니다.
    promptKeys.forEach((key) => { document.querySelector(`#${key}-prompt`).textContent = data[key].content; });
  } catch (error) {
    const message = `프롬프트를 불러오지 못했습니다: ${error.message}`;
    promptKeys.forEach((key) => { document.querySelector(`#${key}-prompt`).textContent = message; });
  }
}

/** 서버의 테스트 사례를 버튼으로 보여주고, 선택한 사례를 실행하지 않고 입력창에만 채웁니다. */
async function loadCases() {
  // 1. 사례 조회: 현재 페이지의 사례 목록을 불러와, 고객이 직접 보낼 사례를 고를 수 있게 합니다.
  try {
    const data = await readResponse(await fetch(casesUrl));
    if (!Array.isArray(data.cases)) throw new Error('사례 형식이 올바르지 않습니다.');
    cases = data.cases;
    caseList.replaceChildren();
    /** 사례 하나를 제목이 붙은 버튼으로 만들어 선택 목록에 추가합니다. */
    cases.forEach((item) => {
      // 1. 버튼 준비: 사례 제목을 버튼에 넣고, 아직 선택되지 않았다는 상태를 표시합니다.
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = item.title;
      button.setAttribute('aria-pressed', 'false');
      /** 누른 사례의 문장과 이미지 첨부 여부를 선택해, 다음 전송에 사용할 입력을 준비합니다. */
      button.addEventListener('click', () => {
        // 1. 입력 채우기: 사례 문장을 입력창에 넣고, 실제 전송은 보내기 버튼을 눌렀을 때 실행하도록 기다립니다.
        selectedCase = item;
        caseList.querySelectorAll('button').forEach((entry) => entry.setAttribute('aria-pressed', String(entry === button)));
        input.value = item.input.text;
        caseNote.textContent = item.input.has_image
          ? '현재 대화에 입력합니다. 이미지 첨부 여부만 전달하며 실제 이미지는 전송하지 않습니다.'
          : '현재 대화에 입력합니다. 보내기를 누르면 실행됩니다.';
        input.focus();
      });
      caseList.append(button);
    });
  } catch (error) {
    caseList.textContent = '사례를 불러오지 못했습니다.';
    caseNote.textContent = '직접 입력하여 대화할 수 있습니다.';
  }
}

/** 사례 문장을 직접 고치면 사례 선택을 해제하고, 현재 대화 상태로 입력을 이어갑니다. */
input.addEventListener('input', () => {
  // 1. 선택 해제: 직접 쓴 문장에 이전 사례의 이미지 첨부 표시가 붙지 않도록 사례 선택을 비웁니다.
  if (selectedCase) {
    selectedCase = null;
    caseList.querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', 'false'));
    caseNote.textContent = '직접 입력할 때는 현재 업무 상태를 사용합니다.';
  }
});

/** 보내기를 누르면 현재 대화 상태와 문장을 서버에 보내고, 답변을 표시한 뒤 대화를 저장합니다. */
form.addEventListener('submit', async (event) => {
  // 1. 입력 확인: 빈 입력·중복 전송·저장 대기·고객 미선택이면 요청을 보내지 않습니다.
  event.preventDefault();
  const text = input.value.trim();
  if (!text || running || pendingHistory || !customerSelect.value) {

    return;
  }

  // 2. 상태 준비: 사례를 새로 골라도 기존 상태와 세션 ID를 유지하고, 현재 고객 ID를 넣습니다.
  const selected = selectedCase;
  const customerId = customerSelect.value;
  const requestState = {...sessionState, customer_id: customerId};

  // 3. 기록 포함: 앞선 문맥을 모델이 알 수 있도록 저장된 대화를 넣으며, 첫 요청에는 빈 목록을 넣습니다.
  requestState.history = sessionState.history || [];

  // 4. 요청 구성: 업무 상태에 이번 문장과 이미지 첨부 여부를 합쳐 서버가 받을 요청을 만듭니다.
  const request = {...requestState, input: {text, has_image: selected ? selected.input.has_image : false}};

  // 5. 대기 표시: 이번 요청을 화면에 남기고, 답변을 기다리는 동안 입력창과 선택 버튼을 잠급니다.
  requestViewer.textContent = JSON.stringify(request, null, 2);
  responseViewer.textContent = '서버 응답을 기다리고 있습니다…';
  document.querySelector('#chat-welcome')?.remove();
  appendMessage('customer', text);
  input.value = '';
  errorBox.hidden = true;
  running = true;
  sendButton.disabled = true;
  resetButton.disabled = true;
  customerSelect.disabled = true;
  input.disabled = true;
  /** 요청 중이거나 대화를 저장하지 못했으면 사례 버튼도 누를 수 없게 합니다. */
  caseList.querySelectorAll('button').forEach((button) => {
    // 1. 버튼 제어: 처리 중에 다른 사례로 입력이 바뀌지 않도록 버튼을 잠급니다.
    button.disabled = true;
  });
  status.textContent = '답변을 기다리고 있습니다…';

  // 6. 요청: 페이지에 설정된 API로 요청을 보내고, 받은 응답 본문을 JSON으로 읽습니다.
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(request),
    });
    const data = await response.json();

    // 7. 응답 검증: 서버 응답을 먼저 화면에 남긴 뒤, 실패 상태이거나 세션 ID가 없으면 오류로 처리합니다.
    responseViewer.textContent = JSON.stringify(data, null, 2);
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `요청에 실패했습니다. (HTTP ${response.status})`);
    if (!data || typeof data !== 'object' || typeof data.session_id !== 'string') throw new Error('서버 응답에서 세션 상태를 찾을 수 없습니다.');

    // 8. 응답 반영: 응답 상태를 다음 요청용으로 보관하고, 답변이 있으면 말풍선으로 보여줍니다.
    sessionState = data;
    sessionStorage.setItem(`order-session-${customerId}`, data.session_id);
    selectedCase = null;
    caseList.querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', 'false'));
    caseNote.textContent = '선택한 사례는 보내기를 누르면 실행됩니다.';
    if (typeof data.answer?.answer === 'string' && data.answer.answer.trim()) {
      appendMessage('assistant', data.answer.answer);
    } else {
      appendMessage('notice', '의도 분류가 완료되었습니다. 해당 기능의 고객 답변은 아직 구현되지 않았습니다.');
    }

    // 9. 기록 준비: 이번 고객 입력과 실제 답변을 대화 저장용으로 묶고, 처리 기록 조회 후 저장을 요청합니다.
    const turnMessages = [{role: 'user', content: text}];
    if (typeof data.answer?.answer === 'string' && data.answer.answer.trim()) {
      turnMessages.push({role: 'assistant', content: data.answer.answer});
    }
    pendingHistory = {customer_id: customerId, session_id: data.session_id, messages: turnMessages};
    await loadStateRecords(customerId, data.session_id);
    status.textContent = '대화 기록을 저장하고 있습니다…';
    try {
      await savePendingHistory();
    } catch (error) {
      errorBox.textContent = `답변은 생성되었지만 대화 기록을 저장하지 못했습니다: ${error.message}`;
      errorBox.hidden = false;
      status.textContent = '기록 저장을 다시 시도해 주세요.';
    }
  } catch (error) {
    // 10. 실패 안내: 요청 중 오류가 나면 실패 사유를 표시하고, 다시 보낼 수 있도록 이번 문장을 입력창에 복원합니다.
    input.value = text;
    errorBox.textContent = error.message || '서버에 연결할 수 없습니다.';
    errorBox.hidden = false;
    if (responseViewer.textContent === '서버 응답을 기다리고 있습니다…') responseViewer.textContent = '서버 응답을 받지 못했습니다.';
    status.textContent = '메시지를 다시 보내 주세요.';
  } finally {
    // ## 요청 처리가 끝나면 입력 잠금과 실행 중 표시를 해제합니다.
    running = false;

    // 11. 조작 복구: 요청 중 표시를 해제하고, 대화 저장이 끝났을 때만 다음 입력을 허용합니다.
    updateChatControls();
    if (!pendingHistory) input.focus();
  }
});

/** 새 대화나 고객 변경 시 화면과 메모리의 상태를 비우며, 서버에 저장된 기록은 삭제하지 않습니다. */
function resetChat() {
  // 1. 초기화 확인: 요청이나 저장이 진행 중이면 멈추고, 그 외에는 다음 요청에 사용할 상태를 비웁니다.
  if (running || pendingHistory) {

    return;
  }
  sessionState = {};

  // 2. 화면 초기화: 화면의 말풍선·요청·응답·처리 기록을 지워 새 대화가 시작됐음을 보여줍니다.
  messages.replaceChildren();
  appendMessage('notice', '새 대화가 시작되었습니다.');
  requestViewer.textContent = '메시지를 보내면 표시됩니다.';
  responseViewer.textContent = '메시지를 보내면 표시됩니다.';
  stateRecords.replaceChildren();
  stateRecordsStatus.textContent = '대화를 실행하면 저장된 기록이 표시됩니다.';
  NotebookTrace.render(flowCurrent, 'legacy_order');
  flowStatus.textContent = '메시지를 보내면 각 단계의 결과가 표시됩니다.';
  errorBox.hidden = true;
  status.textContent = '';

  // 3. 입력 초기화: 이전 문장과 사례 선택을 지우고, 새 메시지를 입력할 수 있게 입력창으로 이동합니다.
  input.value = '';
  selectedCase = null;
  caseList.querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', 'false'));
  caseNote.textContent = '선택한 사례는 보내기를 누르면 실행됩니다.';
  input.focus();
}

/** 새 대화 버튼을 누르면 현재 고객의 세션 연결과 화면을 비웁니다. */
resetButton.addEventListener('click', () => {
  // 1. 새 세션: 현재 고객의 마지막 세션 연결을 끊고 화면을 비웁니다.
  sessionStorage.removeItem(`order-session-${customerSelect.value}`);
  resetChat();
});
/** 고객을 바꾸면 선택한 고객의 마지막 주문 세션을 다시 읽습니다. */
customerSelect.addEventListener('change', async () => {
  // 1. 고객 변경: 이전 고객의 대화를 비우고 선택한 고객의 저장 기록을 읽습니다.
  resetChat();
  await restoreOrderSession();
});
/** 저장 재시도를 누르면 모델 호출 없이 대화 저장만 다시 요청하고, 성공 여부를 화면에 보여줍니다. */
retryHistoryButton.addEventListener('click', async () => {
  // 1. 재시도 준비: 처리 중이면 멈추고, 저장할 대화가 있을 때만 입력을 잠급니다.
  if (running || !pendingHistory) {

    return;
  }
  running = true;
  updateChatControls();
  status.textContent = '대화 기록을 다시 저장하고 있습니다…';
  try {
    // 2. 기록 재시도: 실패한 대화 저장만 다시 요청해, 이미 받은 답변이 새로 생성되지 않게 합니다.
    await savePendingHistory();
  } catch (error) {
    // ## 조회나 저장에 실패한 이유를 화면에 표시합니다.
    errorBox.textContent = `대화 기록 저장 실패: ${error.message}`;
    errorBox.hidden = false;
    status.textContent = '기록 저장을 다시 시도해 주세요.';
  } finally {
    // ## 요청 처리가 끝나면 입력 잠금과 실행 중 표시를 해제합니다.
    running = false;
    updateChatControls();
    if (!pendingHistory) input.focus();
  }
});

loadPrompts();
loadCases();
sendButton.disabled = true;
loadCustomers();
