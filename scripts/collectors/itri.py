"""
ITRI(대만 산업기술연구원) 採購資訊系統 詢價案 공고 수집기.

실제 페이지 구조 (2026-09 기준, 직접 확인해 작성):
- 진입: https://www.itri.org.tw/ 의 "採購資訊" → https://vendor.itri.org.tw/broadBqry.aspx
  (302 → broadBqry2.aspx). 여기서 실제 공고 목록이 있는 곳은
- 목록: https://quotaweb.itri.org.tw/quotabrowse.aspx  (로그인 없이 공개)
  표 헤더: 案號 | 項次 | 品名/料號 | 數量 | 履約期限 | 詳細規格 | 規格附件 | 採購承辦 | 報價截止日
  날짜는 YYYYMMDD 정수 문자열(예: 20261202)로 들어온다.
  상세 규격은 같은 사이트의 팝업(詢/報價單)이며, 목록만으로 제목·수량·
  기한이 모두 확인되므로 상세 페이지는 요청하지 않는다(불필요한 부하 방지).

번역: 이 사이트는 **번체 중국어**다. 기존 zh_translate 용어집은 간체자
기준이라 번체 제목에는 거의 걸리지 않아 로마자 표기로만 떨어진다. 그래서
이 수집기 안에 번체자 장비/공정 용어집을 따로 두고 먼저 치환한 뒤, 남은
한자는 zh_translate의 로마자 폴백을 그대로 쓴다(기존 EBNEW/MOFCOM 동작에는
영향을 주지 않는다 — 이 용어집은 여기서만 쓴다).

수집 대상은 반도체/디스플레이/TGV 및 관련 공정장비다. ITRI 詢價案에는
시약·소모품·생의학·일반 용역이 많이 섞여 있어 보수적으로 걸러낸다.
"""

import re
import ssl
import time
import html as html_lib
import urllib.error
import urllib.request

from . import zh_translate

SOURCE_NAME = "ITRI (대만)"
SOURCE_CODE = "ITRI"
SOURCE_SITE_URL = "https://quotaweb.itri.org.tw/quotabrowse.aspx"
SOURCE_COUNTRY_CODE = "TW"

LIST_URL = "https://quotaweb.itri.org.tw/quotabrowse.aspx"
DETAIL_URL = LIST_URL  # 상세는 목록 페이지 내 팝업이라 별도 URL이 없다

REQUEST_TIMEOUT = 25
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3
UA = "Mozilla/5.0 (compatible; g2b-alert-bot/1.0)"

# --- 번체자 장비/공정 용어집 (이 수집기 전용) ---
TW_TERMS = {
    "半導體": "반도체", "晶圓片": "웨이퍼", "晶圓": "웨이퍼", "晶片": "칩",
    "面板": "패널", "顯示器": "디스플레이", "顯示": "디스플레이",
    "玻璃基板": "유리기판", "玻璃": "유리",
    "濺鍍": "스퍼터링", "鍍膜": "박막 증착", "蒸鍍": "증착",
    "薄膜": "박막", "沉積": "증착",
    "蝕刻": "식각", "乾式蝕刻": "건식 식각", "濕式蝕刻": "습식 식각",
    "清洗": "세정", "電漿": "플라즈마",
    "曝光": "노광", "黃光": "포토리소그래피", "光罩": "포토마스크",
    "微影": "리소그래피", "光阻": "포토레지스트",
    "研磨": "연마", "拋光": "폴리싱", "退火": "어닐링", "熱處理": "열처리",
    "電鍍": "전해 도금", "金屬化": "금속화",
    "封裝": "패키징", "先進封裝": "첨단 패키징", "接合": "본딩", "鍵合": "본딩",
    "堆疊": "적층", "後端": "후공정", "製程": "공정",
    "真空": "진공", "腔體": "챔버", "設備": "장비", "機台": "장비",
    "量測": "계측", "檢測": "검사", "試片": "시편",
    "委託": "위탁", "採購": "구매", "驗證": "검증", "實作": "구현",
    "背面": "배면", "生醫": "생의학", "藥": "의약",
    # 제목에 자주 붙는 일반 명사 — 없으면 로마자 폴백으로 떨어져 제목이
    # 읽히지 않으므로 실제 수집 결과를 보고 빈도가 높은 것부터 채웠다.
    "矽": "실리콘", "珠": "비즈", "材料": "재료", "製作": "제작",
    "平台": "플랫폼", "電路": "회로", "功能": "기능", "框架": "프레임",
    "底板": "베이스플레이트", "追蹤": "추적", "控制": "제어",
    "波束": "빔", "低軌": "저궤도", "通訊": "통신", "測溫": "온도 측정",
    "功率放大器": "전력증폭기", "功率": "전력", "放大器": "증폭기",
    "模組": "모듈", "元件": "소자", "零件": "부품", "組件": "조립품",
    "系統": "시스템", "設計": "설계", "分析": "분석", "測試": "테스트",
    "維修": "유지보수", "保養": "정비", "服務": "서비스", "整合": "통합",
    "技術": "기술", "支援": "지원", "展區": "전시구역", "計畫": "과제",
    "生產": "생산", "加工": "가공", "訂製": "주문제작", "規格": "규격",
    "及": " 및 ", "與": " 및 ", "之": " ",
}

# 관련성: 아래 신호가 있어야 포함(번체/영문 모두 확인)
EQUIPMENT_TERMS = [
    "半導體", "晶圓", "晶片", "面板", "顯示", "玻璃基板",
    "濺鍍", "鍍膜", "蒸鍍", "薄膜", "沉積", "蝕刻", "電漿",
    "曝光", "黃光", "光罩", "微影", "光阻",
    "研磨", "拋光", "退火", "熱處理", "電鍍", "金屬化",
    "封裝", "接合", "鍵合", "堆疊", "後端", "真空", "腔體",
    "semiconductor", "wafer", "oled", "lcd", "panel", "sputter", "cvd",
    "pvd", "ald", "etch", "cmp", "lithography", "tgv",
]

# 장비 신호가 있어도 이 신호가 함께 있으면 우리 대상이 아니다
# (ITRI 詢價案에는 생의학·제약·환경·일반 시설 건이 많이 섞여 있다).
HARD_EXCLUDE_TERMS = [
    "生醫", "醫療", "藥", "細胞", "蛋白", "食品", "農", "環保", "廢水",
    "清潔服務", "保全", "餐飲", "旅遊", "保險", "印刷", "文具",
    "冷氣", "空調", "消防", "裝修", "修繕", "工程申請", "室裝",
    "電腦", "筆電", "伺服器", "軟體", "網路設備", "顯示卡",
]

CATEGORY_MAP = {
    "디스플레이 장비": ["面板", "顯示", "oled", "lcd", "panel", "display"],
    "TGV 장비": ["玻璃基板", "玻璃", "tgv", "glass"],
}


def build_ssl_context():
    """이 서버 인증서에는 Subject Key Identifier 확장이 빠져 있어, 엄격
    검증(VERIFY_X509_STRICT)을 기본으로 켜는 Python 3.13+ 에서는
    handshake가 실패한다(GitHub Actions의 Python 3.12에서는 기본이 비엄격
    이라 정상 접속된다). 인증서 체인 검증과 호스트명 확인은 그대로 두고
    RFC 5280 엄격 플래그만 끈다 — 검증을 비활성화하는 것이 아니다."""
    ctx = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


SSL_CONTEXT = build_ssl_context()


def fetch(url):
    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=SSL_CONTEXT) as res:
                raw = res.read()
            for enc in ("utf-8", "big5", "cp950"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < MAX_RETRY_ATTEMPTS:
                delay = RETRY_DELAY_SECONDS * attempt
                print(f"[ITRI] 요청 실패({exc}), {delay}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(delay)
    raise RuntimeError(f"ITRI 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def normalize(text):
    return re.sub(r"\s+", " ", html_lib.unescape(text or "")).strip()


def strip_tags(raw):
    return normalize(re.sub(r"<[^>]+>", " ", raw or ""))


def contains(text, term):
    low = text.lower()
    if re.search(r"[一-鿿]", term):
        return term in text
    return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", low) is not None


def is_relevant(title):
    for term in HARD_EXCLUDE_TERMS:
        if contains(title, term):
            return False, f"제외 신호({term})"
    for term in EQUIPMENT_TERMS:
        if contains(title, term):
            return True, None
    return False, "장비 신호 없음"


def match_categories(title):
    cats = []
    for cat, terms in CATEGORY_MAP.items():
        if any(contains(title, t) for t in terms):
            cats.append(cat)
    if not cats or any(contains(title, t) for t in ["半導體", "晶圓", "晶片", "封裝", "蝕刻", "濺鍍", "薄膜", "semiconductor", "wafer"]):
        if "반도체 장비" not in cats:
            cats.insert(0, "반도체 장비")
    return cats


def translate_tw(text):
    """번체자 용어집으로 먼저 치환하고, 남은 한자는 zh_translate의 로마자
    폴백에 맡긴다. 반환: (한국어 우선 표기, 번역 완료 여부)"""
    if not text:
        return text, True
    result = text
    replaced = 0
    for src, dst in sorted(TW_TERMS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if src in result:
            result = result.replace(src, dst)
            replaced += 1
    romanized, _ok = zh_translate.translate(result)
    # 용어집이 하나도 안 걸렸거나 한자가 많이 남아 로마자로 떨어졌으면
    # 제목만으로 내용 파악이 어렵다고 보고 미완료로 표시한다.
    still_cjk = bool(re.search(r"[一-鿿]", result))
    complete = replaced > 0 and not still_cjk
    return romanized, complete


def parse_date(value):
    """'20261202' → '2026-12-02'. 형식이 아니면 None."""
    v = re.sub(r"\D", "", value or "")
    if len(v) != 8:
        return None
    y, m, d = int(v[0:4]), int(v[4:6]), int(v[6:8])
    if not (2000 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def parse_list(html):
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [strip_tags(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 9:
            continue
        case_no = cells[0]
        if not re.match(r"^[A-Z0-9]{8,}$", case_no):
            continue
        rows.append({
            "caseNo": case_no,
            "seq": cells[1],
            "title": re.sub(r"\s*/\s*$", "", cells[2]).strip(),
            "qty": cells[3],
            "deliveryDue": parse_date(cells[4]),
            "officer": cells[7] if len(cells) > 7 else "",
            "quoteDue": parse_date(cells[8]) if len(cells) > 8 else None,
        })
    return rows


def build_item(row):
    original_title = row["title"]
    ko_title, ok = translate_tw(original_title)
    categories = match_categories(original_title)
    return {
        "id": f"itri{row['caseNo']}-{row['seq']}",
        "title": ko_title,
        "translatedTitle": ko_title,
        "originalTitle": original_title,
        "translationIncomplete": not ok,
        "org": "ITRI(대만 산업기술연구원)",
        "originalOrg": "工業技術研究院",
        "country": "대만",
        "countryCode": SOURCE_COUNTRY_CODE,
        "region": None,
        "status": None,
        "dueDate": row.get("quoteDue"),
        "postedDate": None,
        "keywords": categories,
        "classificationStatus": None if categories else "미분류/검토 필요",
        "budget": None,
        "contractMethod": "詢價案(견적 요청)",
        "deliveryCondition": f"履約期限 {row['deliveryDue']}" if row.get("deliveryDue") else None,
        "paymentCondition": None,
        "eligibility": None,
        "description": f"수량 {row['qty']} · 案號 {row['caseNo']} (항목 {row['seq']})" if row.get("qty") else None,
        "attachments": [],
        "url": DETAIL_URL,
        "originalUrl": DETAIL_URL,
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "sourceSiteUrl": SOURCE_SITE_URL,
        "sourceCountry": SOURCE_COUNTRY_CODE,
        "sourceType": "Taiwan Site",
        "detectedLanguage": "zh-TW",
        "noticeType": "정식입찰",
        "projectNo": row["caseNo"],
    }


def collect():
    html = fetch(LIST_URL)
    rows = parse_list(html)
    print(f"[ITRI] 조회 대상(raw): {len(rows)}건")

    included, excluded = [], {}
    for row in rows:
        ok, reason = is_relevant(row["title"])
        if ok:
            included.append(row)
        else:
            excluded[reason] = excluded.get(reason, 0) + 1
    top = sorted(excluded.items(), key=lambda kv: -kv[1])[:3]
    print(f"[ITRI] 관련성 없어 제외: {sum(excluded.values())}건 (주요 사유: {top})")

    items = [build_item(r) for r in included]
    incomplete = sum(1 for i in items if i["translationIncomplete"])
    print(f"[ITRI] 최종 포함: {len(items)}건 (번역 미완료 {incomplete}건)")
    return items
