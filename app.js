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
const LOCALE_STORAGE_KEY = "g2b-alert-locale";
const PROCESS_UNKNOWN = "__unknown__";

const UI = {
  ko: {
    all: "전체", processAll: "공정 전체", processUnknown: "공정 미분류",
    selectedFilters: (types, processes) => `유형 ${types}개 · 공정 ${processes}개 선택 중`,
    total: (n) => `총 ${n}건`, count: (n) => `${n}건`,
    deadline: "마감", deadlineUnknown: "마감일 확인 필요", closed: "마감", dueToday: "오늘 마감",
    countryUnknown: "국가 미상", translationIncomplete: "번역 덜 됨", reviewNeeded: "장비인지 확인 필요",
    new: "신규", basic: "기본 정보", schedule: "일정 정보", noticeInfo: "공고 정보",
    summary: "핵심 요약", attachments: "첨부파일", sourceLink: "원문 공고 보기",
    noDescription: "상세 설명이 제공되지 않았습니다.", noBudget: "예산 정보 없음",
    noDeadline: "확인 필요", noApplicable: "해당 없음", preDeadline: "마감 전(수집 기준)",
    koreanFallback: "한국어 번역", originalEnglish: "영문 원문",
  },
  en: {
    all: "All", processAll: "All processes", processUnknown: "Unclassified process",
    selectedFilters: (types, processes) => `${types} notice type(s) · ${processes} process(es) selected`,
    total: (n) => `${n} total`, count: (n) => `${n}`,
    deadline: "Deadline", deadlineUnknown: "Check deadline", closed: "Closed", dueToday: "Due today",
    countryUnknown: "Unknown country", translationIncomplete: "Translation incomplete", reviewNeeded: "Review equipment match",
    new: "NEW", basic: "Overview", schedule: "Schedule", noticeInfo: "Commercial details",
    summary: "Summary", attachments: "Attachments", sourceLink: "View original notice",
    noDescription: "No detailed description was provided.", noBudget: "Budget not available",
    noDeadline: "Check source", noApplicable: "Not applicable", preDeadline: "Open when collected",
    koreanFallback: "Korean translation", originalEnglish: "Original English",
  },
};

function loadLocale() {
  try {
    const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (saved === "en" || saved === "ko") return saved;
  } catch (e) {}
  return "ko";
}

function t(key, ...args) {
  const value = (UI[state.locale] || UI.ko)[key];
  return typeof value === "function" ? value(...args) : (value || key);
}

function uiText(ko, en) {
  return state.locale === "en" ? en : ko;
}

const EN_LABELS = {
  "반도체": "Semiconductor", "디스플레이": "Display", "베트남": "Vietnam", "인도": "India",
  "미국": "United States", "독일": "Germany", "태국": "Thailand", "인도네시아": "Indonesia",
  "말레이시아": "Malaysia", "멕시코": "Mexico", "브라질": "Brazil", "러시아": "Russia",
  "싱가포르": "Singapore", "필리핀": "Philippines",
  "오스트리아": "Austria", "벨기에": "Belgium", "체코": "Czechia", "덴마크": "Denmark",
  "스페인": "Spain", "핀란드": "Finland", "프랑스": "France", "아일랜드": "Ireland",
  "이탈리아": "Italy", "네덜란드": "Netherlands", "폴란드": "Poland", "포르투갈": "Portugal",
  "스웨덴": "Sweden", "유럽": "Europe",
  "반도체 장비": "Semiconductor equipment", "디스플레이 장비": "Display equipment", "TGV 장비": "TGV equipment",
  "기타 / 미분류": "Other / unclassified", "국내": "Korea", "중국": "China", "일본": "Japan", "대만": "Taiwan",
  "정식입찰": "Formal tender", "사전규격": "Pre-specification", "프로젝트 정보": "Project lead",
  "자료 제출 요청": "Request for materials",
  "공급사 모집": "Supplier recruitment", "수출상담회": "Export consultation", "구매상담회": "Buyer consultation",
  "낙찰·수주결과": "Award result", "취소·철회": "Cancelled / withdrawn",
  "세정": "Cleaning", "본딩": "Bonding", "검사": "Inspection", "증착": "Deposition", "건식 식각": "Dry etching",
  "습식 식각": "Wet etching", "스퍼터링": "Sputtering", "패키징": "Packaging", "열처리": "Thermal processing",
  "계측": "Metrology", "화학기상증착(CVD)": "Chemical vapor deposition (CVD)",
  "원자층증착(ALD)": "Atomic layer deposition (ALD)", "화학기계연마(CMP)": "Chemical mechanical polishing (CMP)",
};

function label(value) {
  if (!value || state.locale === "ko") return value;
  return EN_LABELS[value] || value;
}

function isEnglishText(value) {
  return /[A-Za-z]/.test(value || "") && !hasEastAsianText(value);
}

function hasEastAsianText(value) {
  return /[\p{Script=Hangul}\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u.test(value || "");
}

// Exact source text keys ensure corrected notices never inherit stale translations.
const EN_NOTICE_TITLES = {
  "[DGIST 제2026-207호] 화학기상증착장비 구매(Refurbish 장비)": "[DGIST No. 2026-207] Purchase of refurbished chemical vapor deposition equipment",
  "입찰공고(제2026–074호) 300mm 웨이퍼용 FOUP": "[Tender No. 2026–074] FOUP for 300 mm wafers",
  "[공고 제2026-41호] 한국나노기술원 Utility 설비 통합관제시스템(HMI) 고도화 사업 1식": "[Notice No. 2026-41] KANC utility equipment monitoring and control system (HMI) upgrade, one lot",
  "[공고 제2026-38-01호] 금속막 원자층 증착 장비 (Metal Atomic Layer Deposition) 1대 구매 (내자)(재공고)": "[Notice No. 2026-38-01] Purchase of one metal-film atomic layer deposition system (domestic procurement, reissued)",
  "2026 서남아 반도체 공급망 진입지원 사업": "2026 program supporting entry into the Southwest Asian semiconductor supply chain",
};

function displayTitle(item) {
  if (state.locale === "en") {
    if (item.englishTitle) return item.englishTitle;
    if (isEnglishText(item.originalTitle)) return item.originalTitle;
    if (Object.hasOwn(EN_NOTICE_TITLES, item.title)) return EN_NOTICE_TITLES[item.title];
    if (isEnglishText(item.title) && !item.translationIncomplete) return item.title;
    const category = label(item.keywords?.[0]);
    return category ? `${category} notice — English title unavailable` : "English title unavailable";
  }
  return item.title || item.originalTitle || "";
}

function displayOrg(item) {
  if (state.locale === "en" && isEnglishText(item.originalOrg)) return item.originalOrg;
  return displayField(item.org || item.originalOrg || "");
}

function displayField(value) {
  if (state.locale === "ko" || !value) return value;
  const translated = label(value);
  return hasEastAsianText(translated) ? "See original-language details" : translated;
}

function displayDescription(item) {
  if (state.locale === "en") {
    if (item.sourceCode === "TED") return "Equipment category is based on the original title. Check TED for specifications and submission requirements.";
    const original = [item.originalDescription, item.originalSummary].find(isEnglishText);
    if (original) return original;
  }
  return displayField(item.description) || t("noDescription");
}

// 수집원의 한국어 정식 명칭. 화면에는 약어를 단독으로 두지 않고 한국어
// 이름과 함께 보여준다(약어만 보면 어디 공고인지 알 수 없다).
// 여기 값은 각 기관의 공식 한국어 명칭이며 추측 번역이 아니다.
const SOURCE_NAMES_KO = {
  TED: "EU 전자입찰공보",
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
  TED: "EU 전자입찰공보(TED)",
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
  if (state.locale === "en") return code || (isEnglishText(item.source) ? item.source : "Unknown source");
  const ko = SOURCE_NAMES_KO[code];
  return ko ? `${ko}(${code})` : (item.source || code || "출처 미상");
}

function sourceBadgeLabel(item) {
  if (state.locale === "en") return sourceFullName(item);
  return SOURCE_BADGE_LABELS[item.sourceCode] || item.source || item.sourceCode || "출처 미상";
}

// 원문 버튼 문구. 한국어 기관명을 앞세우고 공식 약어는 괄호로만 남긴다.
// 새 수집원이 추가되면 여기에 한 줄만 추가하면 되고, 없는 소스는
// "원문 공고 보기"로 자동 처리된다.
const SOURCE_LINK_LABELS = {
  TED: "EU 전자입찰공보(TED) 원문 보기",
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
  "자료 제출 요청": { label: "자료 제출 요청", cls: "notice-type-prespec" },
  "정식입찰": { label: "정식입찰", cls: "notice-type-formal" },
  "프로젝트 정보": { label: "프로젝트 정보", cls: "notice-type-project" },
  "공급사 모집": { label: "공급사 모집", cls: "notice-type-project" },
  "수출상담회": { label: "수출상담회", cls: "notice-type-consult" },
  "구매상담회": { label: "구매상담회", cls: "notice-type-consult" },
  "낙찰·수주결과": { label: "낙찰·수주결과", cls: "notice-type-result" },
  "취소·철회": { label: "취소·철회", cls: "notice-type-result" },
};

const MATERIAL_REQUEST = "자료 제출 요청";
const TYPE_FILTERS = ["전체", "사전규격", MATERIAL_REQUEST, "정식입찰", "프로젝트 정보", "공급사 모집", "수출상담회", "구매상담회", "낙찰·수주결과", "취소·철회"];

// 국가명 -> 국기 이모지 (없는 국가는 이모지 없이 이름만 표시)
const COUNTRY_FLAGS = {
  "국내": "🇰🇷", "중국": "🇨🇳", "베트남": "🇻🇳", "인도": "🇮🇳", "미국": "🇺🇸",
  "일본": "🇯🇵", "독일": "🇩🇪", "대만": "🇹🇼", "태국": "🇹🇭", "인도네시아": "🇮🇩",
  "말레이시아": "🇲🇾", "멕시코": "🇲🇽", "브라질": "🇧🇷", "러시아": "🇷🇺",
  "싱가포르": "🇸🇬", "필리핀": "🇵🇭",
};

const state = {
  locale: loadLocale(),
  selected: loadSelection(),
  selectedNoticeTypes: new Set(), // 비어있으면 "전체"(모든 정보 유형 표시)
  selectedProcesses: new Set(), // 비어있으면 모든 공정 표시
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

// 원문 제목에 명시된 종료 공고만 판정한다. 정정·재입찰은 종료로 보지 않는다.
function terminalNoticeLabel(item) {
  const title = [item.originalTitle, item.title].filter(Boolean).join(" ");
  if (/撤项公告|撤項公告|终止公告|終止公告|取消公告|废标公告|廢標公告|입찰\s*(?:취소|철회|중단)|유찰\s*공고/i.test(title)
      || item.noticeType === "취소·철회"
      || ["취소", "철회", "중단", "유찰"].includes(item.status)) return "취소·철회";
  if (item.noticeType === "낙찰·수주결과" ||
      /中标结果公告|中標結果公告|中标公告|中標公告|成交公告|낙찰\s*(?:결과\s*)?공고/i.test(title)) return "낙찰·수주결과";
  return "";
}

// 여객 안내 완제품은 제조 공정 장비가 아니다. 기존 원본 공고는 보존한다.
function isPassengerDisplay(item) {
  const title = [item.originalTitle, item.title].filter(Boolean).join(" ");
  return /passenger information departure (?:display|디스플레이) systems?\b|여객\s*(?:출발\s*)?안내용\s*디스플레이/i.test(title);
}

function normalizeNoticeForDisplay(item) {
  if (isPassengerDisplay(item)) return { ...item, equipmentStatus: "제외" };
  const terminal = terminalNoticeLabel(item);
  if (terminal) return { ...item, noticeType: terminal };
  const original = item.originalDescription || "";
  if (item.sourceCode === "JETRO" && item.noticeType === "정식입찰" &&
      /\btime[- ]limit\s+for\s+the\s+submission\s+of\s+the\s+requested\s+materials?\s*:/i.test(original) &&
      !/\btime[- ]limit\b[^:.]{0,80}\btenders?\s*:/i.test(original)) {
    return { ...item, noticeType: MATERIAL_REQUEST,
      description: item.description?.replace(/입찰\s*마감(?=\s*:)/g, "자료 제출 마감") };
  }
  return item;
}

function noticeDeadlineLabel(item) {
  return item.noticeType === MATERIAL_REQUEST
    ? uiText("자료 제출 마감", "Materials due")
    : t("deadline");
}

// These two sources share the same Chinese procurement numbering system.
// Keep the complete number, including the lot suffix, and require the original buyer.
function noticeHistoryKey(item) {
  const { sourceCode, projectNo, originalOrg, postedDate } = item;
  if (!["EBNEW", "MOFCOM"].includes(sourceCode) || !projectNo || !originalOrg ||
      !/^\d{4}-\d{2}-\d{2}$/.test(postedDate || "")) return "";
  const number = projectNo.trim().toUpperCase();
  return /^\d{4}-[A-Z0-9]+(?:\/[A-Z0-9]+)?$/.test(number)
    ? JSON.stringify([number, originalOrg.replace(/\s+/g, "")]) : "";
}

function latestNoticeVersions(items) {
  const groups = new Map();
  for (const item of items) {
    const key = noticeHistoryKey(item);
    if (!key) continue;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }

  const replacements = new Map();
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const versions = [...group].sort((a, b) => b.postedDate.localeCompare(a.postedDate) ||
      Number(b.sourceCode === "MOFCOM") - Number(a.sourceCode === "MOFCOM") ||
      a.id.localeCompare(b.id));
    const latest = versions[0];
    const comparableTitle = (item) => (item.originalTitle || "").replace(/[\s\-－—]+/g, "");
    const sameDay = versions.filter((item) => item.postedDate === latest.postedDate);
    // Date precision is only one day: keep ambiguous same-day records visible.
    if (sameDay.some((item) => item !== latest && (!comparableTitle(latest) ||
      comparableTitle(item) !== comparableTitle(latest) || item.dueDate !== latest.dueDate ||
      item.noticeType !== latest.noticeType))) continue;
    replacements.set(latest.id, { ...latest, noticeHistory: versions.slice(1) });
    for (const item of versions.slice(1)) replacements.set(item.id, null);
  }
  return items.flatMap((item) => {
    const replacement = replacements.has(item.id) ? replacements.get(item.id) : item;
    return replacement ? [replacement] : [];
  });
}

// 마감일 미확인 및 종료 공고는 열려 있는 공고 수에 넣지 않는다.
// 공고 목록 및 원문 링크는 유지한다.
function isValidOpen(item) {
  return !terminalNoticeLabel(item) && !!item.dueDate &&
    Number.isFinite(daysUntil(item.dueDate)) && daysUntil(item.dueDate) >= 0;
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
        <span>${escapeHtml(label(kw))}</span>
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
    return `<button type="button" class="chip${active ? " chip-active" : ""}" data-category="${kw}">${escapeHtml(label(kw))}</button>`;
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

function availableProcesses() {
  return [...new Set((state.data.items || []).map((item) => item.process).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, state.locale === "en" ? "en" : "ko"));
}

function renderProcessChips() {
  const row = document.getElementById("processChipRow");
  if (!row) return;
  const processes = availableProcesses();
  const noneSelected = state.selectedProcesses.size === 0;
  const entries = [{ value: "", text: t("processAll") }, ...processes.map((p) => ({ value: p, text: label(p) })),
    { value: PROCESS_UNKNOWN, text: t("processUnknown") }];
  row.innerHTML = entries.map(({ value, text }) => {
    const active = value === "" ? noneSelected : state.selectedProcesses.has(value);
    return `<button type="button" class="chip chip-process${active ? " chip-active" : ""}" data-process="${escapeHtml(value)}">${escapeHtml(text)}</button>`;
  }).join("");
  row.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const process = chip.dataset.process;
      if (!process) state.selectedProcesses.clear();
      else if (state.selectedProcesses.has(process)) state.selectedProcesses.delete(process);
      else state.selectedProcesses.add(process);
      renderProcessChips();
      renderTypeChips();
      renderResults();
    });
  });
}

function renderTypeChips() {
  const row = document.getElementById("typeChipRow");
  const noneSelected = state.selectedNoticeTypes.size === 0;
  row.innerHTML = TYPE_FILTERS.map((type) => {
    const active = type === "전체" ? noneSelected : state.selectedNoticeTypes.has(type);
    return `<button type="button" class="chip chip-outline${active ? " chip-active" : ""}" data-type="${type}">${escapeHtml(type === "전체" ? t("all") : label(type))}</button>`;
  }).join("");

  const countLabel = document.getElementById("filterCount");
  if (countLabel) {
    countLabel.textContent = noneSelected && state.selectedProcesses.size === 0
      ? "" : t("selectedFilters", state.selectedNoticeTypes.size, state.selectedProcesses.size);
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
  if (!dateStr) return `<span class="dday-badge dday-gray">${t("deadlineUnknown")}</span>`;
  const d = daysUntil(dateStr);
  if (!Number.isFinite(d)) return `<span class="dday-badge dday-gray">${t("deadlineUnknown")}</span>`;
  if (d < 0) return `<span class="dday-badge dday-gray">${t("closed")}</span>`;
  // 숫자형(D-3)은 그대로 두되, 영어 "D-DAY"만 한국어로 바꾼다.
  const label = d === 0 ? t("dueToday") : `D-${d}`;
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
  const terminal = terminalNoticeLabel(item);
  if (terminal) return terminal;
  if (!item.dueDate || !Number.isFinite(daysUntil(item.dueDate))) return t("deadlineUnknown");
  if (daysUntil(item.dueDate) < 0) return t("closed");
  return state.locale === "en" ? t("preDeadline") : (item.status || t("preDeadline"));
}

function noticeDeadlineBadge(item) {
  const terminal = terminalNoticeLabel(item);
  if (terminal) return `<span class="dday-badge dday-gray">${label(terminal)}</span>`;
  return ddayBadge(item.dueDate);
}

function topTags(item) {
  const flag = COUNTRY_FLAGS[item.country] || "";
  const countryLabel = flag ? `${flag} ${label(item.country)}` : (label(item.country) || t("countryUnknown"));
  const tags = [`<span class="country-badge">${escapeHtml(countryLabel)}</span>`];
  if (item.sourceType === "China Site") {
    tags.push(`<span class="china-site-badge">${uiText("중국 사이트", "Chinese source")}</span>`);
  }
  tags.push(`<span class="source-badge" title="${escapeHtml(sourceFullName(item))}">${escapeHtml(sourceBadgeLabel(item))}</span>`);
  const noticeType = NOTICE_TYPE_LABELS[item.noticeType];
  if (noticeType) {
    tags.push(`<span class="notice-type-badge ${noticeType.cls}">${escapeHtml(label(noticeType.label))}</span>`);
  }
  // 번역이 불완전한 중국 공고(용어집에 없어 로마자 표기로 폴백된 경우)는
  // 제목만으로 내용을 알 수 없으므로, 원문 확인이 필요하다는 것을 알린다.
  // 원문 제목은 상세의 "원문(중국어)" 블록, 원문 링크는 하단 버튼에 그대로 있다.
  if (item.translationIncomplete) {
    tags.push(`<span class="translation-badge">${t("translationIncomplete")}</span>`);
  }
  // 장비인지 확정하지 못한 공고 — 홈 "지금 확인할 공고"와 Telegram에서는
  // 빠지고, 목록에서는 이 배지를 달아 사용자가 직접 판단할 수 있게 한다.
  if (item.equipmentStatus === "검토 필요") {
    const reason = state.locale === "ko" ? item.equipmentReason : "";
    tags.push(`<span class="review-badge" title="${escapeHtml(reason || t("reviewNeeded"))}">${t("reviewNeeded")}</span>`);
  }
  if (isNewItem(item)) {
    tags.push(`<span class="new-badge">${t("new")}</span>`);
  }
  return `<span class="notice-tags">${tags.join("")}</span>`;
}

function detailLinkLabel(item) {
  if (state.locale === "en") return t("sourceLink");
  return SOURCE_LINK_LABELS[item.sourceCode] || t("sourceLink");
}

function detailRow(label, value) {
  if (!value) return "";
  return `<div class="notice-detail-row"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(displayField(value))}</dd></div>`;
}

function detailRowWithFallback(label, value, fallback) {
  return detailRow(label, value || fallback);
}

// 첨부파일명에 한국어가 하나도 없으면(중국어·일본어·영어 파일명) 그대로
// 보여줘도 사용자가 무엇인지 알 수 없다. 뜻을 지어내지 않고 "첨부파일 N"으로
// 표시하되 확장자는 남겨 형식은 알 수 있게 한다. 원래 파일명은 링크의
// title 속성과 데이터에 그대로 남는다.
const HANGUL_RE = /[가-힣]/;

function attachmentLabel(name, index) {
  const raw = (name || "").trim();
  if (!raw) return `${t("attachments")} ${index + 1}`;
  if (state.locale === "en" ? !hasEastAsianText(raw) : HANGUL_RE.test(raw)) return raw;
  const ext = (raw.match(/\.([A-Za-z0-9]{1,5})$/) || [])[1];
  return ext ? `${t("attachments")} ${index + 1}.${ext.toLowerCase()}` : `${t("attachments")} ${index + 1}`;
}

function renderAttachments(item) {
  if (!item.attachments || item.attachments.length === 0) return "";
  const links = item.attachments.map((a, i) =>
    `<li><a href="${a.url}" target="_blank" rel="noopener" title="${escapeHtml(a.name || "")}">${escapeHtml(attachmentLabel(a.name, i))}</a></li>`
  ).join("");
  return `
    <div class="detail-section">
      <h4>${t("attachments")}</h4>
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
function originalTextBlock(item) {
  if (state.locale !== "en") return "";
  const fields = [
    ["Title", item.originalTitle || item.title], ["Buyer", item.originalOrg || item.org],
    ["Summary", item.originalDescription || item.originalSummary || item.description],
    ["Equipment", item.equipmentName], ["Region", item.region], ["Quantity", item.quantity],
    ["Budget", item.budget], ["Delivery", item.deliveryCondition], ["Event dates", item.eventPeriod],
    ["Contract method", item.contractMethod], ["Payment terms", item.paymentCondition],
    ["Eligibility", item.eligibility],
  ];
  const rows = fields.filter(([, value]) => hasEastAsianText(value))
    .map(([name, value]) => `<div><dt>${name}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
  return rows ? `<details class="detail-section"><summary>Original-language details</summary><dl class="notice-detail-list">${rows}</dl></details>` : "";
}

function renderNoticeHistory(item) {
  if (!item.noticeHistory?.length) return "";
  const rows = item.noticeHistory.map((version) => {
    let url;
    try { url = new URL(version.url); } catch { return ""; }
    if (!["https:", "http:"].includes(url.protocol)) return "";
    const labelText = [sourceBadgeLabel(version), version.postedDate, displayTitle(version)].join(" · ");
    const deadline = version.dueDate ? ` · ${t("deadline")} ${version.dueDate}` : "";
    return `<li><a href="${escapeHtml(url.href.replace(/"/g, "%22"))}" target="_blank" rel="noopener">${escapeHtml(labelText + deadline)}</a></li>`;
  }).join("");
  return rows ? `<details class="detail-section notice-history"><summary>${uiText("이전 공고 및 다른 출처", "Earlier notices and other sources")}</summary><ul class="attachment-list">${rows}</ul></details>` : "";
}

function findDisplayNotice(noticeId) {
  return state.data.items.find((item) => item.id === noticeId ||
    item.noticeHistory?.some((version) => version.id === noticeId));
}

function renderCard(item, kw) {
  const field = (ko, en) => state.locale === "en" ? en : ko;
  const businessRows = [
    detailRow(field("공고번호", "Notice ID"), item.projectNo || item.g2bBidNo),
    detailRow(field("수량", "Quantity"), item.quantity),
    detailRowWithFallback(field("예산", "Budget"), item.budget, t("noBudget")),
    detailRow(field("계약방식", "Contract method"), item.contractMethod),
    detailRow(field("지급조건", "Payment terms"), item.paymentCondition),
    detailRow(field("자격조건", "Eligibility"), item.eligibility),
  ].join("");

  return `
    <details class="notice-card" data-notice-id="${escapeHtml(item.id || "")}">
      <summary class="notice-summary">
        <span class="notice-icon">${iconSvg(kw, 18)}</span>
        <span class="notice-body">
          ${topTags(item)}
          <p class="notice-title">${escapeHtml(displayTitle(item))}</p>
          <span class="notice-meta">
            <span class="meta-org">${escapeHtml(displayOrg(item))}</span>
            <span class="meta-due">${escapeHtml(label(terminalNoticeLabel(item)) || `${noticeDeadlineLabel(item)} ${item.dueDate || t("noDeadline")}`)}</span>
          </span>
        </span>
        ${noticeDeadlineBadge(item)}
        <span class="chevron">›</span>
      </summary>
      <div class="notice-detail">
        <div class="detail-section">
          <h4>${t("basic")}</h4>
          <dl class="notice-detail-list">
            ${detailRow(field("산업", "Industry"), label(item.industry))}
            ${detailRow(field("공정", "Process"), label(item.process))}
            ${detailRow(field("장비명", "Equipment"), item.equipmentName)}
            ${detailRow(field("국가", "Country"), label(item.country))}
            ${detailRow(field("지역", "Region"), item.region)}
            ${detailRow(field("출처", "Source"), item.source)}
            ${detailRow(field("발주기관", "Buyer"), displayOrg(item))}
            ${detailRow(field("분야", "Category"), label(kw))}
            ${detailRow(field("정보 유형", "Notice type"), label(item.noticeType))}
            ${item.sourceCode === "TED" ? detailRow(field("원문 제목", "Original title"), item.originalTitle) : ""}
          </dl>
        </div>
        ${originalTextBlock(item)}
        ${renderNoticeHistory(item)}
        <div class="detail-section">
          <h4>${t("schedule")}</h4>
          <dl class="notice-detail-list">
            ${detailRow(field("등록일", "Published"), item.postedDate || t("noDeadline"))}
            ${detailRow(item.noticeType === MATERIAL_REQUEST ? noticeDeadlineLabel(item) : field("마감일", "Deadline"), item.dueDate || (terminalNoticeLabel(item) ? t("noApplicable") : t("deadlineUnknown")))}
            ${detailRow(field("이행기한 / 납기", "Delivery"), item.deliveryCondition)}
            ${detailRow(field("행사 기간", "Event dates"), item.eventPeriod)}
            ${detailRow(field("상태", "Status"), label(displayStatus(item)))}
          </dl>
        </div>
        ${businessRows ? `<div class="detail-section"><h4>${t("noticeInfo")}</h4><dl class="notice-detail-list">${businessRows}</dl></div>` : ""}
        <div class="detail-section">
          <h4>${t("summary")}</h4>
          <p class="notice-detail-desc">${escapeHtml(displayDescription(item))}</p>
        </div>
        ${renderAttachments(item)}
        <button type="button" class="ghost-btn notice-feedback" data-feedback-open data-feedback-id="${escapeHtml(item.id)}" data-feedback-title="${escapeHtml(displayTitle(item))}">${uiText("정보 오류 신고", "Report incorrect information")}</button>
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

function matchesProcess(item) {
  if (state.selectedProcesses.size === 0) return true;
  if (!item.process) return state.selectedProcesses.has(PROCESS_UNKNOWN);
  return state.selectedProcesses.has(item.process);
}

// 분야 외 공통 필터(정보유형/신규/마감임박/지역). 분야 그룹과 미분류 그룹이
// 같은 기준으로 걸러지도록 한 곳에 모아둔다.
function passesCommonFilters(item) {
  if (state.selectedNoticeTypes.size > 0 && !state.selectedNoticeTypes.has(item.noticeType)) return false;
  if (!matchesProcess(item)) return false;
  if (state.showOnlyNew && !isNewItem(item)) return false;
  if (state.dueSoonOnly) {
    if (!isValidOpen(item)) return false;
    const d = item.dueDate ? daysUntil(item.dueDate) : null;
    if (d === null || d < 0 || d > 7) return false;
  }
  return matchesRegion(item);
}

function computeNewCount() {
  // 분야가 겹쳐도 공고 ID 기준으로 한 번만 센다. 기존 정보유형/지역 필터 유지.
  return uniqueItems(state.data.items.filter((item) =>
    (isUnclassified(item) || (item.keywords || []).some((kw) => state.selected.has(kw))) &&
    (state.selectedNoticeTypes.size === 0 || state.selectedNoticeTypes.has(item.noticeType)) &&
    matchesProcess(item) &&
    matchesRegion(item) &&
    isNewItem(item)
  )).length;
}

function updateNewAnnounceBar(count) {
  const bar = document.getElementById("newAnnounceBar");
  if (!bar) return;
  bar.hidden = false;
  if (count === 0) {
    bar.disabled = true;
    bar.classList.remove("active");
    bar.textContent = state.locale === "en" ? "No new notices found in the last 48 hours" : "최근 48시간 안에 새로 잡힌 공고가 없습니다";
    return;
  }
  bar.disabled = false;
  bar.classList.toggle("active", state.showOnlyNew);
  bar.textContent = state.locale === "en"
    ? (state.showOnlyNew ? `Showing ${count} new notice(s) · Show all` : `Show ${count} new notice(s)`)
    : (state.showOnlyNew ? `새 공고 ${count}건만 보는 중 · 전체로 돌아가기` : `새 공고 ${count}건만 보기`);
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

  // 여러 분야에 속하는 동일 공고를 전체 합계에는 한 번만 센다.
  const totalCount = uniqueItems(groups.flatMap((g) => g.items)).length;
  document.getElementById("totalCount").textContent = t("total", totalCount);

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
        <div class="group-title">${iconSvg(kw, 16)} ${escapeHtml(label(kw))}</div>
        <span class="group-count">${t("count", items.length)}</span>
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
  if (!iso) return state.locale === "en" ? "No collection history" : "수집 기록 없음";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  const prefix = state.locale === "en" ? "Last collected" : "마지막 수집";
  return `${prefix} ${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
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

  const unknownDeadline = uniqueItems(state.data.items).filter((item) =>
    matchesRegion(item) && !terminalNoticeLabel(item) &&
    (!item.dueDate || !Number.isFinite(daysUntil(item.dueDate)))).length;
  return { valid, domestic, overseas, newThisWeek, newCount: newItems.length, newToday, dueSoon, byCategory, unknownDeadline };
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
      <rect x="${x.toFixed(1)}" y="${y}" width="${barWidth.toFixed(1)}" height="${Math.max(barHeight, 2)}" rx="3" fill="var(--si)"></rect>
      ${b.count > 0 ? `<text x="${(x + barWidth / 2).toFixed(1)}" y="${y - 4}" font-size="9" font-weight="500" fill="var(--ink)" text-anchor="middle">${b.count}</text>` : ""}
      ${showEveryLabel ? `<text x="${(x + barWidth / 2).toFixed(1)}" y="${height - 5}" font-size="8.5" fill="var(--muted)" text-anchor="middle">${escapeHtml(b.label)}</text>` : ""}
    `;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="${uiText("기간별 신규 공고 추이 차트", "New notice trends")}">${bars}</svg>`;
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
    return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}"><circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--line)" stroke-width="${stroke}"></circle></svg>`;
  }
  let offset = 0;
  const circles = segments.filter((s) => s.value > 0).map((seg) => {
    const dash = (seg.value / total) * circumference;
    const circle = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${seg.color}" stroke-width="${stroke}" stroke-dasharray="${dash.toFixed(1)} ${(circumference - dash).toFixed(1)}" stroke-dashoffset="${(-offset).toFixed(1)}" transform="rotate(-90 ${cx} ${cy})"></circle>`;
    offset += dash;
    return circle;
  }).join("");
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="${uiText("분야별 비중 도넛 차트", "Share by category")}">
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--line)" stroke-width="${stroke}"></circle>
    ${circles}
  </svg>`;
}

function renderDonutLegend(segments) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  return `<ul class="chart-legend">${segments.map((s) => {
    const pct = total > 0 ? Math.round((s.value / total) * 100) : 0;
    return `<li><span class="legend-dot" style="background:${s.color}"></span>${escapeHtml(s.label)} <b>${t("count", s.value)}</b> <span class="legend-pct">${pct}%</span></li>`;
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
      <span><span class="legend-dot" style="background:var(--ink)"></span>${uiText("국내", "Korea")} <b>${t("count", domestic)}</b> (${domPct}%)</span>
      <span><span class="legend-dot" style="background:var(--si-bright)"></span>${uiText("해외", "International")} <b>${t("count", overseas)}</b> (${overPct}%)</span>
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
        ${isNewItem(item) ? `<span class="new-badge">${t("new")}</span>` : ""}
        ${item.noticeType === MATERIAL_REQUEST ? `<span class="notice-type-badge notice-type-prespec">${label(MATERIAL_REQUEST)}</span>` : ""}
        ${noticeDeadlineBadge(item)}
      </span>
      <span class="spotlight-title">${escapeHtml(displayTitle(item))}</span>
      <span class="spotlight-meta">${escapeHtml(flag ? `${flag} ${label(item.country)}` : (label(item.country) || t("countryUnknown")))} · ${escapeHtml(label(kw) || uiText("분야 미상", "Unknown category"))}</span>
    </button>`;
}

// 홈/일정 화면의 카드에서 공고 탭의 해당 상세로 이동한다.
// 현재 필터 때문에 목록에 없으면 필터를 풀고 다시 그린 뒤 찾아간다.
function noticeIdFromHash() {
  // "#n=<id>" 한 가지만 본다. 없거나 모양이 다르면 빈 문자열이다.
  const m = (location.hash || "").match(/^#n=([^&]+)$/);
  if (!m) return "";
  try {
    return decodeURIComponent(m[1]);
  } catch (e) {
    return "";
  }
}

function openNoticeDetail(noticeId) {
  if (!noticeId) return;
  const target = findDisplayNotice(noticeId);
  if (target) noticeId = target.id;
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
  if (target) {
    (target.keywords || []).forEach((kw) => state.selected.add(kw));
  }
  state.region = "all";
  state.showOnlyNew = false;
  state.dueSoonOnly = false;
  state.selectedNoticeTypes.clear();
  state.selectedProcesses.clear();
  renderCategoryChips();
  renderProcessChips();
  renderTypeChips();
  renderResults();
  setTimeout(reveal, 0);
}

// 웨이퍼 맵 — 열린 공고 한 건을 칩 하나로 그린다.
//
// 팹에서 웨이퍼 한 장의 상태를 한눈에 보는 방식 그대로다. 마감이 가까운
// 공고일수록 가운데에 놓고 색을 달리해, 숫자를 읽지 않아도 "급한 것이
// 얼마나 되는지"가 보인다. 칩을 누르면 아래 칸에 그 공고가 뜬다.
function waferUrgency(item) {
  const d = item.dueDate ? daysUntil(item.dueDate) : Infinity;
  if (d <= 3) return { cls: "u-hot", rank: 0, d };
  if (d <= 7) return { cls: "u-soon", rank: 1, d };
  return { cls: "u-open", rank: 2, d };
}

function waferCells(n, size) {
  // n×n 격자 중 원 안에 온전히 들어오는 칸만 쓴다. 아래쪽에는 노치 자리를 비운다.
  const cell = size / n;
  const c = size / 2;
  const r = size / 2 - 3;
  const cells = [];
  for (let row = 0; row < n; row += 1) {
    for (let col = 0; col < n; col += 1) {
      const x = col * cell;
      const y = row * cell;
      const corners = [[x, y], [x + cell, y], [x, y + cell], [x + cell, y + cell]];
      if (!corners.every(([px, py]) => Math.hypot(px - c, py - c) <= r)) continue;
      const mx = x + cell / 2;
      const my = y + cell / 2;
      if (my > c + r - cell * 1.1 && Math.abs(mx - c) < cell * 0.9) continue; // 노치
      cells.push({ x, y, dist: Math.hypot(mx - c, my - c), angle: Math.atan2(my - c, mx - c) });
    }
  }
  // 가운데에서 바깥으로, 같은 거리면 시계 방향으로 채운다.
  cells.sort((a, b) => (Math.round(a.dist) - Math.round(b.dist)) || (a.angle - b.angle));
  return { cells, cell };
}

function renderWaferMap(validItems) {
  const size = 200;
  const items = validItems
    .map((item) => ({ item, u: waferUrgency(item) }))
    .sort((a, b) => a.u.rank - b.u.rank || a.u.d - b.u.d);

  // 공고가 다 들어가고도 빈 칩이 조금 남는 가장 성긴 격자를 고른다.
  let grid = waferCells(9, size);
  for (let n = 9; n <= 31 && grid.cells.length < Math.max(items.length * 1.12, 45); n += 1) {
    grid = waferCells(n, size);
  }
  const gap = Math.max(0.8, grid.cell * 0.09);
  const side = grid.cell - gap;

  const dies = grid.cells.map((cellPos, i) => {
    const x = (cellPos.x + gap / 2).toFixed(2);
    const y = (cellPos.y + gap / 2).toFixed(2);
    const entry = items[i];
    if (!entry) {
      return `<rect class="die" x="${x}" y="${y}" width="${side.toFixed(2)}" height="${side.toFixed(2)}" rx="1"></rect>`;
    }
    const { item, u } = entry;
    const dot = isNewItem(item)
      ? `<circle class="die-new" style="--i:${i}" cx="${(cellPos.x + grid.cell / 2).toFixed(2)}" cy="${(cellPos.y + grid.cell / 2).toFixed(2)}" r="${(side * 0.2).toFixed(2)}"></circle>`
      : "";
    return `<rect class="die die-on ${u.cls}" style="--i:${i}" data-die-id="${escapeHtml(item.id || "")}" x="${x}" y="${y}" width="${side.toFixed(2)}" height="${side.toFixed(2)}" rx="1"><title>${escapeHtml(displayTitle(item))}</title></rect>${dot}`;
  }).join("");

  const c = size / 2;
  const r = size / 2 - 1;
  // 원 아래쪽에 작은 노치를 판 웨이퍼 외곽선
  const notch = 5;
  const edge = `M ${c - notch} ${c + r - 0.4} A ${r} ${r} 0 1 1 ${c + notch} ${c + r - 0.4} L ${c} ${c + r - notch} Z`;
  return `<svg class="wafer" viewBox="0 0 ${size} ${size}" role="img" aria-label="${uiText(`열려 있는 공고 ${items.length}건을 칩으로 그린 웨이퍼 맵`, `Wafer map of ${items.length} open notices`)}">
    <path class="wafer-edge" d="${edge}"></path>
    ${dies}
  </svg>`;
}

// 칩을 고르면 그 공고를 아래 칸에 보여 준다. 칩이 작아 바로 이동시키면
// 잘못 누르기 쉬우므로, 먼저 무엇인지 보여 주고 "공고 열기"로 들어가게 한다.
function probeDie(noticeId) {
  const probe = document.getElementById("waferProbe");
  const item = (state.data.items || []).find((i) => i.id === noticeId);
  if (!probe || !item) return;
  document.querySelectorAll(".die-probed").forEach((el) => el.classList.remove("die-probed"));
  const die = document.querySelector(`.die-on[data-die-id="${CSS.escape(noticeId)}"]`);
  if (die) die.classList.add("die-probed");
  const due = item.dueDate ? `${noticeDeadlineLabel(item)} ${item.dueDate}` : t("deadlineUnknown");
  const d = item.dueDate ? daysUntil(item.dueDate) : null;
  const left = d === null ? "" : (d === 0 ? ` · ${t("dueToday")}` : ` · D-${d}`);
  probe.innerHTML = `
    <div class="probe-body">
      <p class="probe-title">${escapeHtml(displayTitle(item))}</p>
      <p class="probe-meta">${escapeHtml(label(item.country) || t("countryUnknown"))} · ${escapeHtml(due)}${left}</p>
    </div>
    <button type="button" class="probe-open" data-open-notice="${escapeHtml(item.id)}">${uiText("공고 열기", "Open notice")}</button>`;
}

function renderHome() {
  const stats = computeHomeStats();

  document.querySelectorAll(".region-chip").forEach((chip) => {
    chip.classList.toggle("chip-active", chip.dataset.region === state.region);
  });

  document.getElementById("kpiHeroCard").innerHTML = `
    <div class="hero-top">
      <div>
        <p class="hero-label">${uiText("지금 열려 있는 공고", "Open notices")}</p>
        <p class="hero-count">${stats.valid.length}<span>${uiText("건", "")}</span></p>
      </div>
      <p class="hero-split">
        ${uiText("국내", "Korea")}<b>${stats.domestic}</b><br>
        ${uiText("해외", "International")}<b>${stats.overseas}</b><br>
        ${uiText("이번 주 새 공고", "New this week")}<b class="up">+${stats.newThisWeek}</b><br>
        ${uiText("마감일 미확인", "Deadline unverified")}<b>${stats.unknownDeadline}</b>
      </p>
    </div>
    <div class="wafer-wrap">${renderWaferMap(stats.valid)}</div>
    <ul class="wafer-legend">
      <li><i class="lg-hot"></i>${uiText("3일 안에 마감", "Due within 3 days")}</li>
      <li><i class="lg-soon"></i>${uiText("7일 안에 마감", "Due within 7 days")}</li>
      <li><i class="lg-open"></i>${uiText("여유 있음", "Open")}</li>
      <li><i class="lg-new"></i>${uiText("새 공고", "New notices")}</li>
    </ul>
    <div class="probe" id="waferProbe">
      <p class="probe-empty">${uiText("칩 하나가 공고 한 건입니다. 칩을 누르면 어떤 공고인지 보입니다.", "Select a chip to preview its notice.")}</p>
    </div>
  `;

  document.getElementById("kpiMiniRow").innerHTML = `
    <button type="button" class="kpi-mini-card" id="kpiNewCard">
      <span class="kpi-mini-label">${uiText("새 진행 공고", "New open notices")}</span>
      <span class="kpi-mini-value">${stats.newCount}<small>${uiText("건", "")}</small></span>
      <span class="kpi-mini-sub">${uiText("최근 48시간 · 오늘", "Last 48 hours · today")} +${stats.newToday}</span>
    </button>
    <button type="button" class="kpi-mini-card kpi-mini-warn" id="kpiDueSoonCard">
      <span class="kpi-mini-label">${uiText("곧 마감", "Closing soon")}</span>
      <span class="kpi-mini-value">${stats.dueSoon.length}<small>${uiText("건", "")}</small></span>
      <span class="kpi-mini-sub">${uiText("7일 안에 마감", "Due within 7 days")}</span>
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
      <span class="stat-mini-label">${escapeHtml(label(kw))}</span>
      <span class="stat-mini-value">${stats.byCategory[kw] || 0}<small>${uiText("건", "")}</small></span>
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
    : `<p class="empty-state">${uiText("지금 열려 있는 공고가 없습니다.", "No open notices.")}</p>`;

  const updatedText = formatUpdatedAt(state.data.updatedAt);
  document.getElementById("updatedAtHome").innerHTML = updatedText;
}

function computeCalendarDueMap() {
  const map = {};
  uniqueItems(state.data.items).forEach((item) => {
    if (terminalNoticeLabel(item) || !item.dueDate || !Number.isFinite(daysUntil(item.dueDate))) return;
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

  document.getElementById("calMonthLabel").textContent = new Intl.DateTimeFormat(state.locale, { year: "numeric", month: "long" }).format(cursor);

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
    <h3 class="dash-card-title">${uiText(`${state.calendarSelectedDate}에 마감되는 공고 ${dayItems.length}건`, `${dayItems.length} due on ${state.calendarSelectedDate}`)}</h3>
    <div class="spotlight-list">
      ${dayItems.map(renderSpotlightCard).join("") || `<p class="empty-state">${uiText("이날 마감되는 공고가 없습니다.", "No notices are due on this date.")}</p>`}
    </div>`;
}

function renderStats() {
  const all = uniqueItems(state.data.items).filter(isValidOpen);

  document.getElementById("statsTrend7").innerHTML = renderBarChart(computeNewTrend(7));
  document.getElementById("statsTrend30").innerHTML = renderBarChart(computeNewTrend(30), { height: 90 });

  const catColors = { "반도체 장비": "var(--ink)", "디스플레이 장비": "var(--si-bright)", "TGV 장비": "var(--amber)" };
  const byCategory = KEYWORDS.map((kw) => ({
    label: label(kw),
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
    const type = label(item.noticeType) || uiText("미상", "Unknown");
    noticeTypeCounts[type] = (noticeTypeCounts[type] || 0) + 1;
  });
  document.getElementById("statsNoticeType").innerHTML = renderBarList(noticeTypeCounts);

  const sourceCounts = {};
  all.forEach((item) => {
    const s = sourceBadgeLabel(item);
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
    renderProcessChips();
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

function applyLocale() {
  document.documentElement.lang = state.locale;
  document.title = document.querySelector("h1").dataset[state.locale];
  document.querySelectorAll("[data-ko][data-en]").forEach((el) => {
    el.textContent = el.dataset[state.locale];
  });
  for (const attr of ["aria-label", "title"]) {
    document.querySelectorAll(`[data-${attr}-${state.locale}]`).forEach((el) => {
      el.setAttribute(attr, el.getAttribute(`data-${attr}-${state.locale}`));
    });
  }
  document.querySelectorAll(".language-btn").forEach((btn) => {
    const active = btn.dataset.locale === state.locale;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
}

function setLocale(locale) {
  if (locale !== "ko" && locale !== "en") return;
  const openIds = new Set([...document.querySelectorAll(".notice-card[open]")].map((card) => card.dataset.noticeId));
  state.locale = locale;
  try { localStorage.setItem(LOCALE_STORAGE_KEY, locale); } catch (e) {}
  applyLocale();
  renderSourceHealth();
  renderCollectionTime();
  const active = document.querySelector(".bottom-nav-item.active");
  showTab(active ? active.dataset.tab : "home");
  document.querySelectorAll(".notice-card").forEach((card) => {
    card.open = openIds.has(card.dataset.noticeId);
  });
}

// 수집이 실패한 출처가 있으면 헤더에 경고를 띄운다 — 실패해도 그 출처의
// 이전 수집분이 화면에 그대로 남기 때문에, 표시가 없으면 낡은 데이터를
// 최신으로 오해하게 된다. 정상일 때는 아무것도 표시하지 않는다.
function renderSourceHealth() {
  const el = document.getElementById("sourceHealthNotice");
  if (!el) return;
  if (!state.data.collectionDelayed) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = uiText("일부 공고의 갱신이 지연되고 있습니다. 최신 일정은 공고 원문에서 확인해 주세요.", "Some notices may be delayed. Please check the original notice for the latest schedule.");
}

function renderCollectionTime() {
  const updatedText = formatUpdatedAt(state.data.updatedAt);
  document.getElementById("updatedAt").textContent = updatedText;
  document.getElementById("updatedAt2").textContent = updatedText;
}

async function loadData() {
  try {
    const res = await fetch("data/announcements.json", { cache: "no-store" });
    state.data = await res.json();
    // 공통 장비 판정에서 "제외"로 분류된 공고(재료·부품·소모품·용역·공사 등)는
    // 화면에 올리지 않는다. 데이터 파일에는 남겨 둔다 — 지우면 id가 사라져
    // 다음 수집에서 다시 신규 공고로 잡히기 때문이다.
    const rawItems = (state.data.items || []).map(normalizeNoticeForDisplay);
    state.data.excludedItems = rawItems.filter((i) => i.equipmentStatus === "제외");
    state.data.items = latestNoticeVersions(rawItems.filter((i) => i.equipmentStatus !== "제외"));
  } catch (e) {
    console.error("공고 데이터를 불러오지 못했습니다.", e);
    state.data = { updatedAt: null, items: [] };
  }
  renderCollectionTime();
  renderSourceHealth();
  // Telegram 알림의 공고별 링크(#n=<id>)로 들어왔으면 그 공고를 펼쳐 준다.
  // openNoticeDetail이 필터까지 풀고 찾아가므로 여기서는 넘겨주기만 한다.
  const wanted = noticeIdFromHash();
  if (wanted && findDisplayNotice(wanted)) {
    openNoticeDetail(wanted);
    return;
  }
  // 데이터가 늦게 도착해도 현재 보고 있는 탭을 다시 그려 숫자/차트를 채운다.
  const active = document.querySelector(".bottom-nav-item.active");
  showTab(active ? active.dataset.tab : "home");
}

function init() {
  applyLocale();
  renderKeywordGrid();
  loadData();

  document.querySelectorAll(".language-btn").forEach((btn) => {
    btn.addEventListener("click", () => setLocale(btn.dataset.locale));
  });

  document.getElementById("viewResultsBtn").addEventListener("click", () => showTab("tenders"));
  document.getElementById("viewAllTendersBtn").addEventListener("click", () => showTab("tenders"));

  document.getElementById("newAnnounceBar").addEventListener("click", () => {
    state.showOnlyNew = !state.showOnlyNew;
    renderResults();
  });

  document.getElementById("telegramBtn").addEventListener("click", () => {
    alert(uiText("텔레그램 알림은 이미 연결되어 있습니다. 매일 아침 수집이 끝나면 새로 잡힌 장비 공고를 보냅니다. 분야 선택은 이 화면의 공고 목록에만 적용됩니다.", "Telegram alerts are connected. New equipment notices are sent after the morning collection. Category settings apply only to the notice list on this device."));
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
    if (card) { openNoticeDetail(card.dataset.noticeId); return; }
    const die = e.target.closest(".die-on[data-die-id]");
    if (die) { probeDie(die.dataset.dieId); return; }
    const open = e.target.closest("[data-open-notice]");
    if (open) openNoticeDetail(open.dataset.openNotice);
  });
  // 마우스가 있는 화면에서는 칩 위에 올리기만 해도 무엇인지 보여 준다.
  document.addEventListener("mouseover", (e) => {
    const die = e.target.closest && e.target.closest(".die-on[data-die-id]");
    if (die) probeDie(die.dataset.dieId);
  });

  // 공고별 링크(#n=<id>)로 들어온 경우에는 첫 화면을 띄우지 않는다.
  // 데이터가 도착하면 loadData가 그 공고를 펼쳐 준다.
  if (!noticeIdFromHash()) showTab("home");
}

document.addEventListener("DOMContentLoaded", init);
