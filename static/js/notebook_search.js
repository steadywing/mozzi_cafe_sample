// 서버에 준비된 샘플 사진으로 실제 검색 흐름을 실행합니다.
const form = document.querySelector('#chat-form');
const input = document.querySelector('#chat-input');
const sample = document.querySelector('#sample');
const sampleImage = document.querySelector('#sample-image');
const sampleFigure = document.querySelector('#sample-figure');
const sampleCaption = document.querySelector('#sample-caption');
const sampleExpected = document.querySelector('#sample-expected');
const messages = document.querySelector('#chat-messages');
const steps = document.querySelector('#flow-steps');
const traceHistory = document.querySelector('#trace-history');
let sessionId = NotebookTrace.getSession('search');
NotebookTrace.render(steps, 'search');
NotebookTrace.load('search', sessionId, steps, traceHistory).catch(() => {});
const status = document.querySelector('#chat-status');
const errorBox = document.querySelector('#chat-error');
let running = false;
let cases = [];

/** 새 대화를 시작하면 사진 검색 안내를 대화창 가운데 다시 보여줍니다. */
function showWelcome() {
  // 1. 안내 구성: 처음 화면과 같은 제목과 설명을 만듭니다.
  const welcome = document.createElement('div');
  welcome.id = 'chat-welcome';
  welcome.className = 'chat-welcome';
  const title = document.createElement('strong');
  title.textContent = '비슷한 메뉴를 찾아볼까요?';
  const note = document.createElement('p');
  note.textContent = '테스트 사진을 선택하고 문장을 보내 주세요.';
  welcome.append(title, note);

  // 2. 안내 표시: 이전 대화 대신 새 안내를 놓습니다.
  messages.replaceChildren(welcome);
}

/** 선택한 테스트 사진과 확인 목표를 화면에 보여줍니다. */
function showSample() {
  // 1. 선택 확인: 목록에 있는 사례만 사진과 목표를 표시합니다.
  const chosen = cases.find((item) => item.sample === sample.value);
  sampleFigure.hidden = !chosen;
  if (!chosen) {
    sampleImage.removeAttribute('src');
    sampleExpected.textContent = '';

    return;
  }
  sampleImage.src = `/test/api/search/images/${encodeURIComponent(chosen.sample)}`;
  sampleImage.alt = `${chosen.title} 테스트 사진`;
  sampleCaption.textContent = chosen.title;
  sampleExpected.textContent = `확인 목표: ${chosen.expected}`;
}

sample.addEventListener('change', showSample);

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

/** 준비된 샘플 사진 목록을 서버에서 읽어 선택 상자에 표시합니다. */
async function loadSamples() {
  // 1. 샘플 조회: 허용된 사진 이름을 선택지로 만듭니다.
  try {
    const response = await fetch('/test/api/search/cases');
    if (!response.ok) throw new Error('샘플 사진을 불러오지 못했습니다.');
    const data = await response.json();
    sample.replaceChildren();
    cases = data.cases;
    /** 샘플 사진 하나의 제목과 파일 이름을 선택 항목으로 추가합니다. */
    cases.forEach((item) => {
      // 1. 선택지 구성: 화면에는 제목을 보여주고 요청에는 파일 이름을 사용합니다.
      const option = document.createElement('option');
      option.value = item.sample;
      option.textContent = item.title;
      sample.append(option);
    });
    if (!cases.length) throw new Error('준비된 샘플 사진이 없습니다.');
    showSample();
  } catch (error) {
    // ## 조회나 저장에 실패한 이유를 화면에 표시합니다.
    errorBox.textContent = error.message;
    errorBox.hidden = false;
  }
}

/** 서버가 반환한 검색 처리 단계를 실제 입력·프롬프트·상태로 표시합니다. */
function showSteps(data) {
  // 1. 단계 표시: 검색 결과와 단계 후 상태를 갱신합니다.
  NotebookTrace.render(steps, 'search', data.steps);
  document.querySelector('#flow-status').textContent = `처리 시간 ${data.elapsed_ms} ms`;
}

/** 선택한 샘플과 문장을 보내고 메뉴 검색 결과를 표시합니다. */
form.addEventListener('submit', async (event) => {
  // 1. 요청 준비: 선택된 샘플과 이번 문장을 함께 전달합니다.
  event.preventDefault();
  const text = input.value.trim();
  if (!text || !sample.value || running) {

    return;
  }
  running = true;
  form.querySelector('button').disabled = true;
  sample.disabled = true;
  input.disabled = true;
  document.querySelector('#reset-chat').disabled = true;
  status.textContent = '사진의 유사 메뉴를 찾고 있습니다…';
  errorBox.hidden = true;
  try {
    // 2. 검색 실행: 성공하면 후보를 바탕으로 생성한 답변을 표시합니다.
    const response = await fetch('/chatbot/search', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text, sample: sample.value, session_id: sessionId})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '검색을 실행하지 못했습니다.');
    appendMessage('customer', `${text} (${sample.value})`);
    appendMessage('notice', data.state.answer.text);
    showSteps(data);
    await NotebookTrace.load('search', sessionId, steps, traceHistory).catch(() => {});
    status.textContent = '';
  } catch (error) {
    // 3. 실패 안내: 입력을 유지해 설정을 확인하고 다시 실행할 수 있게 합니다.
    errorBox.textContent = error.message;
    errorBox.hidden = false;
    status.textContent = '';
  } finally {
    // ## 요청 처리가 끝나면 입력 잠금과 실행 중 표시를 해제합니다.
    running = false;
    form.querySelector('button').disabled = false;
    sample.disabled = false;
    input.disabled = false;
    document.querySelector('#reset-chat').disabled = false;
  }
});

/** 새 대화에서 화면의 이전 검색 결과를 비웁니다. */
document.querySelector('#reset-chat').addEventListener('click', async () => {
  // 1. 화면 초기화: 처리 중에는 화면을 바꾸지 않습니다.
  if (running) {

    return;
  }
  await NotebookTrace.clear('search', sessionId);
  sessionId = NotebookTrace.newSession('search');
  showWelcome();
  NotebookTrace.render(steps, 'search');
  traceHistory.replaceChildren();
  document.querySelector('#flow-status').textContent = '사진을 선택하고 검색하면 결과가 표시됩니다.';
  errorBox.hidden = true;
  status.textContent = '';
});

loadSamples();
