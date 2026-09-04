// 장비 프로젝트 레이더 - 클라이언트 로직
// data/announcements.json 을 읽어 분야/유형으로 필터링/그룹핑해서 렌더링한다.

const KEYWORDS = [
  "반도체 장비",
  "디스플레이 장비",
  "TGV 장비",
];

const KEYWORD_ICONS = {
  "반도체 장비": "M9 2h6v2h-6zM9 20h6v2h-6zM2 9h2v6H2zM20 9h2v6h-2zM6 6h12v12H6z M9.5 9.5h5v5h-5z",
  "디스플레이 장비": "M3 4h18v13H3zM8 21h8M12 17v4",
  "TGV 장비": "M12 3l7 4v6c0 4-3 6.5-7 8-4-1.5-7-4-7-8V7z M9 12l2 2 4-4",
};

const STORAGE_KEY = "g2b-alert-selected-keywords";

// 수집원의 한국어 정식 명칭. 화면에는 약어를 단독으로 두지 않고 한국어
// 이름과 함께 보여준다(약어만 보면 어디 공고인지 알 수 없다).
// 여기 값은 각 기관의 공식 한국어 명칭이며 추측 번역이 아니다.
const SOURCE_NAMES_KO = {
  KANC: "한국나노기술원",
  NNFC: "나노종합기술원",
  KRISS: "한국표준과학연구원",
  KAIST: "한국과학기술원",
  DGIST: "대구경북과학기술원",
  KOTRA: "대한무역투자진흥공사",
  JETRO: "일본무역진흥기구",
  ITRI: "대만 산업기술연구원",
  EBNEW: "중국 비롄왕",
  MOFCOM: "중국 국제입찰망",
};

// 카드 배지에 쓰는 짧은 표기. 자리가 좁아 한국어 이름을 다 넣기 어려우므로
// 국내 기관은 한국어 이름을, 해외 기관은 "한국어 이름(약어)"을 쓴다.
const SOURCE_BADGE_LABELS = {
  KANC: "한국나노기술원",
  NNFC: "나노종합기술원",
  KRISS: "표준과학연구원",
  KAIST: "한국과학기술원",
  DGIST: "대구경북과기원",
  KOTRA: "대한무역투자진흥공사",
  JETRO: "일본무역진흥기구",
  ITRI: "대만 산업기술연구원",
  EBNEW: "중국 비롄왕",
  MOFCOM: "중국 국제입찰망",
};

function sourceFullName(item) {
  const code = item.sourceCode;
  const ko = SOURCE_NAMES_KO[code];
  return ko ? `${ko}(${code})` : (item.source || code || "출처 미상");
}

function sourceBadgeLabel(item) {
  return SOURCE_BADGE_LABELS[item.sourceCode] || item.source || item.sourceCode || "출처 미상";
}

// 원문 버튼 문구. 한국어 기관명을 앞세우고 공식 약어는 괄호로만 남긴다.
// 새 수집원이 추가되면 여기에 한 줄만 추가하면 되고, 없는 소스는
// "원문 공고 보기"로 자동 처리된다.
const SOURCE_LINK_LABELS = {
  KANC: "한국나노기술원 원문 공고 보기",
  NNFC: "나노종합기술원 원문 공고 보기",
  KRISS: "한국표준과학연구원 원문 공고 보기",
  KOTRA: "대한무역투자진흥공사(KOTRA) 원문 공고 보기",
  EBNEW: "중국 비롄왕(EBNEW) 원문 공고 보기",
  MOFCOM: "중국 국제입찰망(MOFCOM) 원문 공고 보기",
  JETRO: "일본무역진흥기구(JETRO) 원문 공고 보기",
  DGIST: "대구경북과학기술원(DGIST) 원문 공고 보기",
  ITRI: "대만 산업기술연구원(ITRI) 원문 공고 보기",
  KAIST: "나라장터 원문 공고 보기",
};

const NOTICE_TYPE_LABELS = {
  "사전규격": { label: "사전규격", cls: "notice-type-prespec" },
  "정식입찰": { label: "정식입찰", cls: "notice-type-formal" },
  "프로젝트 정보": { label: "프로젝트 정보", cls: "notice-type-project" },
  "공급사 모집": { label: "공급사 모집", cls: "notice-type-project" },
  "수출상담회": { label: "수출상담회", cls: "notice-type-consult" },
  "구매상담회": { label: "구매상담회", cls: "notice-type-consult" },
  "낙찰·수주결과": { label: "낙찰·수주결과", cls: "notice-type-result" },
};

const TYPE_FILTERS = ["전체", "사전규격", "정식입찰", "프로젝트 정보", "공급사 모집", "수출상담회", "구매상담회", "낙찰·수주결과"];

// 국가명 -> 국기 이모지 (없는 국가는 이모지 없이 이름만 표시)
const COUNTRY_FLAGS = {
  "국내": "🇰🇷", "중국": "🇨🇳", "베트남": "🇻🇳", "인도": "🇮🇳", "미국": "🇺🇸",
  "일본": "🇯🇵", "독일": "🇩🇪", "대만": "🇹🇼", "태국": "🇹🇭", "인도네시아": "🇮🇩",
  "말레이시아": "🇲🇾", "멕시코": "🇲🇽", "브라질": "🇧🇷", "러시아": "🇷🇺",
  "싱가포르": "🇸🇬", "필리핀": "🇵🇭",
};

const state = {
  selected: loadSelection(),
  selectedNoticeTypes: new Set(), // 비어있으면 "전체"(모든 정보 유형 표시)
  showOnlyNew: false, // true면 NEW(48시간 이내 최초발견) 공고만 표시
  dueSoonOnly: false, // true면 D-7 이내 마감 공고만 표시(대시보드 "마감 임박" 카드용)
  region: "all", // "all" | "domestic" | "overseas" — 홈 대시보드 지역 필터, 공고 탭에도 함께 적용됨
  data: { updatedAt: null, items: [] },
};

// firstSeenAt(우리 시스템이 실제로 처음 발견한 시각) 기준 48시간 이내면
// NEW로 본다 — 공고의 등록일/마감일은 이 판단에 쓰지 않는다.
const NEW_BADGE_WINDOW_MS = 48 * 60 * 60 * 1000;
function isNewItem(item) {
  if (!item.firstSeenAt) return false;
  const seenTime = new Date(item.firstSeenAt).getTime();
  if (Number.isNaN(seenTime)) return false;
  return Date.now() - seenTime < NEW_BADGE_WINDOW_MS;
}

// --- 대시보드 공용 헬퍼 (기존 필터/렌더 로직은 그대로 두고 추가만 한다) ---

function matchesRegion(item) {
  if (state.region === "domestic") return item.country === "국내";
  if (state.region === "overseas") return !!item.country && item.country !== "국내";
  return true;
}

// 같은 공고가 여러 분야(keywords)에 속해 카드 목록에서는 여러 번 보일 수 있는데,
// 대시보드 KPI/통계는 "몇 건의 공고가 있는지"를 물어보는 것이므로 id 기준으로
// 한 번씩만 센다("중복 공고 제외" 요구사항).
function uniqueItems(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    if (!item.id || seen.has(item.id)) continue;
    seen.add(item.id);
    result.push(item);
  }
  return result;
}

// 마감되지 않은 공고(= "현재 확인 가능한 유효 공고"). dueDate가 없는 공고는
// 마감 여부를 알 수 없으므로 임의로 제외하지 않는다(기존 서버 로직과 동일 원칙).
function isValidOpen(item) {
  if (!item.dueDate) return true;
  return daysUntil(item.dueDate) >= 0;
}

// 홈 대시보드가 기준으로 삼는 "유효 공고" 집합: 중복 제외 + 마감 제외 + 지역 필터.
function getValidItems() {
  return uniqueItems(state.data.items).filter((item) => isValidOpen(item) && matchesRegion(item));
}

function loadSelection() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch (e) {}
  return new Set(KEYWORDS);
}

function saveSelection() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...state.selected]));
}

function iconSvg(keyword, size = 18) {
  const d = KEYWORD_ICONS[keyword] || "M4 4h16v16H4z";
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
}

function renderKeywordGrid() {
  const grid = document.getElementById("keywordGrid");
  grid.innerHTML = KEYWORDS.map((kw) => {
    const selected = state.selected.has(kw);
    return `
      <button type="button" class="keyword-card${selected ? " selected" : ""}" data-keyword="${kw}">
        <span class="checkbox">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
        </span>
        <span>${kw}</span>
      </button>`;
  }).join("");

  grid.querySelectorAll(".keyword-card").forEach((card) => {
    card.addEventListener("click", () => {
      const kw = card.dataset.keyword;
      if (state.selected.has(kw)) state.selected.delete(kw);
      else state.selected.add(kw);
      saveSelection();
      card.classList.toggle("selected");
    });
  });
}

function renderCategoryChips() {
  const row = document.getElementById("categoryChipRow");
  row.innerHTML = KEYWORDS.map((kw) => {
    const active = state.selected.has(kw);
    return `<button type="button" class="chip${active ? " chip-active" : ""}" data-category="${kw}">${kw}</button>`;
  }).join("");

  row.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const kw = chip.dataset.category;
      if (state.selected.has(kw)) state.selected.delete(kw);
      else state.selected.add(kw);
      saveSelection();
      renderCategoryChips();
      renderKeywordGrid();
      renderResults();
    });
  });
}

function renderTypeChips() {
  const row = document.getElementById("typeChipRow");
  const noneSelected = state.selectedNoticeTypes.size === 0;
  row.innerHTML = TYPE_FILTERS.map((type) => {
    const active = type === "전체" ? noneSelected : state.selectedNoticeTypes.has(type);
    return `<button type="button" class="chip chip-outline${active ? " chip-active" : ""}" data-type="${type}">${type}</button>`;
  }).join("");

  const countLabel = document.getElementById("typeFilterCount");
  if (countLabel) {
    countLabel.textContent = noneSelected ? "" : `${state.selectedNoticeTypes.size}개 유형 선택 중`;
  }

  row.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const type = chip.dataset.type;
      if (type === "전체") {
        state.selectedNoticeTypes.clear();
      } else if (state.selectedNoticeTypes.has(type)) {
        state.selectedNoticeTypes.delete(type);
      } else {
        state.selectedNoticeTypes.add(type);
      }
      renderTypeChips();
      renderResults();
    });
  });
}

function daysUntil(dateStr) {
  if (!dateStr) return Infinity; // 마감일 미상 공고는 정렬 시 맨 뒤로
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dateStr + "T00:00:00");
  return Math.round((due - today) / 86400000);
}

function ddayBadge(dateStr) {
  if (!dateStr) return `<span class="dday-badge dday-gray">마감일 확인 필요</span>`;
  const d = daysUntil(dateStr);
  if (d < 0) return `<span class="dday-badge dday-gray">마감</span>`;
  // 숫자형(D-3)은 그대로 두되, 영어 "D-DAY"만 한국어로 바꾼다.
  const label = d === 0 ? "오늘 마감" : `D-${d}`;
  let cls = "dday-blue";
  if (d <= 3) cls = "dday-red";
  else if (d <= 7) cls = "dday-orange";
  return `<span class="dday-badge ${cls}">${label}</span>`;
}

// 원문에서 가져온 status는 수집 시점 값이라 마감일이 지나도 "진행중"으로
// 남는다(마감돼도 계속 보여주는 KOTRA/EBNEW/MOFCOM에서 실제로 발생).
// 카드의 D-day 배지는 마감일 기준으로 "마감"을 표시하는데 상세의 상태만
// "진행중"이면 같은 카드 안에서 정보가 충돌하므로, 표시할 때 마감일을
// 우선한다. 데이터 파일 자체는 수정하지 않고 화면 표시만 보정한다.
function displayStatus(item) {
  if (item.dueDate && daysUntil(item.dueDate) < 0) return "마감";
  return item.status;
}

function topTags(item) {
  const flag = COUNTRY_FLAGS[item.country] || "";
  const countryLabel = flag ? `${flag} ${item.country}` : (item.country || "국가 미상");
  const tags = [`<span class="country-badge">${escapeHtml(countryLabel)}</span>`];
  if (item.sourceType === "China Site") {
    tags.push(`<span class="china-site-badge">🌐 중국 사이트</span>`);
  }
  tags.push(`<span class="source-badge" title="${escapeHtml(sourceFullName(item))}">${escapeHtml(sourceBadgeLabel(item))}</span>`);
  const noticeType = NOTICE_TYPE_LABELS[item.noticeType];
  if (noticeType) {
    tags.push(`<span class="notice-type-badge ${noticeType.cls}">${noticeType.label}</span>`);
  }
  // 번역이 불완전한 중국 공고(용어집에 없어 로마자 표기로 폴백된 경우)는
  // 제목만으로 내용을 알 수 없으므로, 원문 확인이 필요하다는 것을 알린다.
  // 원문 제목은 상세의 "원문(중국어)" 블록, 원문 링크는 하단 버튼에 그대로 있다.
  if (item.translationIncomplete) {
    tags.push(`<span class="translation-badge" title="자동 번역이 불완전한 부분이 있습니다. 아래 원문 공고 링크에서 확인하세요.">번역 미완료</span>`);
  }
  // 장비인지 확정하지 못한 공고 — 홈 "지금 확인할 공고"와 Telegram에서는
  // 빠지고, 목록에서는 이 배지를 달아 사용자가 직접 판단할 수 있게 한다.
  if (item.equipmentStatus === "검토 필요") {
    tags.push(`<span class="review-badge" title="${escapeHtml(item.equipmentReason || "장비 여부 확인이 필요합니다.")}">장비 여부 검토 필요</span>`);
  }
  if (isNewItem(item)) {
    tags.push(`<span class="new-badge">신규</span>`);
  }
  return `<span class="notice-tags">${tags.join("")}</span>`;
}

function detailLinkLabel(item) {
  return SOURCE_LINK_LABELS[item.sourceCode] || "원문 공고 보기";
}

function detailRow(label, value) {
  if (!value) return "";
  return `<div class="notice-detail-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`;
}

function detailRowWithFallback(label, value, fallback) {
  return `<div class="notice-detail-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value || fallback)}</dd></div>`;
}

// 첨부파일명에 한국어가 하나도 없으면(중국어·일본어·영어 파일명) 그대로
// 보여줘도 사용자가 무엇인지 알 수 없다. 뜻을 지어내지 않고 "첨부파일 N"으로
// 표시하되 확장자는 남겨 형식은 알 수 있게 한다. 원래 파일명은 링크의
// title 속성과 데이터에 그대로 남는다.
const HANGUL_RE = /[가-힣]/;

function attachmentLabel(name, index) {
  const raw = (name || "").trim();
  if (!raw) return `첨부파일 ${index + 1}`;
  if (HANGUL_RE.test(raw)) return raw;
  const ext = (raw.match(/\.([A-Za-z0-9]{1,5})$/) || [])[1];
  return ext ? `첨부파일 ${index + 1}.${ext.toLowerCase()}` : `첨부파일 ${index + 1}`;
}

function renderAttachments(item) {
  if (!item.attachments || item.attachments.length === 0) return "";
  const links = item.attachments.map((a, i) =>
    `<li><a href="${a.url}" target="_blank" rel="noopener" title="${escapeHtml(a.name || "")}">${escapeHtml(attachmentLabel(a.name, i))}</a></li>`
  ).join("");
  return `
    <div class="detail-section">
      <h4>첨부파일</h4>
      <ul class="attachment-list">${links}</ul>
    </div>`;
}

// 상세 화면은 한국어로만 채운다. 예전에는 여기에 "원문(중국어)" 블록을 두고
// 중국어·영어 제목과 발주처를 그대로 펼쳐 보여줬는데, 한국어 사용자에게는
// 읽을 수 없는 글자가 화면 절반을 차지하는 셈이었다.
//
// 원문 데이터는 지우지 않는다 — announcements.json의 originalTitle /
// originalOrg / originalSummary에 그대로 남아 있고, 원문이 필요한 사용자는
// 상세 하단의 "원문 공고 보기" 버튼으로 원 사이트에서 확인한다.
function originalTextBlock() {
  return "";
}

function renderCard(item, kw) {
  const businessRows = [
    detailRow("공고번호", item.projectNo || item.g2bBidNo),
    detailRow("수량", item.quantity),
    detailRowWithFallback("예산", item.budget, "예산 정보 없음"),
    detailRow("계약방식", item.contractMethod),
    detailRow("지급조건", item.paymentCondition),
    detailRow("자격조건", item.eligibility),
  ].join("");

  return `
    <details class="notice-card" data-notice-id="${escapeHtml(item.id || "")}">
      <summary class="notice-summary">
        <span class="notice-icon">${iconSvg(kw, 18)}</span>
        <span class="notice-body">
          ${topTags(item)}
          <p class="notice-title">${escapeHtml(item.title)}</p>
          <span class="notice-meta">
            <span>🏛 ${escapeHtml(item.org)}</span>
            <span>📅 마감일 ${item.dueDate || "확인 필요"}</span>
          </span>
        </span>
        ${ddayBadge(item.dueDate)}
        <span class="chevron">›</span>
      </summary>
      <div class="notice-detail">
        <div class="detail-section">
          <h4>기본 정보</h4>
          <dl class="notice-detail-list">
            ${detailRow("산업", item.industry)}
            ${detailRow("공정", item.process)}
            ${detailRow("장비명", item.equipmentName)}
            ${detailRow("국가", item.country)}
            ${detailRow("지역", item.region)}
            ${detailRow("출처", item.source)}
            ${detailRow("발주기관", item.org)}
            ${detailRow("분야", kw)}
            ${detailRow("정보 유형", item.noticeType)}
          </dl>
        </div>
        ${originalTextBlock(item)}
        <div class="detail-section">
          <h4>일정 정보</h4>
          <dl class="notice-detail-list">
            ${detailRow("등록일", item.postedDate || "확인 필요")}
            ${detailRow("마감일", item.dueDate || "마감일 확인 필요")}
            ${detailRow("이행기한 / 납기", item.deliveryCondition)}
            ${detailRow("행사 기간", item.eventPeriod)}
            ${detailRow("상태", displayStatus(item))}
          </dl>
        </div>
        ${businessRows ? `<div class="detail-section"><h4>공고 정보</h4><dl class="notice-detail-list">${businessRows}</dl></div>` : ""}
        <div class="detail-section">
          <h4>핵심 요약</h4>
          <p class="notice-detail-desc">${escapeHtml(item.description || "상세 설명이 제공되지 않았습니다.")}</p>
        </div>
        ${renderAttachments(item)}
        <a class="notice-detail-link" href="${item.url || "#"}" target="_blank" rel="noopener">
          ${detailLinkLabel(item)}
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M9 7h8v8"/></svg>
        </a>
      </div>
    </details>`;
}

// 수집기가 분야를 하나도 확정하지 못한 공고(classificationStatus:
// "미분류/검토 필요"). 분류 로직 자체는 건드리지 않고, 화면에서만 별도
// 그룹으로 노출한다.
const UNCLASSIFIED_LABEL = "기타 / 미분류";
function isUnclassified(item) {
  return !(item.keywords && item.keywords.length > 0);
}

// 분야 외 공통 필터(정보유형/신규/마감임박/지역). 분야 그룹과 미분류 그룹이
// 같은 기준으로 걸러지도록 한 곳에 모아둔다.
function passesCommonFilters(item) {
  if (state.selectedNoticeTypes.size > 0 && !state.selectedNoticeTypes.has(item.noticeType)) return false;
  if (state.showOnlyNew && !isNewItem(item)) return false;
  if (state.dueSoonOnly) {
    const d = item.dueDate ? daysUntil(item.dueDate) : null;
    if (d === null || d < 0 || d > 7) return false;
  }
  return matchesRegion(item);
}

function computeNewCount() {
  // 신규 공고 바에 표시할 건수 — 현재 선택된 분야/정보유형 필터는 그대로
  // 반영하고(그래야 바를 눌렀을 때 실제로 보이는 건수와 일치한다),
  // NEW 필터 자체는 적용하지 않은 상태에서 센다.
  const selectedList = [...state.selected];
  let count = 0;
  for (const kw of selectedList) {
    count += state.data.items.filter((item) =>
      (item.keywords || []).includes(kw) &&
      (state.selectedNoticeTypes.size === 0 || state.selectedNoticeTypes.has(item.noticeType)) &&
      matchesRegion(item) &&
      isNewItem(item)
    ).length;
  }
  // 미분류 그룹도 목록에 함께 표시되므로, 바에 적힌 건수와 실제로 보이는
  // 건수가 어긋나지 않게 여기서도 같이 센다.
  count += state.data.items.filter((item) =>
    isUnclassified(item) &&
    (state.selectedNoticeTypes.size === 0 || state.selectedNoticeTypes.has(item.noticeType)) &&
    matchesRegion(item) &&
    isNewItem(item)
  ).length;
  return count;
}

function updateNewAnnounceBar(count) {
  const bar = document.getElementById("newAnnounceBar");
  if (!bar) return;
  bar.hidden = false;
  if (count === 0) {
    bar.disabled = true;
    bar.classList.remove("active");
    bar.textContent = "새로운 공고 없음";
    return;
  }
  bar.disabled = false;
  bar.classList.toggle("active", state.showOnlyNew);
  bar.textContent = state.showOnlyNew
    ? `🆕 신규 공고 ${count}건 표시 중 · 전체 보기`
    : `🆕 신규 공고 ${count}건 보기`;
}

function renderResults() {
  const selectedList = [...state.selected];

  updateNewAnnounceBar(computeNewCount());

  const groups = selectedList.map((kw) => {
    const items = state.data.items
      .filter((item) => (item.keywords || []).includes(kw))
      .filter(passesCommonFilters)
      .sort((a, b) => daysUntil(a.dueDate) - daysUntil(b.dueDate));
    return { kw, items };
  }).filter((g) => g.items.length > 0);

  // 분야가 하나도 매칭되지 않은 공고(수집기가 "미분류/검토 필요"로 남긴 건)는
  // 어떤 분야 그룹에도 속하지 못해 화면에서 통째로 사라졌었다. 별도 그룹으로
  // 항상 마지막에 붙여, 모든 공고가 최소 한 번은 목록에 나오도록 한다.
  // (분야 칩 선택과 무관하게 표시한다 — 애초에 분야로 걸러낼 수 없는 항목이라
  //  분야 선택에 연동하면 다시 사라지기 때문이다.)
  const unclassified = state.data.items
    .filter(isUnclassified)
    .filter(passesCommonFilters)
    .sort((a, b) => daysUntil(a.dueDate) - daysUntil(b.dueDate));
  if (unclassified.length > 0) {
    groups.push({ kw: UNCLASSIFIED_LABEL, items: unclassified });
  }

  const totalCount = groups.reduce((sum, g) => sum + g.items.length, 0);
  document.getElementById("totalCount").textContent = `총 ${totalCount}건`;

  const container = document.getElementById("resultGroups");
  const empty = document.getElementById("emptyState");

  if (groups.length === 0) {
    container.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  container.innerHTML = groups.map(({ kw, items }) => `
    <section class="result-group">
      <div class="group-header">
        <div class="group-title">${iconSvg(kw, 16)} ${kw}</div>
        <span class="group-count">총 ${items.length}건</span>
      </div>
      <div class="card-list">
        ${items.map((item) => renderCard(item, kw)).join("")}
      </div>
    </section>
  `).join("");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function formatUpdatedAt(iso) {
  if (!iso) return "업데이트 정보 없음";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `마지막 업데이트 ${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ============================================================
// 대시보드(홈/통계/일정) — 전부 위의 기존 데이터/필터 헬퍼만 읽어서
// 집계·렌더링하는 추가 레이어다. 기존 검색/필터/카드/Telegram 로직은
// 여기서 호출만 하지, 내부를 바꾸지 않는다.
// ============================================================

function computeHomeStats() {
  const valid = getValidItems();
  const domestic = valid.filter((item) => item.country === "국내").length;
  const overseas = valid.length - domestic;

  const now = Date.now();
  const weekAgoMs = now - 7 * 24 * 60 * 60 * 1000;
  const newThisWeek = valid.filter((item) => {
    if (!item.firstSeenAt) return false;
    const t = new Date(item.firstSeenAt).getTime();
    return !Number.isNaN(t) && t >= weekAgoMs;
  }).length;

  const newItems = valid.filter(isNewItem);
  const dayAgoMs = now - 24 * 60 * 60 * 1000;
  const newToday = newItems.filter((item) => new Date(item.firstSeenAt).getTime() >= dayAgoMs).length;

  const dueSoon = valid.filter((item) => item.dueDate && daysUntil(item.dueDate) >= 0 && daysUntil(item.dueDate) <= 7);

  const byCategory = {};
  KEYWORDS.forEach((kw) => { byCategory[kw] = 0; });
  valid.forEach((item) => (item.keywords || []).forEach((kw) => {
    if (byCategory[kw] !== undefined) byCategory[kw] += 1;
  }));

  return { valid, domestic, overseas, newThisWeek, newCount: newItems.length, newToday, dueSoon, byCategory };
}

// 최근 N일 동안 firstSeenAt(최초발견) 기준 일자별 신규 공고 수 — Telegram
// 발송 기준과 동일한 firstSeenAt을 그대로 재사용한다.
function computeNewTrend(days) {
  const buckets = [];
  const base = new Date();
  base.setHours(0, 0, 0, 0);
  for (let i = days - 1; i >= 0; i -= 1) {
    const d = new Date(base);
    d.setDate(d.getDate() - i);
    buckets.push({ time: d.getTime(), count: 0, label: `${d.getMonth() + 1}/${d.getDate()}` });
  }
  const items = uniqueItems(state.data.items).filter(matchesRegion);
  items.forEach((item) => {
    if (!item.firstSeenAt) return;
    const d = new Date(item.firstSeenAt);
    d.setHours(0, 0, 0, 0);
    const bucket = buckets.find((b) => b.time === d.getTime());
    if (bucket) bucket.count += 1;
  });
  return buckets;
}

// 라이브러리 없이 순수 인라인 SVG로 그리는 작은 막대 차트.
function renderBarChart(buckets, opts = {}) {
  const width = opts.width || 320;
  const height = opts.height || 88;
  const gap = 5;
  const barWidth = (width - gap * (buckets.length - 1)) / buckets.length;
  const max = Math.max(1, ...buckets.map((b) => b.count));
  const bottomPad = 18;
  const bars = buckets.map((b, i) => {
    const barHeight = Math.round((b.count / max) * (height - bottomPad - 14));
    const x = i * (barWidth + gap);
    const y = height - bottomPad - barHeight;
    const showEveryLabel = buckets.length <= 10;
    return `
      <rect x="${x.toFixed(1)}" y="${y}" width="${barWidth.toFixed(1)}" height="${Math.max(barHeight, 2)}" rx="3" fill="var(--accent)"></rect>
      ${b.count > 0 ? `<text x="${(x + barWidth / 2).toFixed(1)}" y="${y - 4}" font-size="9" font-weight="700" fill="var(--navy)" text-anchor="middle">${b.count}</text>` : ""}
      ${showEveryLabel ? `<text x="${(x + barWidth / 2).toFixed(1)}" y="${height - 5}" font-size="8.5" fill="var(--text-muted)" text-anchor="middle">${escapeHtml(b.label)}</text>` : ""}
    `;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="기간별 신규 공고 추이 차트">${bars}</svg>`;
}

// 라이브러리 없이 순수 인라인 SVG로 그리는 작은 도넛 차트.
function renderDonutChart(segments, opts = {}) {
  const size = opts.size || 108;
  const stroke = opts.stroke || 15;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) {
    return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}"><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--border)" stroke-width="${stroke}"></circle></svg>`;
  }
  let offset = 0;
  const circles = segments.filter((s) => s.value > 0).map((seg) => {
    const dash = (seg.value / total) * circumference;
    const circle = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${seg.color}" stroke-width="${stroke}" stroke-dasharray="${dash.toFixed(1)} ${(circumference - dash).toFixed(1)}" stroke-dashoffset="${(-offset).toFixed(1)}" transform="rotate(-90 ${cx} ${cy})"></circle>`;
    offset += dash;
    return circle;
  }).join("");
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="분야별 비중 도넛 차트">
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--border)" stroke-width="${stroke}"></circle>
    ${circles}
  </svg>`;
}

function renderDonutLegend(segments) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  return `<ul class="chart-legend">${segments.map((s) => {
    const pct = total > 0 ? Math.round((s.value / total) * 100) : 0;
    return `<li><span class="legend-dot" style="background:${s.color}"></span>${escapeHtml(s.label)} <b>${s.value}건</b> <span class="legend-pct">${pct}%</span></li>`;
  }).join("")}</ul>`;
}

// 국내/해외처럼 2개 값 비교는 도넛보다 가로 비율 바가 더 즉각적으로 읽힌다.
function renderRegionBar(domestic, overseas) {
  const total = domestic + overseas;
  const domPct = total > 0 ? Math.round((domestic / total) * 100) : 0;
  const overPct = 100 - domPct;
  return `
    <div class="region-bar">
      <div class="region-bar-fill" style="width:${total > 0 ? domPct : 50}%"></div>
    </div>
    <div class="region-bar-legend">
      <span><span class="legend-dot" style="background:var(--navy)"></span>국내 <b>${domestic}건</b> (${domPct}%)</span>
      <span><span class="legend-dot" style="background:var(--accent-soft)"></span>해외 <b>${overseas}건</b> (${overPct}%)</span>
    </div>`;
}

function computeSpotlightItems(validItems, limit = 5) {
  // "검토 필요"(장비인지 확정하지 못한 공고)는 홈 상단에 올리지 않는다.
  // 공고 탭에서는 배지를 달아 그대로 볼 수 있다.
  const scored = validItems
    .filter((item) => item.equipmentStatus !== "검토 필요")
    .map((item) => {
    let priority = 3; // 일반 공고
    const d = item.dueDate ? daysUntil(item.dueDate) : null;
    if (isNewItem(item)) priority = 0;
    else if (d !== null && d >= 0 && d <= 3) priority = 1;
    else if (d !== null && d >= 0 && d <= 7) priority = 2;
    return { item, priority, d: d === null ? Infinity : d };
  });
  scored.sort((a, b) => a.priority - b.priority || a.d - b.d);
  return scored.slice(0, limit).map((s) => s.item);
}

function renderSpotlightCard(item) {
  const flag = COUNTRY_FLAGS[item.country] || "";
  const kw = (item.keywords && item.keywords[0]) || "";
  // 예전에는 이 카드가 외부 원문 사이트로 바로 이동했다. 사용자가 우리
  // 레이더의 상세 정보를 보지 못하고 나가버려서, 공고 탭의 같은 상세보기로
  // 들어가도록 바꿨다(원문 이동은 상세 하단의 "원문 보기" 버튼에서 한다).
  return `
    <button type="button" class="spotlight-card" data-notice-id="${escapeHtml(item.id || "")}">
      <span class="spotlight-badges">
        ${isNewItem(item) ? '<span class="new-badge">신규</span>' : ""}
        ${ddayBadge(item.dueDate)}
      </span>
      <span class="spotlight-title">${escapeHtml(item.title)}</span>
      <span class="spotlight-meta">${escapeHtml(flag ? `${flag} ${item.country}` : (item.country || "국가 미상"))} · ${escapeHtml(kw || "분야 미상")}</span>
    </button>`;
}

// 홈/일정 화면의 카드에서 공고 탭의 해당 상세로 이동한다.
// 현재 필터 때문에 목록에 없으면 필터를 풀고 다시 그린 뒤 찾아간다.
function openNoticeDetail(noticeId) {
  if (!noticeId) return;
  showTab("tenders");
  const reveal = () => {
    const card = document.querySelector(`.notice-card[data-notice-id="${CSS.escape(noticeId)}"]`);
    if (!card) return false;
    card.open = true;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("notice-card-focus");
    setTimeout(() => card.classList.remove("notice-card-focus"), 2000);
    return true;
  };
  if (reveal()) return;
  // 현재 필터(분야/지역/유형/신규/마감임박) 때문에 목록에 없을 수 있다.
  // 그 공고가 보이도록 필터를 풀고 다시 그린 뒤 찾아간다.
  const target = (state.data.items || []).find((i) => i.id === noticeId);
  if (target) {
    (target.keywords || []).forEach((kw) => state.selected.add(kw));
  }
  state.region = "all";
  state.showOnlyNew = false;
  state.dueSoonOnly = false;
  state.selectedNoticeTypes.clear();
  renderCategoryChips();
  renderTypeChips();
  renderResults();
  setTimeout(reveal, 0);
}

function renderHome() {
  const stats = computeHomeStats();

  document.querySelectorAll(".region-chip").forEach((chip) => {
    chip.classList.toggle("chip-active", chip.dataset.region === state.region);
  });

  document.getElementById("kpiHeroCard").innerHTML = `
    <p class="kpi-hero-label">현재 유효 공고</p>
    <p class="kpi-hero-value">${stats.valid.length}<span>건</span></p>
    <p class="kpi-hero-sub">국내 ${stats.domestic} · 해외 ${stats.overseas}</p>
    <p class="kpi-hero-delta">이번 주 +${stats.newThisWeek}건</p>
  `;

  document.getElementById("kpiMiniRow").innerHTML = `
    <button type="button" class="kpi-mini-card" id="kpiNewCard">
      <span class="kpi-mini-label">신규 공고</span>
      <span class="kpi-mini-value">${stats.newCount}건</span>
      <span class="kpi-mini-sub">오늘 +${stats.newToday}</span>
    </button>
    <button type="button" class="kpi-mini-card kpi-mini-warn" id="kpiDueSoonCard">
      <span class="kpi-mini-label">마감 임박</span>
      <span class="kpi-mini-value">${stats.dueSoon.length}건</span>
      <span class="kpi-mini-sub">D-7 이내</span>
    </button>
  `;
  document.getElementById("kpiNewCard").addEventListener("click", () => {
    state.showOnlyNew = true;
    state.dueSoonOnly = false;
    showTab("tenders");
  });
  document.getElementById("kpiDueSoonCard").addEventListener("click", () => {
    state.dueSoonOnly = true;
    state.showOnlyNew = false;
    showTab("tenders");
  });

  document.getElementById("homeTrendChart").innerHTML = renderBarChart(computeNewTrend(7));

  document.getElementById("categoryStatsRow").innerHTML = KEYWORDS.map((kw) => `
    <button type="button" class="stat-mini-card" data-goto-category="${escapeHtml(kw)}">
      <span class="stat-mini-label">${escapeHtml(kw)}</span>
      <span class="stat-mini-value">${stats.byCategory[kw] || 0}건</span>
    </button>
  `).join("");
  document.querySelectorAll("[data-goto-category]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selected = new Set([btn.dataset.gotoCategory]);
      saveSelection();
      showTab("tenders");
    });
  });

  document.getElementById("regionStatsBar").innerHTML = renderRegionBar(stats.domestic, stats.overseas);

  const spotlight = computeSpotlightItems(stats.valid, 5);
  document.getElementById("spotlightList").innerHTML = spotlight.length
    ? spotlight.map(renderSpotlightCard).join("")
    : `<p class="empty-state">표시할 공고가 없습니다.</p>`;

  const updatedText = formatUpdatedAt(state.data.updatedAt);
  document.getElementById("updatedAtHome").innerHTML = `🔄 ${updatedText}`;
}

function computeCalendarDueMap() {
  const map = {};
  uniqueItems(state.data.items).forEach((item) => {
    if (!item.dueDate) return; // 마감일 없는 공고는 캘린더에서 제외
    if (!map[item.dueDate]) map[item.dueDate] = [];
    map[item.dueDate].push(item);
  });
  return map;
}

function pad2(n) { return String(n).padStart(2, "0"); }
function dateKey(y, m, d) { return `${y}-${pad2(m + 1)}-${pad2(d)}`; }

function renderCalendar() {
  const dueMap = computeCalendarDueMap();
  const cursor = state.calendarMonth || new Date();
  state.calendarMonth = cursor;
  const year = cursor.getFullYear();
  const month = cursor.getMonth();

  document.getElementById("calMonthLabel").textContent = `${year}년 ${month + 1}월`;

  const firstDay = new Date(year, month, 1);
  const startWeekday = firstDay.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const todayKey = dateKey(new Date().getFullYear(), new Date().getMonth(), new Date().getDate());

  const cells = [];
  for (let i = 0; i < startWeekday; i += 1) cells.push("<div class=\"cal-cell cal-cell-empty\"></div>");
  for (let d = 1; d <= daysInMonth; d += 1) {
    const key = dateKey(year, month, d);
    const dayItems = dueMap[key] || [];
    let urgency = "";
    if (dayItems.length) {
      const minD = Math.min(...dayItems.map((it) => daysUntil(it.dueDate)));
      if (minD <= 3) urgency = "cal-urgent";
      else if (minD <= 7) urgency = "cal-soon";
      else urgency = "cal-normal";
    }
    const isToday = key === todayKey ? "cal-today" : "";
    const isSelected = key === state.calendarSelectedDate ? "cal-selected" : "";
    cells.push(`
      <button type="button" class="cal-cell ${urgency} ${isToday} ${isSelected}" data-date="${key}">
        <span class="cal-day-num">${d}</span>
        ${dayItems.length ? `<span class="cal-day-dot">${dayItems.length}</span>` : ""}
      </button>
    `);
  }

  document.getElementById("calendarGrid").innerHTML = cells.join("");
  document.querySelectorAll(".cal-cell[data-date]").forEach((cell) => {
    cell.addEventListener("click", () => {
      state.calendarSelectedDate = cell.dataset.date === state.calendarSelectedDate ? null : cell.dataset.date;
      renderCalendar();
    });
  });

  const listEl = document.getElementById("calendarDayList");
  if (!state.calendarSelectedDate) {
    listEl.innerHTML = "";
    return;
  }
  const dayItems = dueMap[state.calendarSelectedDate] || [];
  listEl.innerHTML = `
    <h3 class="dash-card-title">${escapeHtml(state.calendarSelectedDate)} 마감 (${dayItems.length}건)</h3>
    <div class="spotlight-list">
      ${dayItems.map(renderSpotlightCard).join("") || '<p class="empty-state">마감 공고가 없습니다.</p>'}
    </div>`;
}

function renderStats() {
  const all = uniqueItems(state.data.items).filter(isValidOpen);

  document.getElementById("statsTrend7").innerHTML = renderBarChart(computeNewTrend(7));
  document.getElementById("statsTrend30").innerHTML = renderBarChart(computeNewTrend(30), { height: 90 });

  const catColors = { "반도체 장비": "var(--navy)", "디스플레이 장비": "var(--accent)", "TGV 장비": "var(--accent-soft)" };
  const byCategory = KEYWORDS.map((kw) => ({
    label: kw,
    value: all.filter((item) => (item.keywords || []).includes(kw)).length,
    color: catColors[kw],
  }));
  document.getElementById("statsCategoryDonut").innerHTML = `
    ${renderDonutChart(byCategory)}
    ${renderDonutLegend(byCategory)}
  `;

  const domestic = all.filter((item) => item.country === "국내").length;
  document.getElementById("statsRegionBar").innerHTML = renderRegionBar(domestic, all.length - domestic);

  const noticeTypeCounts = {};
  all.forEach((item) => {
    const t = item.noticeType || "미상";
    noticeTypeCounts[t] = (noticeTypeCounts[t] || 0) + 1;
  });
  document.getElementById("statsNoticeType").innerHTML = renderBarList(noticeTypeCounts);

  const sourceCounts = {};
  all.forEach((item) => {
    const s = item.sourceCode || "미상";
    sourceCounts[s] = (sourceCounts[s] || 0) + 1;
  });
  document.getElementById("statsBySource").innerHTML = renderBarList(sourceCounts);
}

function renderBarList(countsByLabel) {
  const entries = Object.entries(countsByLabel).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return entries.map(([label, value]) => `
    <div class="bar-list-row">
      <span class="bar-list-label">${escapeHtml(label)}</span>
      <span class="bar-list-track"><span class="bar-list-fill" style="width:${Math.round((value / max) * 100)}%"></span></span>
      <span class="bar-list-value">${value}</span>
    </div>
  `).join("");
}

const TABS = ["home", "tenders", "stats", "calendar", "settings"];
function showTab(tab) {
  TABS.forEach((t) => {
    const el = document.getElementById(`screen-${t}`);
    if (el) el.hidden = t !== tab;
  });
  document.getElementById("filterBar").hidden = tab !== "tenders";
  document.querySelectorAll(".bottom-nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });

  if (tab === "tenders") {
    renderCategoryChips();
    renderTypeChips();
    renderResults();
  } else if (tab === "home") {
    renderHome();
  } else if (tab === "stats") {
    renderStats();
  } else if (tab === "calendar") {
    renderCalendar();
  } else if (tab === "settings") {
    renderKeywordGrid();
  }
}

// 수집이 실패한 출처가 있으면 헤더에 경고를 띄운다 — 실패해도 그 출처의
// 이전 수집분이 화면에 그대로 남기 때문에, 표시가 없으면 낡은 데이터를
// 최신으로 오해하게 된다. 정상일 때는 아무것도 표시하지 않는다.
// 헤더의 "데이터 출처 N곳" 표기를 실제 활성 수집원 수로 채운다.
// sourceHealth의 키가 곧 이번 실행에 등록돼 돌아간 수집원 목록이라,
// 수집원을 추가·제거해도 화면 숫자를 따로 고칠 필요가 없다.
function renderSourceSummary() {
  const el = document.getElementById("sourceSummary");
  if (!el) return;
  const codes = Object.keys(state.data.sourceHealth || {});
  if (codes.length === 0) return; // 데이터 로드 실패 시 기본 문구 유지
  // 약어 대신 한국어 기관명을 보여준다(약어만 보면 어디인지 알 수 없다).
  const preview = codes.slice(0, 2)
    .map((c) => SOURCE_BADGE_LABELS[c] || c)
    .join(" · ");
  const rest = codes.length - 2;
  el.innerHTML = `데이터 출처 ${codes.length}곳 · ${escapeHtml(preview)}`
    + (rest > 0 ? ` <span class="source-more">+${rest}</span>` : "");
}

function renderSourceHealth() {
  const el = document.getElementById("sourceHealthNotice");
  if (!el) return;
  const health = state.data.sourceHealth || {};
  // 배너는 정기 수집(scheduled) 기준 상태만 보여준다. 검증하려고 손으로 돌린
  // 실행에서 난 실패까지 띄우면 사용자에게는 실제 장애와 구분되지 않는다
  // (No.018에서 수동 실행 3회 연속 timeout이 실제 장애 알림까지 갔다).
  // 수동 실행 실패는 sourceHealth와 Actions 로그에 그대로 남는다.
  const failing = Object.entries(health).filter(
    ([, h]) => h && h.ok === false && h.lastRunMode !== "manual-validation");
  if (failing.length === 0) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  const rows = failing.map(([code, h]) => {
    const last = h.lastSuccessAt ? formatUpdatedAt(h.lastSuccessAt).replace("마지막 업데이트 ", "") : "기록 없음";
    return `<span class="health-row"><b>${escapeHtml(code)}</b> 마지막 정상 수집: ${escapeHtml(last)}</span>`;
  }).join("");
  el.hidden = false;
  el.innerHTML = `<span class="health-head">⚠ 수집 장애 ${failing.length}곳</span>${rows}`
    + `<span class="health-note">※ 해당 출처는 기존 수집 데이터를 표시 중입니다.</span>`;
}

async function loadData() {
  try {
    const res = await fetch("data/announcements.json", { cache: "no-store" });
    state.data = await res.json();
    // 공통 장비 판정에서 "제외"로 분류된 공고(재료·부품·소모품·용역·공사 등)는
    // 화면에 올리지 않는다. 데이터 파일에는 남겨 둔다 — 지우면 id가 사라져
    // 다음 수집에서 다시 신규 공고로 잡히기 때문이다.
    const rawItems = state.data.items || [];
    state.data.excludedItems = rawItems.filter((i) => i.equipmentStatus === "제외");
    state.data.items = rawItems.filter((i) => i.equipmentStatus !== "제외");
  } catch (e) {
    console.error("공고 데이터를 불러오지 못했습니다.", e);
    state.data = { updatedAt: null, items: [] };
  }
  const updatedText = formatUpdatedAt(state.data.updatedAt);
  document.getElementById("updatedAt").innerHTML = `🔄 ${updatedText}`;
  document.getElementById("updatedAt2").innerHTML = `🔄 ${updatedText}`;
  renderSourceSummary();
  renderSourceHealth();
  // 데이터가 늦게 도착해도 현재 보고 있는 탭을 다시 그려 숫자/차트를 채운다.
  const active = document.querySelector(".bottom-nav-item.active");
  showTab(active ? active.dataset.tab : "home");
}

function init() {
  renderKeywordGrid();
  loadData();

  document.getElementById("viewResultsBtn").addEventListener("click", () => showTab("tenders"));
  document.getElementById("viewAllTendersBtn").addEventListener("click", () => showTab("tenders"));

  document.getElementById("newAnnounceBar").addEventListener("click", () => {
    state.showOnlyNew = !state.showOnlyNew;
    renderResults();
  });

  document.getElementById("telegramBtn").addEventListener("click", () => {
    alert("텔레그램 알림은 이미 자동으로 연결되어 있습니다 — 설정에서 알림 받을 분야를 선택하면 신규 공고가 발견될 때마다 전송됩니다.");
  });

  document.querySelectorAll(".bottom-nav-item").forEach((btn) => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });

  document.querySelectorAll(".region-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.region = chip.dataset.region;
      document.querySelectorAll(".region-chip").forEach((c) => c.classList.toggle("chip-active", c === chip));
      renderHome();
    });
  });

  document.getElementById("calPrevBtn").addEventListener("click", () => {
    const c = state.calendarMonth || new Date();
    state.calendarMonth = new Date(c.getFullYear(), c.getMonth() - 1, 1);
    state.calendarSelectedDate = null;
    renderCalendar();
  });
  document.getElementById("calNextBtn").addEventListener("click", () => {
    const c = state.calendarMonth || new Date();
    state.calendarMonth = new Date(c.getFullYear(), c.getMonth() + 1, 1);
    state.calendarSelectedDate = null;
    renderCalendar();
  });

  document.addEventListener("click", (e) => {
    const card = e.target.closest(".spotlight-card[data-notice-id]");
    if (card) openNoticeDetail(card.dataset.noticeId);
  });

  showTab("home");
}

document.addEventListener("DOMContentLoaded", init);
