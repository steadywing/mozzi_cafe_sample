// 노트북 테스트 화면의 실제 실행 기록을 같은 형식으로 표시합니다.
window.NotebookTrace = (() => {
  const labels = {
    generate_unknown_response: '범위 밖 질문 답변',
    generate_order_draft: '주문 내용 추출', validate_order: '주문 조건 확인', handle_order: '주문 확정',
    generate_recommendation_conditions: '추천 조건 추출', filter_recommendation_menu: '메뉴 후보 필터', generate_recommendation_response: '추천 답변 생성',
    create_image_embedding: '사진·문장 임베딩', search_similar_menu: '유사 메뉴 검색', generate_search_response: '검색 답변 생성',
    generate_document_selection: '관련 문서 선택', load_cafe_documents: '카페 문서 읽기', generate_consultation_response: '근거 답변 생성',
    generate_receipt_data: '영수증 판독', validate_receipt: '주문 내역 검증', request_receipt_confirmation: '고객 확인 요청', add_receipt_points: '가상 포인트 적립', format_point_result: '적립 결과 안내',
    input: '고객 입력 준비', create_order_draft: '주문 초안 생성', match_menu_and_fill_prices: '메뉴·가격 확인',
    check_order: '필수 정보 확인', place_order: '모의 주문 접수', awaiting_revision: '수정 대기', response: '고객 응답 준비',
  };
  const plans = {
    unknown: ['generate_unknown_response'],
    order: ['generate_order_draft', 'validate_order', 'handle_order'],
    recommendation: ['generate_recommendation_conditions', 'filter_recommendation_menu', 'generate_recommendation_response'],
    search: ['create_image_embedding', 'search_similar_menu', 'generate_search_response'],
    consultation: ['generate_document_selection', 'load_cafe_documents', 'generate_consultation_response'],
    points: ['generate_receipt_data', 'validate_receipt', 'request_receipt_confirmation', 'add_receipt_points', 'format_point_result'],
    legacy_order: ['input', 'create_order_draft', 'match_menu_and_fill_prices', 'check_order', 'response'],
  };

  /** 긴 답변을 받아 흐름 카드에 맞는 한 줄 요약으로 줄여 돌려줍니다. */
  function brief(value) {
    // 1. 길이 조절: 대화의 전체 답변은 왼쪽에 두고 핵심 첫 부분만 표시합니다.
    const text = String(value || '').replace(/\s+/g, ' ').trim();

    return text.length > 140 ? `${text.slice(0, 137)}…` : text;
  }

  /** 저장된 단계 상태를 받아 단계의 핵심 결과를 짧은 문장으로 돌려줍니다. */
  function resultText(step) {
    // 1. 실행 확인: 아직 실행하지 않은 단계와 조건상 건너뛴 단계를 구분합니다.
    if (!step.state) return '실행하면 이 단계의 결과가 여기에 표시됩니다.';
    if (step.executed === false) return '이번 턴에서는 실행하지 않았습니다.';
    const state = step.state;
    const name = step.step;
    const answer = state.answer?.text || state.answer?.answer;

    // 2. 결과 요약: 각 기능에서 실제로 바뀐 값을 한 줄로 알려줍니다.
    if (name === 'generate_unknown_response') return brief(answer) || '범위 밖 질문의 응답을 만들었습니다.';
    if (name === 'input') return `고객 입력: ${brief(state.input?.text || '')}`;
    if (name === 'create_order_draft') return `주문 항목 ${state.order?.items?.length || 0}개를 추출했습니다.`;
    if (name === 'match_menu_and_fill_prices') return `메뉴 ${state.order?.items?.length || 0}개의 판매 정보와 가격을 확인했습니다.`;
    if (name === 'check_order') return brief(answer) || `주문 상태: ${state.order?.confirmation_status || '확인 중'}`;
    if (name === 'place_order') return `주문 상태: ${state.order?.confirmation_status || '확인 중'}${state.order?.order_id ? ` · ${state.order.order_id}` : ''}`;
    if (name === 'awaiting_revision') return brief(answer) || '고객의 수정 내용을 기다립니다.';
    if (name === 'response') return brief(answer) || '응답 상태를 저장했습니다.';
    if (name === 'generate_order_draft') return `주문 항목 ${state.order?.items?.length || 0}개를 추출했습니다.`;
    if (name === 'validate_order' || name === 'handle_order') return brief(answer) || `주문 상태: ${state.order?.confirmation_status || '확인 중'}`;
    if (name === 'generate_recommendation_conditions') return `알레르기 ${state.recommendation?.allergies?.length || 0}개 · 선호 ${state.recommendation?.preferences?.length || 0}개를 확인했습니다.`;
    if (name === 'filter_recommendation_menu') return `조건에 맞는 메뉴 ${state.recommendation?.candidate_menu_ids?.length ?? 0}개를 남겼습니다.`;
    if (name === 'create_image_embedding') return '선택한 사진과 문장을 검색용 벡터로 바꿨습니다.';
    if (name === 'search_similar_menu') return `유사 메뉴 ${state.search?.candidate_menu_ids?.length ?? 0}개를 찾았습니다.`;
    if (name === 'generate_document_selection') return `관련 문서 ${state.consultation?.selected_documents?.length ?? state.selected_documents?.length ?? 0}개를 선택했습니다.`;
    if (name === 'load_cafe_documents') return '선택한 카페 문서의 원문을 읽었습니다.';
    if (name === 'generate_receipt_data') return `영수증 ${state.receipt?.receipt_number || '정보'}를 읽었습니다.`;
    if (name === 'validate_receipt') return `검증 결과: ${state.receipt?.verification || '확인 중'}${state.receipt?.reason ? ` · ${state.receipt.reason}` : ''}`;
    if (name === 'request_receipt_confirmation') return brief(answer) || '적립 전 고객 확인을 기다립니다.';
    if (name === 'add_receipt_points') return `적립 상태: ${state.receipt?.status || '확인 중'} · 고객 포인트 ${state.customer?.points ?? '확인 중'}점`;
    if (answer) return brief(answer);

    return '단계 후 상태를 아래에서 확인할 수 있습니다.';
  }

  /** 이름과 값을 받아 펼쳐 볼 수 있는 실행 자료 영역을 만듭니다. */
  function detail(title, value) {
    // 1. 내용 구성: 서버가 반환한 실제 값을 텍스트로 넣습니다.
    const box = document.createElement('details');
    const heading = document.createElement('summary');
    const body = document.createElement('pre');
    heading.textContent = title;
    body.className = 'trace-block';
    body.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    box.append(heading, body);

    return box;
  }

  /** 실제 단계 또는 예정된 함수 이름을 받아 번호·결과·실행 자료를 표시합니다. */
  function stepRow(step, index) {
    // 1. 단계 제목: 한국어 역할과 실제 함수명을 번호 옆에 표시합니다.
    const row = document.createElement('li');
    const heading = document.createElement('div');
    const number = document.createElement('span');
    const title = document.createElement('h3');
    const code = document.createElement('code');
    heading.className = 'flow-heading';
    number.textContent = String(index + 1).padStart(2, '0');
    title.textContent = labels[step.step] || step.step;
    code.textContent = step.step;
    heading.append(number, title, code);
    const summary = document.createElement('p');
    summary.className = 'flow-summary';
    summary.textContent = resultText(step);
    row.append(heading, summary);

    // 2. 실제 자료: 모델 입력, 프롬프트, 단계 후 상태를 서로 다른 항목으로 보여줍니다.
    if (step.input !== undefined) row.append(detail(step.model ? '실제 모델 입력' : '단계 입력', step.input));
    else if (step.model_input !== undefined) row.append(detail('실제 모델 입력', step.model_input));
    else if (step.step === 'input' && step.state?.input) row.append(detail('이번 고객 입력', step.state.input));
    if (step.prompt !== undefined) row.append(detail('사용 프롬프트', step.prompt));
    if (step.output !== undefined) row.append(detail('단계 출력', step.output));
    if (step.questions !== undefined) row.append(detail('분류 질문', step.questions));
    if (step.model !== undefined) row.append(detail('사용 모델', step.model));
    if (step.state !== undefined) row.append(detail('단계 후 저장 상태', step.state));

    return row;
  }

  /** 기능 이름과 실행 단계를 받아 오른쪽 목록을 갱신합니다. */
  function render(target, feature, steps) {
    // 1. 흐름 구성: 실행 전에는 예정 함수 목록을, 실행 후에는 실제 단계를 표시합니다.
    const list = document.createElement('ol');
    list.className = 'flow-list';
    const items = steps?.length ? steps : (plans[feature] || []).map((name) => ({step: name}));
    items.forEach((step, index) => { list.append(stepRow(step, index)); });
    target.replaceChildren(list);
  }

  /** 한 세션의 이전 턴을 받아 접어서 조회할 수 있는 목록을 보여줍니다. */
  function renderHistory(target, feature, turns) {
    // 1. 기록 구성: 저장된 턴마다 단계 목록을 보존합니다.
    target.replaceChildren();
    turns.forEach((turn, index) => {
      const block = document.createElement('details');
      block.className = 'trace-turn';
      const heading = document.createElement('summary');
      heading.textContent = `${turn.turn_index || index + 1}번째 턴 · ${turn.steps?.length || 0}단계`;
      const body = document.createElement('div');
      render(body, feature, turn.steps);
      block.append(heading, body);
      target.append(block);
    });
  }

  /** 기능 이름에 해당하는 브라우저 세션 ID를 준비해 돌려줍니다. */
  function getSession(feature) {
    // 1. 식별자 준비: 새로 고친 화면에서도 같은 실습 기록을 조회합니다.
    const key = `notebook-${feature}-session`;
    let id = sessionStorage.getItem(key);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(key, id);
    }

    return id;
  }

  /** 새 대화에서 쓸 식별자를 만들고 이전 브라우저 식별자를 교체합니다. */
  function newSession(feature) {
    // 1. 식별자 교체: 다음 요청이 새 실행 기록으로 저장되게 합니다.
    const id = crypto.randomUUID();
    sessionStorage.setItem(`notebook-${feature}-session`, id);

    return id;
  }

  /** 서버에 저장된 턴을 읽어 최신 흐름과 이전 기록을 화면에 표시합니다. */
  async function load(feature, id, current, history) {
    // 1. 기록 조회: 현재 페이지의 기능과 세션에 한정한 기록을 읽습니다.
    const response = await fetch(`/test/api/traces/${feature}/${encodeURIComponent(id)}`);
    if (!response.ok) return [];
    const data = await response.json();
    const turns = data.turns || [];
    if (turns.length) render(current, feature, turns[turns.length - 1].steps);
    renderHistory(history, feature, turns.slice(0, -1));

    return turns;
  }

  /** 서버에 저장된 현재 실습 기록을 삭제합니다. */
  async function clear(feature, id) {
    // 1. 기록 삭제: 새 대화에서 이전 턴이 복원되지 않게 합니다.
    await fetch(`/test/api/traces/${feature}/${encodeURIComponent(id)}`, {method: 'DELETE'});
  }

  return {render, renderHistory, getSession, newSession, load, clear};
})();
