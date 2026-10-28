// 적립 실습은 서버 메모리 세션을 사용하고 실제 고객 파일을 변경하지 않습니다.
let sessionId = NotebookTrace.getSession('points');
let busy = false;
const messages = document.querySelector('#messages');
const status = document.querySelector('#status');
const flowStatus = document.querySelector('#flow-status');
const steps = document.querySelector('#steps');
const startButton = document.querySelector('#start');
const confirmButton = document.querySelector('#confirm');
const resetButton = document.querySelector('#reset');
const sampleInput = document.querySelector('#sample');
const customerInput = document.querySelector('#customer');
const pointsInput = document.querySelector('#points');
const receiptImage = document.querySelector('#receipt-image');
const caseDescription = document.querySelector('#case-description');
let cases = [];
let flowSteps = [];
const traceHistory = document.querySelector('#trace-history');
NotebookTrace.render(steps, 'points');
NotebookTrace.load('points', sessionId, steps, traceHistory).then((turns) => {
  flowSteps = turns.flatMap((turn) => turn.steps || []);
  if (flowSteps.length) NotebookTrace.render(steps, 'points', flowSteps);
}).catch(() => {});

/** 실행 중에는 실습 자료와 새 대화를 바꾸지 못하게 합니다. */
function lockInputs(locked) {
  // 1. 입력 제어: 진행 중에는 요청과 화면에 표시된 선택이 어긋나지 않게 합니다.
  sampleInput.disabled = locked;
  customerInput.disabled = locked;
  pointsInput.disabled = locked;
  resetButton.disabled = locked;
}

/** 고객에게 표시할 안내 문장을 공통 말풍선으로 추가합니다. */
function appendMessage(text) {
  // 1. 말풍선 구성: 안내와 문장을 텍스트로 넣어 화면에 표시합니다.
  const message = document.createElement('div');
  message.className = 'chat-message assistant';
  const label = document.createElement('span');
  label.className = 'message-label';
  label.textContent = '챗봇';

  // ## 말풍선 본문을 만든 뒤 이름표와 함께 대화 목록에 추가합니다.
  const bubble = document.createElement('p');
  bubble.textContent = text;
  message.append(label, bubble);
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
}

/** 새 실습을 위해 최초 안내와 처리할 단계 목록을 복원합니다. */
function resetDisplay() {
  // 1. 대화 안내: 처음처럼 샘플과 고객 선택 방법을 보여줍니다.
  messages.replaceChildren();
  const welcome = document.createElement('div');
  welcome.className = 'chat-welcome';
  const title = document.createElement('strong');
  title.textContent = '영수증을 확인해 주세요';
  const note = document.createElement('p');
  note.textContent = '샘플과 가상 고객을 선택하면 주문 정보를 비교합니다.';
  welcome.append(title, note);
  messages.append(welcome);

  // 2. 처리 안내: 실행 전에도 각 함수의 순서와 역할을 보여줍니다.
  NotebookTrace.render(steps, 'points');
  traceHistory.replaceChildren();
  flowSteps = [];
  flowStatus.textContent = '영수증을 확인하면 단계별 결과가 표시됩니다.';
}

/** 서버 응답을 받아 적립 흐름과 이전 턴의 저장 기록을 표시합니다. */
async function showResult(data, append) {
  // 1. 답변 표시: 실제 적립 결과를 대화에 추가합니다.
  appendMessage(data.state.answer.text);

  // 2. 단계 표시: 확인 턴에서는 영수증 판독 이후 단계를 이어 붙입니다.
  flowSteps = append ? [...flowSteps, ...data.steps] : [...data.steps];
  await NotebookTrace.load('points', sessionId, steps, traceHistory).catch(() => {});
  NotebookTrace.render(steps, 'points', flowSteps);
  if (data.elapsed_ms != null) flowStatus.textContent = `처리 완료 · ${data.elapsed_ms} ms`;
}

/** 서버 응답을 읽고 실패하면 안내 메시지를 오류로 전달합니다. */
async function readResponse(response) {
  // 1. 응답 확인: 서버가 보낸 오류 또는 실행 결과를 확인합니다.
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || '처리에 실패했습니다.');

  return data;
}

/** 선택한 사례의 영수증과 가상 고객을 화면에 보여줍니다. */
function showSelectedCase() {
  // 1. 사례 표시: 미리보기와 판독에 같은 샘플 이름을 사용합니다.
  const selected = cases.find((item) => item.sample === sampleInput.value);
  if (!selected) {

    return;
  }
  customerInput.value = selected.customer_id;
  receiptImage.src = selected.image_url;
  receiptImage.alt = `${selected.title} 테스트 영수증`;
  receiptImage.hidden = false;
  caseDescription.textContent = `예상: ${selected.expected} · 가상 고객 ${selected.customer_id}. 실제 판독 결과는 실행 후 확인하세요.`;
  confirmButton.disabled = true;
}

/** 서버에 준비된 테스트 사례를 읽어 선택 목록과 미리보기를 채웁니다. */
async function loadCases() {
  // 1. 사례 조회: 이미지와 판독 대상이 서버의 같은 목록을 사용합니다.
  try {
    const data = await readResponse(await fetch('/test/api/points/cases'));
    cases = data.cases;
    sampleInput.replaceChildren();
    for (const item of cases) {
      const option = document.createElement('option');
      option.value = item.sample;
      option.textContent = item.title;
      sampleInput.append(option);
    }
    if (!cases.length) throw new Error('준비된 영수증 사례가 없습니다.');
    sampleInput.value = cases[0].sample;
    sampleInput.disabled = false;
    startButton.disabled = false;
    showSelectedCase();
  } catch (error) {
    // 2. 조회 실패: 사용할 수 없는 사례는 판독을 시작하지 않습니다.
    caseDescription.textContent = error.message || '영수증 사례를 불러오지 못했습니다.';
  }
}

/** 사례를 바꾸면 사진과 고객을 함께 바꾸고 이전 확인 상태를 해제합니다. */
sampleInput.addEventListener('change', showSelectedCase);

/** 고객이 바뀌면 이전 고객의 영수증 검증 결과로 적립하지 못하게 합니다. */
customerInput.addEventListener('input', () => { confirmButton.disabled = true; });

/** 선택한 샘플을 판독하고 검증이 성공했을 때 확인 버튼을 켭니다. */
startButton.addEventListener('click', async () => {
  // 1. 판독 요청: 서버에 허용된 샘플 ID와 가상 고객만 전달합니다.
  if (busy) {

    return;
  }
  busy = true;
  lockInputs(true);
  startButton.disabled = true;
  confirmButton.disabled = true;
  status.textContent = '영수증을 읽고 주문을 확인하고 있습니다…';
  try {
    const payload = {session_id: sessionId, sample: document.querySelector('#sample').value, customer_id: document.querySelector('#customer').value.trim()};
    const data = await readResponse(await fetch('/chatbot/points/start', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}));
    messages.replaceChildren();
    await showResult(data, false);
    confirmButton.disabled = data.state.receipt.verification !== 'passed';
    status.textContent = '';
  } catch (error) {
    // 2. 오류 안내: 판독이 실패하면 확인하지 않은 상태로 유지합니다.
    status.textContent = error.message || '서버에 연결할 수 없습니다.';
  } finally {
    // ## 요청 처리가 끝나면 다음 입력을 받을 수 있게 잠금을 해제합니다.
    busy = false;
    lockInputs(false);
    startButton.disabled = false;
  }
});

/** 고객 확인 후 실습용 포인트를 서버에 전달합니다. */
confirmButton.addEventListener('click', async () => {
  // 1. 입력 확인: 잘못된 포인트는 판독 결과를 유지한 채 고칠 수 있게 합니다.
  if (busy) {

    return;
  }
  const pointsToAdd = Number(document.querySelector('#points').value);
  if (!Number.isSafeInteger(pointsToAdd) || pointsToAdd <= 0) {
    status.textContent = '실습용 포인트는 1 이상의 양의 정수로 입력해 주세요.';

    return;
  }

  // 2. 적립 요청: 확인 버튼을 누른 경우에만 서버 상태로 적립합니다.
  busy = true;
  lockInputs(true);
  confirmButton.disabled = true;
  startButton.disabled = true;
  try {
    const payload = {session_id: sessionId, confirmed: true, points_to_add: pointsToAdd};
    const data = await readResponse(await fetch('/chatbot/points/confirm', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}));
    await showResult(data, true);
    if (data.state.receipt.status === 'completed') {
      status.textContent = '적립을 마쳤습니다. 새 대화에서도 이미 처리한 영수증은 다시 적립할 수 없습니다.';
    } else {
      status.textContent = data.state.receipt.reason || '적립 결과를 확인해 주세요.';
      confirmButton.disabled = data.state.receipt.reason !== '연습에 사용할 적립 포인트를 지정해 주세요.';
    }
  } catch (error) {
    // 3. 오류 안내: 요청이 실패하면 다시 확인할 수 있게 합니다.
    status.textContent = error.message || '서버에 연결할 수 없습니다.';
    confirmButton.disabled = false;
  } finally {
    // ## 요청 처리가 끝나면 다음 입력을 받을 수 있게 잠금을 해제합니다.
    busy = false;
    lockInputs(false);
    startButton.disabled = false;
  }
});

/** 현재 실습 세션을 지우고 새 식별자로 다시 시작합니다. */
resetButton.addEventListener('click', async () => {
  // 1. 세션 초기화: 서버가 처리 이력을 유지하므로 중복 적립은 막습니다.
  if (busy) {

    return;
  }
  const confirmationWasDisabled = confirmButton.disabled;
  busy = true;
  lockInputs(true);
  startButton.disabled = true;
  confirmButton.disabled = true;
  try {
    await readResponse(await fetch(`/chatbot/points/${encodeURIComponent(sessionId)}`, {method: 'DELETE'}));
    sessionId = NotebookTrace.newSession('points');
    resetDisplay();
    confirmButton.disabled = true;
    status.textContent = '새 대화에서도 이미 적립한 영수증은 다시 적립할 수 없습니다.';
  } catch (error) {
    confirmButton.disabled = confirmationWasDisabled;
    status.textContent = error.message || '초기화에 실패했습니다.';
  } finally {
    // ## 요청 처리가 끝나면 다음 입력을 받을 수 있게 잠금을 해제합니다.
    busy = false;
    lockInputs(false);
    startButton.disabled = false;
  }
});

loadCases();
