// 의도 분류 실습은 브라우저 세션 ID를 사용하고 상태는 서버 메모리에 보관합니다.
const form = document.querySelector('#chat-form');
const input = document.querySelector('#chat-input');
const sendButton = document.querySelector('#send-message');
const resetButton = document.querySelector('#reset-chat');
const messages = document.querySelector('#chat-messages');
const status = document.querySelector('#chat-status');
const errorBox = document.querySelector('#chat-error');
const caseList = document.querySelector('#case-list');
const caseNote = document.querySelector('#case-note');
let sessionId = crypto.randomUUID();
let selectedCase = null;
let caseTurn = 0;
let running = false;

/** 서버 응답을 읽고 오류가 있으면 화면에 표시할 메시지로 바꿉니다. */
async function readResponse(response) {
  // 1. 응답 확인: 성공한 JSON을 반환하고 실패하면 서버의 안내를 오류로 전달합니다.
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `요청에 실패했습니다. (HTTP ${response.status})`);

  return data;
}

/** 말하는 사람과 문장을 받아 대화 영역에 안전하게 추가합니다. */
function appendMessage(role, content) {
  // 1. 말풍선 표시: 텍스트로 내용을 넣어 입력한 HTML이 실행되지 않게 합니다.
  const message = document.createElement('div');
  message.className = `chat-message ${role}`;
  const label = document.createElement('span');
  label.className = 'message-label';
  label.textContent = role === 'customer' ? '나' : role === 'assistant' ? '챗봇' : '분류 결과';

  // ## 말풍선 본문을 만든 뒤 이름표와 함께 대화 목록에 추가합니다.
  const bubble = document.createElement('p');
  bubble.textContent = content;
  message.append(label, bubble);
  messages.append(message);
  messages.scrollTop = messages.scrollHeight;
}

/** 처리 중인지에 따라 입력과 사례 선택을 잠그거나 다시 사용할 수 있게 합니다. */
function updateControls() {
  // 1. 입력 제어: 한 턴이 끝나기 전에는 중복 요청과 세션 변경을 막습니다.
  sendButton.disabled = running;
  resetButton.disabled = running;
  input.disabled = running;
  caseList.querySelectorAll('button').forEach((button) => { button.disabled = running; });
}

/** 서버에서 받은 단계별 상태와 실행 정보를 오른쪽 흐름에 표시합니다. */
function showFlow(data, request) {
  // 1. 단계 선택: 각 함수의 실제 출력 상태를 이름으로 찾아 화면에 표시합니다.
  const steps = Object.fromEntries(data.steps.map((item) => [item.step, item]));
  const prepared = steps.prepare_state.state;
  const classified = steps.classify_intent.state;
  const answerStep = steps.generate_unknown_response;
  const saved = steps.save_state.state;
  const result = classified.intent;

  // ## 준비·분류·저장 단계의 요약과 실제 상태를 각각 표시합니다.
  document.querySelector('#prepare-summary').textContent = `이전 의도: ${prepared.previous_intent || '없음'} · 기록: ${prepared.history.length}개`;
  document.querySelector('#classify-summary').textContent = `의도: ${result.intent} · 신뢰도: ${result.confidence == null ? '없음' : result.confidence}`;
  document.querySelector('#save-summary').textContent = '현재 세션에 저장했습니다.';
  document.querySelector('#prepare-state').textContent = JSON.stringify(prepared, null, 2);
  document.querySelector('#model-input').textContent = JSON.stringify({text: prepared.input.text, previous_intent: prepared.previous_intent, has_image: prepared.input.has_image}, null, 2);
  document.querySelector('#classify-state').textContent = JSON.stringify(classified, null, 2);

  // ## 답변 생성 여부에 맞춰 입력·프롬프트·상태를 표시합니다.
  document.querySelector('#answer-summary').textContent = answerStep ? `답변 생성 완료 · 모델: ${answerStep.model}` : 'unknown이 아니므로 실행하지 않았습니다.';
  document.querySelector('#answer-input').textContent = answerStep ? JSON.stringify(answerStep.input, null, 2) : '이번 턴에는 실행하지 않았습니다.';
  document.querySelector('#answer-prompt').textContent = answerStep ? answerStep.prompt : '이번 턴에는 실행하지 않았습니다.';
  document.querySelector('#answer-state').textContent = answerStep ? JSON.stringify(answerStep.state, null, 2) : '이번 턴에는 실행하지 않았습니다.';
  document.querySelector('#save-state').textContent = JSON.stringify(saved, null, 2);

  // 2. 실행 정보: 모델과 소요 시간, 실제 프롬프트와 전체 요청·응답을 함께 남깁니다.
  document.querySelector('#flow-status').textContent = '최근 턴의 처리가 완료되었습니다.';
  document.querySelector('#execution-info').textContent = `모델: ${data.model} · 처리 시간: ${data.elapsed_ms.toLocaleString()} ms`;
  document.querySelector('#jev-prompt').textContent = data.prompt;
  document.querySelector('#request-json').textContent = JSON.stringify(request, null, 2);
  document.querySelector('#response-json').textContent = JSON.stringify(data, null, 2);
}

/** 테스트 사례를 불러와 선택한 입력과 이미지 여부를 전송 준비 상태로 만듭니다. */
async function loadCases() {
  // 1. 사례 조회: 테스트 파일의 제목을 버튼으로 만들고 선택하면 입력창을 채웁니다.
  try {
    const data = await readResponse(await fetch('/test/api/intent-turn/cases'));
    caseList.replaceChildren();
    /** 테스트 사례 하나를 제목이 붙은 선택 버튼으로 추가합니다. */
    data.cases.forEach((item) => {
      // 1. 버튼 구성: 사례 제목과 초기 선택 상태를 버튼에 넣습니다.
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = item.title;
      button.setAttribute('aria-pressed', 'false');
      /** 사례를 선택하면 문장과 이미지 첨부 여부를 다음 요청에 사용합니다. */
      button.addEventListener('click', () => {
        // 1. 입력 선택: 기존 대화는 유지하고 사례 문장만 입력창에 넣습니다.
        selectedCase = item;
        caseTurn = 0;
        const turn = item.turns ? item.turns[caseTurn] : item;
        input.value = turn.input.text;
        caseList.querySelectorAll('button').forEach((entry) => entry.setAttribute('aria-pressed', String(entry === button)));
        caseNote.textContent = `예상 의도: ${turn.expected_intent}${turn.input.has_image ? ' · 이미지 첨부 여부 포함' : ''}${item.turns ? ` · ${caseTurn + 1}/${item.turns.length}번째 문장` : ''}. 보내기를 눌러 실행하세요.`;
        input.focus();
      });
      caseList.append(button);
    });
  } catch (error) {
    caseList.textContent = '사례를 불러오지 못했습니다. 직접 입력해 주세요.';
  }
}

/** 사례 문장을 수정하면 사례의 이미지 첨부 여부도 함께 해제합니다. */
input.addEventListener('input', () => {
  // 1. 선택 해제: 직접 입력한 문장에 이전 사례의 이미지 정보가 남지 않게 합니다.
  selectedCase = null;
  caseList.querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', 'false'));
  caseNote.textContent = '선택한 사례는 보내기를 누르면 실행됩니다.';
});

/** 고객 문장을 서버에 보내고 실제 분류 결과와 단계별 상태를 표시합니다. */
form.addEventListener('submit', async (event) => {
  // 1. 요청 준비: 현재 세션과 이번 고객 입력만 보내고 이전 상태는 서버가 복원합니다.
  event.preventDefault();
  const text = input.value.trim();
  if (!text || running) {

    return;
  }
  const chosenCase = selectedCase;
  const chosenTurn = chosenCase?.turns ? chosenCase.turns[caseTurn] : chosenCase;
  const request = {session_id: sessionId, customer_info: null, input: {text, has_image: chosenTurn ? chosenTurn.input.has_image : false}};
  running = true;
  updateControls();
  errorBox.hidden = true;
  status.textContent = '의도를 분류하고 있습니다…';
  document.querySelector('#flow-status').textContent = '서버에서 처리하고 있습니다…';

  try {
    // 2. 분류 실행: 성공한 턴만 대화에 추가하고 서버가 반환한 실제 상태를 표시합니다.
    const data = await readResponse(await fetch('/chatbot/intent/turn', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)}));
    showFlow(data, request);
    document.querySelector('#chat-welcome')?.remove();
    appendMessage('customer', text);
    const result = data.state.intent;
    const expected = chosenTurn ? ` (예상: ${chosenTurn.expected_intent})` : '';
    appendMessage('notice', `${result.intent} · 신뢰도 ${result.confidence == null ? '없음' : result.confidence}${expected}`);
    if (data.state.answer?.answer) appendMessage('assistant', data.state.answer.answer);

    // ## 연속 사례는 다음 문장을 준비하고 마지막 문장이면 사례 선택을 비웁니다.
    if (chosenCase?.turns && caseTurn + 1 < chosenCase.turns.length) {
      caseTurn += 1;
      const next = chosenCase.turns[caseTurn];
      input.value = next.input.text;
      caseNote.textContent = `예상 의도: ${next.expected_intent} · ${caseTurn + 1}/${chosenCase.turns.length}번째 문장. 보내기를 눌러 이어서 실행하세요.`;
    } else {
      input.value = '';
      selectedCase = null;
      caseList.querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', 'false'));
      caseNote.textContent = '선택한 사례는 보내기를 누르면 실행됩니다.';
    }
    status.textContent = '';
  } catch (error) {
    // 3. 실패 안내: 입력을 유지해 다시 시도할 수 있게 하고 실패 사실을 흐름에도 표시합니다.
    errorBox.textContent = error.message || '서버에 연결할 수 없습니다.';
    errorBox.hidden = false;
    status.textContent = '메시지를 다시 보내 주세요.';
    document.querySelector('#flow-status').textContent = '이번 턴을 처리하지 못했습니다.';
  } finally {
    // 4. 입력 복구: 실행이 끝나면 다음 문장을 입력할 수 있게 합니다.
    running = false;
    updateControls();
    input.focus();
  }
});

/** 새 대화 버튼을 누르면 현재 세션을 초기화하고 빈 대화 화면을 보여줍니다. */
resetButton.addEventListener('click', async () => {
  // 1. 세션 초기화: 서버의 현재 세션을 지운 뒤 새 식별자로 다음 대화를 시작합니다.
  if (running) {

    return;
  }
  running = true;
  updateControls();
  try {
    await readResponse(await fetch(`/chatbot/intent/turn/${encodeURIComponent(sessionId)}`, {method: 'DELETE'}));

    // ## 새 세션의 대화와 사례 선택을 초기화합니다.
    sessionId = crypto.randomUUID();
    messages.replaceChildren();
    appendMessage('notice', '새 대화가 시작되었습니다.');
    input.value = '';
    selectedCase = null;
    caseList.querySelectorAll('button').forEach((button) => button.setAttribute('aria-pressed', 'false'));
    caseNote.textContent = '선택한 사례는 보내기를 누르면 실행됩니다.';

    // ## 이전 처리 결과와 실행 정보를 대기 상태로 되돌립니다.
    document.querySelector('#flow-status').textContent = '메시지를 보내면 처리 흐름이 표시됩니다.';
    ['prepare-summary', 'classify-summary', 'answer-summary', 'save-summary'].forEach((id) => { document.querySelector(`#${id}`).textContent = '대기 중'; });
    ['prepare-state', 'model-input', 'classify-state', 'answer-input', 'answer-prompt', 'answer-state', 'save-state', 'request-json', 'response-json'].forEach((id) => { document.querySelector(`#${id}`).textContent = '아직 실행되지 않았습니다.'; });
    document.querySelector('#execution-info').textContent = '모델과 처리 시간이 여기에 표시됩니다.';
    document.querySelector('#jev-prompt').textContent = '실행 후 표시됩니다.';
    errorBox.hidden = true;
    status.textContent = '';
  } catch (error) {
    // 2. 실패 안내: 서버 세션을 지우지 못하면 현재 대화를 유지하고 원인을 보여줍니다.
    errorBox.textContent = `새 대화를 시작하지 못했습니다: ${error.message}`;
    errorBox.hidden = false;
  } finally {
    // ## 요청 처리가 끝나면 입력 잠금과 실행 중 표시를 해제합니다.
    running = false;
    updateControls();
    input.focus();
  }
});

loadCases();
