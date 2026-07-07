// 장비 프로젝트 레이더 - 클라이언트 로직
// data/announcements.json 을 읽어 분야/유형으로 필터링/그룹핑해서 렌더링한다.

const KEYWORDS = [
  "반도체 장비",
  "디스플레이 장비",
  "도금 장비",
];

const KEYWORD_ICONS = {
  "반도체 장비": "M9 2h6v2h-6zM9 20h6v2h-6zM2 9h2v6H2zM20 9h2v6h-2zM6 6h12v12H6z M9.5 9.5h5v5h-5z",
  "디스플레이 장비": "M3 4h18v13H3zM8 21h8M12 17v4",
  "도금 장비": "M12 3l7 4v6c0 4-3 6.5-7 8-4-1.5-7-4-7-8V7z M9 12l2 2 4-4",
};

const STORAGE_KEY = "g2b-alert-selected-keywords";

// source 값을 기준으로 원문 버튼 문구를 결정한다. 새 수집원이 추가되면
// 여기에 한 줄만 추가하면 되고, 없는 소스는 "{source} 원문 보기"로 자동 처리된다.
const SOURCE_LINK_LABELS = {
  KANC: "한국나노기술원 원문 보기",
  NNFC: "나노종합기술원 원문 보기",
};

const NOTICE_TYPE_LABELS = {
  "사전규격": { label: "사전규격", cls: "notice-type-prespec" },
  "정식입찰": { label: "정식입찰", cls: "notice-type-formal" },
};

const TYPE_FILTERS = ["전체", "사전규격", "정식입찰"];

const state = {
  selected: loadSelection(),
  typeFilter: "전체",
  data: { updatedAt: null, items: [] },
};

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
  row.innerHTML = TYPE_FILTERS.map((type) => {
    const active = state.typeFilter === type;
    return `<button type="button" class="chip chip-outline${active ? " chip-active" : ""}" data-type="${type}">${type}</button>`;
  }).join("");

  row.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.typeFilter = chip.dataset.type;
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
  const label = d === 0 ? "D-DAY" : d > 0 ? `D-${d}` : `D+${Math.abs(d)}`;
  let cls = "dday-blue";
  if (d <= 3) cls = "dday-red";
  else if (d <= 7) cls = "dday-orange";
  return `<span class="dday-badge ${cls}">${label}</span>`;
}

function topTags(item) {
  const tags = [`<span class="country-badge">${escapeHtml(item.country || "국가 미상")}</span>`];
  tags.push(`<span class="source-badge">${escapeHtml(item.sourceCode || item.source || "출처 미상")}</span>`);
  const noticeType = NOTICE_TYPE_LABELS[item.noticeType];
  if (noticeType) {
    tags.push(`<span class="notice-type-badge ${noticeType.cls}">${noticeType.label}</span>`);
  }
  return `<span class="notice-tags">${tags.join("")}</span>`;
}

function detailLinkLabel(item) {
  return SOURCE_LINK_LABELS[item.sourceCode] || `${item.source || "원문"} 원문 보기`;
}

function detailRow(label, value) {
  if (!value) return "";
  return `<div class="notice-detail-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`;
}

function renderAttachments(item) {
  if (!item.attachments || item.attachments.length === 0) return "";
  const links = item.attachments.map((a) =>
    `<li><a href="${a.url}" target="_blank" rel="noopener">${escapeHtml(a.name)}</a></li>`
  ).join("");
  return `
    <div class="detail-section">
      <h4>첨부파일</h4>
      <ul class="attachment-list">${links}</ul>
    </div>`;
}

function renderCard(item, kw) {
  const businessRows = [
    detailRow("예산", item.budget),
    detailRow("계약방식", item.contractMethod),
    detailRow("인도조건", item.deliveryCondition),
    detailRow("지급조건", item.paymentCondition),
  ].join("");

  return `
    <details class="notice-card">
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
            ${detailRow("국가", item.country)}
            ${detailRow("출처", item.source)}
            ${detailRow("발주기관", item.org)}
            ${detailRow("분야", kw)}
            ${detailRow("정보 유형", item.noticeType)}
          </dl>
        </div>
        <div class="detail-section">
          <h4>일정 정보</h4>
          <dl class="notice-detail-list">
            ${detailRow("등록일", item.postedDate || "확인 필요")}
            ${detailRow("마감일", item.dueDate || "마감일 확인 필요")}
          </dl>
        </div>
        ${businessRows ? `<div class="detail-section"><h4>사업 정보</h4><dl class="notice-detail-list">${businessRows}</dl></div>` : ""}
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

function renderResults() {
  const selectedList = [...state.selected];

  const groups = selectedList.map((kw) => {
    const items = state.data.items
      .filter((item) => item.keywords.includes(kw))
      .filter((item) => state.typeFilter === "전체" || item.noticeType === state.typeFilter)
      .sort((a, b) => daysUntil(a.dueDate) - daysUntil(b.dueDate));
    return { kw, items };
  }).filter((g) => g.items.length > 0);

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

function showScreen(name) {
  document.getElementById("screen-keywords").hidden = name !== "keywords";
  document.getElementById("screen-results").hidden = name !== "results";
  document.getElementById("filterBar").hidden = name !== "results";
  if (name === "results") {
    renderCategoryChips();
    renderTypeChips();
    renderResults();
  }
}

async function loadData() {
  try {
    const res = await fetch("data/announcements.json", { cache: "no-store" });
    state.data = await res.json();
  } catch (e) {
    console.error("공고 데이터를 불러오지 못했습니다.", e);
    state.data = { updatedAt: null, items: [] };
  }
  const updatedText = formatUpdatedAt(state.data.updatedAt);
  document.getElementById("updatedAt").innerHTML = `🔄 ${updatedText}`;
  document.getElementById("updatedAt2").innerHTML = `🔄 ${updatedText}`;
}

function init() {
  renderKeywordGrid();
  loadData();

  document.getElementById("viewResultsBtn").addEventListener("click", () => showScreen("results"));
  document.getElementById("backBtn").addEventListener("click", () => showScreen("keywords"));

  document.getElementById("telegramBtn").addEventListener("click", () => {
    alert("텔레그램 알림 연동은 다음 업데이트에서 제공될 예정입니다.");
  });
}

document.addEventListener("DOMContentLoaded", init);
