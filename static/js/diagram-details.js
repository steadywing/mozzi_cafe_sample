// 흐름도의 도형을 선택하면 숨겨진 상세 설명을 HTML 팝업에 보여줍니다.
const diagram = document.querySelector('.service-diagram');
const popup = document.querySelector('#node-details');
const heading = popup.querySelector('h3');
const category = popup.querySelector('.node-details-kind');
const content = popup.querySelector('.node-details-content');
let activeNode = null;
let pinned = false;
let hideTimer;

/** 설명 팝업을 닫고, 선택한 도형과 고정 표시를 해제합니다. */
function hideDetails() {
  // 1. 닫기: 닫기 예약을 취소한 뒤 도형의 펼침 표시와 팝업을 함께 닫습니다.
  clearTimeout(hideTimer);
  if (activeNode) activeNode.setAttribute('aria-expanded', 'false');
  activeNode = null;
  pinned = false;
  popup.hidden = true;
}

/** 포인터가 도형을 벗어나면 0.2초 뒤 설명을 닫도록 예약하며, 고정한 설명은 유지합니다. */
function scheduleHide() {
  // 1. 예약: 도형에서 팝업으로 이동할 시간을 주되, 클릭으로 고정한 설명은 닫지 않습니다.
  clearTimeout(hideTimer);
  if (!pinned) hideTimer = setTimeout(hideDetails, 200);
}

/** 도형 안의 상세 설명을 읽어, 제목이 있는 항목과 일반 메모로 나누어 팝업에 넣습니다. */
function renderDetails(node) {
  // 1. 준비: 이전 설명을 비우고 제목·값을 담을 영역과 일반 메모 목록을 만듭니다.
  content.replaceChildren();
  const fields = document.createElement('dl');
  fields.className = 'node-detail-fields';
  const notes = document.createElement('ul');
  notes.className = 'node-detail-notes';

  /** 상세 설명 한 문장을 읽어, 콜론 앞의 제목이 있으면 항목으로, 없으면 메모로 나눕니다. */
  node.querySelectorAll('.sub').forEach((line) => {
    // 1. 문장 구분: 콜론 앞뒤를 제목과 내용으로 나누고, 제목이 없는 문장은 메모 목록에 넣습니다.
    const text = line.textContent.trim();
    const match = text.match(/^([^:：]{1,18})[:：]\s*(.*)$/s);
    if (!match) {
      const item = document.createElement('li');
      item.textContent = text;
      notes.append(item);

      return;
    }
    const row = document.createElement('div');

    // 2. 구성: 프롬프트 경로는 코드 모양으로, 더하기 기호로 연결된 입력은 목록으로 표시합니다.
    const label = document.createElement('dt');
    const value = document.createElement('dd');
    label.textContent = match[1].replace('프롬프트 파일', '프롬프트');
    if (match[1].includes('프롬프트')) {
      const code = document.createElement('code');
      code.textContent = match[2];
      value.append(code);
    } else if (match[2].includes(' + ')) {
      const list = document.createElement('ul');
      /** 더하기 기호로 나눈 입력 하나를 받아, 별도의 목록 항목으로 추가합니다. */
      match[2].split(' + ').forEach((part) => {
        // 1. 입력 표시: 입력 문자열을 목록 항목의 텍스트로 넣어 입력마다 한 줄씩 보여줍니다.
        const item = document.createElement('li');
        item.textContent = part;
        list.append(item);
      });
      value.append(list);
    } else {
      value.textContent = match[2];
    }

    // ## 제목과 값을 한 행으로 묶어 상세 목록에 추가합니다.
    row.append(label, value);
    fields.append(row);
  });


  // 2. 내용 표시: 제목이 있는 항목과 일반 메모가 있을 때만 팝업에 추가합니다.
  if (fields.children.length) content.append(fields);
  if (notes.children.length) content.append(notes);
}

/** 선택한 도형의 제목·설명을 팝업에 채우고, 화면 밖으로 나가지 않게 위치를 맞춥니다. */
function showDetails(node, pin = false) {
  // 1. 선택: 이전 선택 표시를 해제하고, 이번 도형의 종류·제목·상세 설명을 팝업에 넣습니다.
  clearTimeout(hideTimer);
  if (activeNode && activeNode !== node) activeNode.setAttribute('aria-expanded', 'false');
  activeNode = node;
  pinned = pin;
  node.setAttribute('aria-expanded', 'true');
  category.textContent = node.querySelector('.kind')?.textContent || '';
  popup.dataset.kind = node.dataset.kind;
  heading.textContent = node.querySelector('.title')?.textContent || '노드 상세';
  renderDetails(node);
  popup.hidden = false;

  // 2. 위치 계산: 흐름도와 바깥 페이지의 좌표를 합쳐 팝업 위치를 계산하고, 아래 공간이 부족하면 위에 놓습니다.
  const frame = diagram.getBoundingClientRect();
  const rect = node.getBoundingClientRect();
  const margin = 12;
  const left = Math.min(frame.left + rect.left, window.innerWidth - popup.offsetWidth - margin);
  let top = frame.top + rect.bottom + 8;
  if (top + popup.offsetHeight > window.innerHeight - margin) {
    top = frame.top + rect.top - popup.offsetHeight - 8;
  }
  popup.style.left = `${Math.max(margin, left)}px`;
  popup.style.top = `${Math.max(margin, top)}px`;
}

/** 흐름도가 로드되면 각 도형에 키보드·포인터 조작을 연결해 설명을 열고 닫을 수 있게 합니다. */
function connectDiagram() {
  // 1. 연결 확인: 흐름도 문서가 준비됐는지 확인하고, 이미 조작을 연결했다면 다시 연결하지 않습니다.
  const svg = diagram.contentDocument;
  if (!svg || svg.documentElement.dataset.detailsReady) {

    return;
  }
  svg.documentElement.dataset.detailsReady = 'true';

  // 2. 접근 준비: 흐름도를 도형의 묶음으로 알리고, 선택한 도형이 눈에 띄도록 테두리 스타일을 넣습니다.
  svg.documentElement.setAttribute('role', 'group');
  const style = svg.createElementNS('http://www.w3.org/2000/svg', 'style');
  style.textContent = 'g[data-kind]{cursor:pointer} g[data-kind]:focus{outline:none} g[data-kind]:focus > rect,g[data-kind]:hover > rect{stroke:#6c428a;stroke-width:3}';
  svg.documentElement.append(style);
  /** 설명이 있는 도형 하나를 받아, Tab으로 이동할 수 있는 버튼으로 설정합니다. */
  svg.querySelectorAll('g[data-kind]').forEach((node) => {
    // 1. 조작 준비: Tab 이동 순서·버튼 역할·접힘 상태·읽어 줄 이름을 도형에 지정합니다.
    node.setAttribute('tabindex', '0');
    node.setAttribute('role', 'button');
    node.setAttribute('aria-expanded', 'false');
    node.setAttribute('aria-label', [...node.querySelectorAll('text')].map((text) => text.textContent).join(' · '));
    /** 마우스 같은 포인터가 도형 위에 올라오면 설명을 열고, 터치는 클릭으로 처리합니다. */
    node.addEventListener('pointerenter', (event) => {
      // 1. 입력 장치 확인: 터치가 아닐 때만 설명을 열어, 터치 기기에서는 누르기 동작과 겹치지 않게 합니다.
      if (event.pointerType !== 'touch') showDetails(node);
    });

    // ## 포인터가 떠나거나 초점이 바뀌는 동작과 클릭 고정을 연결합니다.
    node.addEventListener('pointerleave', scheduleHide);
    node.addEventListener('focus', () => showDetails(node));
    node.addEventListener('blur', scheduleHide);
    node.addEventListener('click', () => showDetails(node, true));
    /** Enter나 스페이스를 누르면 선택한 도형의 설명을 고정해 읽을 수 있게 합니다. */
    node.addEventListener('keydown', (event) => {
      // 1. 키 확인: Enter와 스페이스만 처리하고, 기본 스크롤 대신 설명 고정을 실행합니다.
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        showDetails(node, true);
      }
    });
  });
  /** 흐름도에 초점이 있을 때 Escape를 누르면 열린 설명을 닫습니다. */
  svg.addEventListener('keydown', (event) => {
    // 1. 키 확인: 흐름도 문서에서 받은 키가 Escape일 때 팝업의 선택 상태를 해제합니다.
    if (event.key === 'Escape') hideDetails();
  });
  /** 흐름도의 도형이 아닌 빈 곳을 클릭하면 열린 설명을 닫습니다. */
  svg.addEventListener('click', (event) => {
    // 1. 클릭 위치 확인: 누른 요소가 설명 도형 안에 속하지 않으면 팝업을 닫습니다.
    if (!event.target.closest('g[data-kind]')) hideDetails();
  });
}

popup.addEventListener('pointerenter', () => clearTimeout(hideTimer));
popup.addEventListener('pointerleave', scheduleHide);
popup.addEventListener('focusin', () => clearTimeout(hideTimer));
popup.querySelector('button').addEventListener('click', hideDetails);
/** 바깥 페이지에서 Escape를 누르면 열린 설명 팝업을 닫습니다. */
document.addEventListener('keydown', (event) => {
  // 1. 키 확인: 바깥 문서에서 받은 키가 Escape일 때 팝업을 닫는 함수를 호출합니다.
  if (event.key === 'Escape') hideDetails();
});
/** 선택한 곳이 팝업 밖이면 팝업을 닫아 다른 화면을 볼 수 있게 합니다. */
document.addEventListener('pointerdown', (event) => {
  // 1. 선택 위치 확인: 팝업 안을 누른 경우는 유지하고, 그 밖을 눌렀을 때만 닫습니다.
  if (!popup.contains(event.target)) hideDetails();
});
window.addEventListener('resize', hideDetails);
/** 페이지 스크롤로 도형 위치가 바뀌면 설명을 닫고, 팝업 내부 스크롤은 허용합니다. */
window.addEventListener('scroll', (event) => {
  // 1. 스크롤 위치 확인: 팝업 내부에서 발생한 스크롤이면 설명을 유지하고, 다른 영역이면 닫습니다.
  if (!popup.contains(event.target)) hideDetails();
}, true);
diagram.addEventListener('load', connectDiagram);
connectDiagram();
