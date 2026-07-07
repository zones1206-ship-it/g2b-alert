// 나라장터 공고 알리미 - 클라이언트 로직
// data/announcements.json 을 읽어 키워드로 필터링/그룹핑해서 렌더링한다.

const KEYWORDS = [
  "반도체 장비",
  "세정 설비",
  "디스플레이 장비",
  "트롤리",
  "자동화 설비",
  "검사 장비",
  "클린룸",
  "이송 시스템",
];

const KEYWORD_ICONS = {
  "반도체 장비": "M9 2h6v2h-6zM9 20h6v2h-6zM2 9h2v6H2zM20 9h2v6h-2zM6 6h12v12H6z M9.5 9.5h5v5h-5z",
  "세정 설비": "M12 2s6 7 6 12a6 6 0 0 1-12 0c0-5 6-12 6-12z",
  "디스플레이 장비": "M3 4h18v13H3zM8 21h8M12 17v4",
  "트롤리": "M4 5h13l2 8H6zM6 13v5M17 13v5M6 20a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM17 20a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
  "자동화 설비": "M12 2a3 3 0 0 1 3 3v1h-6V5a3 3 0 0 1 3-3zM7 8h10v13H7z M10 12h4v4h-4z",
  "검사 장비": "M11 3a8 8 0 1 0 5.3 14.1l4.3 4.3 1.4-1.4-4.3-4.3A8 8 0 0 0 11 3zM11 6v5l3 3",
  "클린룸": "M4 4h16v16H4zM4 10h16M10 4v16",
  "이송 시스템": "M3 12h14M13 6l4 6-4 6M5 6l-2 6 2 6",
};

const STORAGE_KEY = "g2b-alert-selected-keywords";

const state = {
  selected: loadSelection(),
  data: { updatedAt: null, items: [] },
};

function loadSelection() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return new Set(JSON.parse(raw));
  } catch (e) {}
  return new Set(["반도체 장비", "세정 설비", "디스플레이 장비"]);
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

function daysUntil(dateStr) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dateStr + "T00:00:00");
  return Math.round((due - today) / 86400000);
}

function ddayBadge(dateStr) {
  const d = daysUntil(dateStr);
  const label = d === 0 ? "D-DAY" : d > 0 ? `D-${d}` : `D+${Math.abs(d)}`;
  let cls = "dday-blue";
  if (d <= 3) cls = "dday-red";
  else if (d <= 7) cls = "dday-orange";
  return `<span class="dday-badge ${cls}">${label}</span>`;
}

function renderResults() {
  const selectedList = [...state.selected];
  document.getElementById("selectedKeywordsText").textContent = selectedList.length
    ? selectedList.join(" · ")
    : "선택 없음";

  const groups = selectedList.map((kw) => {
    const items = state.data.items
      .filter((item) => item.keywords.includes(kw))
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
        ${items.map((item) => `
          <details class="notice-card">
            <summary class="notice-summary">
              <span class="notice-icon">${iconSvg(kw, 18)}</span>
              <span class="notice-body">
                <p class="notice-title">${escapeHtml(item.title)}</p>
                <span class="notice-meta">
                  <span>🏛 ${escapeHtml(item.org)}</span>
                  <span>📅 마감일 ${item.dueDate}</span>
                </span>
              </span>
              ${ddayBadge(item.dueDate)}
              <span class="chevron">›</span>
            </summary>
            <div class="notice-detail">
              <dl class="notice-detail-list">
                <div class="notice-detail-row">
                  <dt>예산</dt>
                  <dd>${escapeHtml(item.budget || "정보 없음")}</dd>
                </div>
                <div class="notice-detail-row">
                  <dt>참가자격</dt>
                  <dd>${escapeHtml(item.eligibility || "정보 없음")}</dd>
                </div>
              </dl>
              <p class="notice-detail-desc">${escapeHtml(item.description || "상세 설명이 제공되지 않았습니다.")}</p>
              <a class="notice-detail-link" href="${item.url || "https://www.g2b.go.kr"}" target="_blank" rel="noopener">
                나라장터 원본 공고 보기
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M9 7h8v8"/></svg>
              </a>
            </div>
          </details>`).join("")}
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
  if (name === "results") renderResults();
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
  document.getElementById("editKeywordsBtn").addEventListener("click", () => showScreen("keywords"));

  document.getElementById("telegramBtn").addEventListener("click", () => {
    alert("텔레그램 알림 연동은 다음 업데이트에서 제공될 예정입니다.");
  });
}

document.addEventListener("DOMContentLoaded", init);
