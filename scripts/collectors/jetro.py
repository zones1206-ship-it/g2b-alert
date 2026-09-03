"""
JETRO(일본무역진흥기구) 일본 정부조달 데이터베이스 수집기.

JETRO는 자체 조달 공고가 아니라, WTO 정부조달협정/일-EU EPA 대상인
**일본 정부·독립행정법인의 조달 공고를 영어로 모아 공개**하는 데이터베이스를
운영한다(“a single point of access on the Internet”). 그래서 AIST/RIKEN/
NIMS/일본 대학 공고가 이 한 곳에 함께 들어온다 — 기관별 수집기를 따로
만들지 않고 여기서 먼저 수집하는 이유다.

실제 페이지 구조 (2026-09 기준, 브라우저 요청을 그대로 확인해 작성):
- 검색 폼(공개 페이지, 로그인 없음):
  https://www.jetro.go.jp/en/database/procurement/  (form id="f-central")
- 목록(JSON, 폼이 그대로 호출하는 공개 엔드포인트):
  GET https://www.jetro.go.jp/view_interface.php?blockId=27911119&<폼 필드>
  응답: {"pagination":{"total":N,"perPage":30,"current":0},
         "items":[{"xid":..,"aid":"..","title":"..","date":"Sep 02, 2026",
                   "agency":"RIKEN","paKind":"Notice of Procurement (Goods & Services)"}]}
- 상세(HTML):
  https://www.jetro.go.jp/en/database/procurement/national/articles/{xid}/{aid}.html
  표: Publishing date / Type of notice / Procurement entity / Classification /
      Summay of notice(원문 오타 그대로) — 요약 본문에
      "⑺ Time limit of tender : 3 : 00 PM, 23, Oct, 2026" 형태로 마감일이 들어있다.

수집 대상은 반도체/디스플레이/TGV 및 관련 공정장비 공고로 한정한다.
JETRO 전체 공고를 다 가져오지 않고, 사용자가 지정한 장비 키워드로 검색한
결과만 후보로 삼은 뒤 제목 기준으로 한 번 더 확인한다(일반 연구장비/
의료장비/사무용품 등이 섞이지 않게).

영문 제목은 collectors/en_translate.py의 용어집으로 한국어 우선 표기를
만들고, 뜻을 확신할 수 없으면 translationIncomplete=True로 표시한다
(원문 제목/원문 링크는 항상 보존한다 — 지어내지 않는다).
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from .common import TGV_STRONG_TERMS, FetchState
from . import en_ko_argos, en_translate, translation_memory

SOURCE_NAME = "JETRO (일본)"
SOURCE_CODE = "JETRO"
SOURCE_SITE_URL = "https://www.jetro.go.jp/en/database/procurement/"
SOURCE_COUNTRY_CODE = "JP"

BASE_URL = "https://www.jetro.go.jp"
LIST_API_URL = BASE_URL + "/view_interface.php?blockId=27911119"
DETAIL_URL_TMPL = BASE_URL + "/en/database/procurement/national/articles/{xid}/{aid}.html"
LIST_PAGE_URL = BASE_URL + "/en/database/procurement/national/list.html"

# 이 사이트의 목록 엔드포인트는 브라우저에서 XHR로 호출되며, 그 요청 헤더를
# 그대로 사용한다(공개 페이지이고 로그인/CAPTCHA가 없다 — 접근 제한을
# 우회하는 것이 아니라 같은 공개 요청을 재현하는 것이다).
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
LIST_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Referer": LIST_PAGE_URL,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Language": "en-US,en;q=0.9",
}
DETAIL_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Referer": LIST_PAGE_URL,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# 검색어(장비/공정 중심). 이 사이트 검색은 영어 제목 대상이라 영문 키워드를 쓴다.
SEARCH_KEYWORDS = [
    "semiconductor", "wafer", "cleanroom", "sputtering", "etching",
    "lithography", "deposition", "display", "OLED", "glass substrate",
    "annealing", "plasma", "bonding", "packaging",
]

LOOKBACK_DAYS = 120  # 조달 공고는 게시 후 마감까지 기간이 길어 넉넉히 본다
MAX_PAGES_PER_KEYWORD = 2  # perPage=30 → 키워드당 최대 60건
REQUEST_TIMEOUT = 25
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3
REQUEST_DELAY_SECONDS = 0.8

# --- 관련성 판정 키워드 (사용자가 지정한 수집 대상) ---
SEMI_TERMS = [
    "semiconductor", "wafer", "fab", "cleanroom", "clean room",
    "advanced packaging", "semiconductor packaging", "die bonding",
    "wafer bonding", "hybrid bonding", "bonder", "photoresist",
    "lithography", "stepper", "exposure",
]
DISPLAY_TERMS = ["display", "oled", "microled", "micro led", "lcd", "panel"]
GLASS_TERMS = [
    "tgv", "through glass via", "glass substrate", "glass interposer",
    "via formation", "glass drilling",
]
PROCESS_TERMS = [
    "pvd", "sputter", "sputtering", "cvd", "pecvd", "ald", "evaporation",
    "etch", "etching", "wet etch", "dry etch", "rie", "icp", "drie",
    "cleaning", "wet cleaning", "wet bench", "plasma cleaning",
    "ecd", "electroplating", "cu plating", "copper plating", "seed layer",
    "cmp", "polishing", "annealing", "furnace", "rtp",
]
# 검사/계측은 반도체·디스플레이 맥락이 함께 있을 때만 인정한다
# (일반 연구용 SEM/현미경까지 끌어오지 않기 위해).
METROLOGY_TERMS = [
    "metrology", "inspection", "ellipsometer", "film thickness",
    "profilometer", "sem", "tem",
]
CONTEXT_TERMS = SEMI_TERMS + DISPLAY_TERMS + GLASS_TERMS + PROCESS_TERMS

# 명백히 대상이 아닌 공고(일반 연구/사무/시설). 장비 신호가 있어도 이 신호가
# 있으면 제외한다.
HARD_EXCLUDE_TERMS = [
    "office supplies", "copy machine", "copier", "vehicle", "car lease",
    "cleaning service", "security service", "catering", "uniform",
    "insurance", "travel", "accommodation", "printing service",
    "translation service", "consulting service", "recruitment",
    "software license", "personal computer", "notebook computer",
    "server rental", "network equipment", "air conditioning",
    "medical", "hospital", "pharmaceutical", "animal", "agricultur",
    "construction work", "building repair", "electricity supply",
]

CATEGORY_TERM_MAP = {
    "반도체 장비": SEMI_TERMS + PROCESS_TERMS,
    "디스플레이 장비": DISPLAY_TERMS,
    "TGV 장비": GLASS_TERMS + [t.lower() for t in TGV_STRONG_TERMS],
}


def fetch(url, headers, retries=MAX_RETRY_ATTEMPTS):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
                return res.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                delay = RETRY_DELAY_SECONDS * attempt
                print(f"[JETRO] 요청 실패({exc}), {delay}초 후 재시도 {attempt}/{retries - 1}")
                time.sleep(delay)
    raise RuntimeError(f"JETRO 요청이 {retries}회 실패했습니다: {last_error}")


def normalize(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


def lower_words(text):
    return " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()) + " "


def has_term(haystack_lower, term):
    """단어 경계로 확인한다 — 'sem'이 'assembly' 안에 우연히 들어가는 식의
    오탐을 막는다."""
    return re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", haystack_lower) is not None


def is_relevant(title):
    """제목 기준 관련성 판정.
    1) 명백한 비-대상 신호가 있으면 제외
    2) 반도체/디스플레이/유리/공정 신호가 있으면 포함
    3) 검사·계측 용어만 있는 경우는 반도체·디스플레이 맥락이 함께 있을 때만 포함
    4) 아무 신호가 없으면 제외(보수적)
    """
    low = lower_words(title)
    for term in HARD_EXCLUDE_TERMS:
        if has_term(low, term):
            return False, f"제외 신호({term})"
    for term in CONTEXT_TERMS:
        if has_term(low, term):
            return True, None
    for term in METROLOGY_TERMS:
        if has_term(low, term):
            return False, "계측/검사 용어만 있고 반도체·디스플레이 맥락 없음"
    return False, "장비 신호 없음"


def match_categories(title):
    low = lower_words(title)
    cats = []
    for cat, terms in CATEGORY_TERM_MAP.items():
        if any(has_term(low, t) for t in terms):
            cats.append(cat)
    return cats


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_list_date(text):
    """'Sep 02, 2026' → '2026-09-02'"""
    m = re.match(r"\s*([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s*(\d{4})", text or "")
    if not m:
        return None
    month = MONTHS.get(m.group(1).lower())
    if not month:
        return None
    return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"


def parse_deadline(summary_text):
    """요약 본문에서 마감일을 찾는다. 실제 표기 예:
      "⑺ Time limit of tender : 3 : 00 PM, 23, Oct, 2026"
      "Time limit for the submission of application forms : 5:00 PM, 3, Nov, 2026"
    찾지 못하면 None을 반환한다(임의로 날짜를 만들지 않는다)."""
    if not summary_text:
        return None
    # 라벨 표기가 기관마다 다르다(실제 확인한 예):
    #   "⑺ Time limit of tender : 3 : 00 PM, 23, Oct, 2026"
    #   "⑺ Time limit for tender ; 15 : 00 7, October, 2026"
    # 구분자도 ':' 와 ';' 가 섞여 쓰이므로 둘 다 받는다.
    labels = [
        r"time limit(?:\s+\w+){0,8}?",
        r"deadline(?:\s+\w+){0,8}?",
        r"due date(?:\s+\w+){0,8}?",
        r"closing date(?:\s+\w+){0,8}?",
    ]
    for label in labels:
        m = re.search(label + r"\s*[:;]\s*(.{0,90})", summary_text, re.I)
        if not m:
            continue
        chunk = m.group(1)
        d = re.search(r"(\d{1,2})\s*,\s*([A-Za-z]{3})[a-z]*\s*,\s*(\d{4})", chunk)
        if d:
            month = MONTHS.get(d.group(2).lower())
            if month:
                return f"{int(d.group(3)):04d}-{month:02d}-{int(d.group(1)):02d}"
        d = re.search(r"([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s*(\d{4})", chunk)
        if d:
            month = MONTHS.get(d.group(1).lower())
            if month:
                return f"{int(d.group(3)):04d}-{month:02d}-{int(d.group(2)):02d}"
    return None


def strip_tags(raw_html):
    import html as html_lib
    text = re.sub(r"<script.*?</script>", " ", raw_html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize(html_lib.unescape(text))


def parse_detail(html):
    """상세 페이지에서 표 항목과 요약 본문을 뽑는다."""
    import html as html_lib
    cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", html, re.S | re.I)
    cleaned = [normalize(html_lib.unescape(re.sub(r"<[^>]+>", " ", c))) for c in cells]
    fields = {}
    for i in range(len(cleaned) - 1):
        key = cleaned[i].lower().rstrip(":")
        if key in ("publishing date", "type of notice", "procurement entity",
                   "classification", "summay of notice", "summary of notice"):
            fields[key] = cleaned[i + 1]
    return fields


def search_list(keyword, page):
    params = {
        "type": "", "from": "", "to": "", "entity": "", "area": "",
        "keyword": keyword,
        "classification1": "", "classification2": "", "classification3": "",
        "deadline": "01",  # 마감일이 지나지 않은 공고만
        "deadline_from": "", "deadline_to": "",
    }
    url = LIST_API_URL + "&" + urllib.parse.urlencode(params)
    if page > 0:
        url += f"&_page={page + 1}"
    raw = fetch(url, LIST_HEADERS)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("JETRO 목록 응답이 JSON이 아닙니다(차단 또는 형식 변경 가능성)")


def build_item(row, detail_fields, detail_url):
    import html as html_lib
    original_title = normalize(html_lib.unescape(row.get("title") or ""))
    original_org = normalize(html_lib.unescape(
        detail_fields.get("procurement entity") or row.get("agency") or ""))

    # 제목은 Argos(en→ko 직접 모델) + 전문용어 보호 방식으로 옮기고, 검증에
    # 실패하거나 Argos를 쓸 수 없는 환경이면 기존 용어집 결과로 자동 폴백한다.
    ko_title, title_ok, _info = en_ko_argos.translate_title(original_title)
    ko_org, _ = en_translate.translate_org(original_org)

    summary = detail_fields.get("summay of notice") or detail_fields.get("summary of notice") or ""
    posted = parse_list_date(row.get("date")) or parse_list_date(detail_fields.get("publishing date", ""))
    due = parse_deadline(summary)

    categories = match_categories(original_title) or match_categories(summary)
    notice_type = "정식입찰"
    kind = (row.get("paKind") or "").lower()
    if "future procurement plan" in kind:
        notice_type = "사전규격"
    elif "public offering proposal" in kind or "request for comments" in kind:
        notice_type = "사전규격"

    return {
        "id": f"jetro{row.get('xid')}",
        "title": ko_title,
        "translatedTitle": ko_title,
        "originalTitle": original_title,
        "translationIncomplete": not title_ok,
        "org": ko_org or "확인 필요",
        "originalOrg": original_org,
        "country": "일본",
        "countryCode": SOURCE_COUNTRY_CODE,
        "region": None,
        "status": None,
        "dueDate": due,
        "postedDate": posted,
        "keywords": categories,
        "classificationStatus": None if categories else "미분류/검토 필요",
        "budget": None,
        "currency": None,
        "contractMethod": normalize(html_lib.unescape(row.get("paKind") or "")) or None,
        "deliveryCondition": None,
        "paymentCondition": None,
        "eligibility": None,
        "description": summary[:1200] or None,
        "attachments": [],
        "url": detail_url,
        "originalUrl": detail_url,
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "sourceSiteUrl": SOURCE_SITE_URL,
        "sourceCountry": SOURCE_COUNTRY_CODE,
        "detectedLanguage": "en",
        "noticeType": notice_type,
        "projectNo": row.get("aid"),
    }


# 목록을 실제로 읽고 파싱했는지 기록한다. "정상 수집 + 조건에 맞는
# 공고 0건"을 수집 실패로 오인하지 않기 위한 신호다(common.FetchState).
FETCH_STATE = FetchState("JETRO")


def collect():
    FETCH_STATE.reset()
    seen_xid = set()
    candidates = []
    raw_count = 0

    for keyword in SEARCH_KEYWORDS:
        for page in range(MAX_PAGES_PER_KEYWORD):
            try:
                data = search_list(keyword, page)
            except RuntimeError as exc:
                print(f"[JETRO] '{keyword}' 검색 실패, 다음 키워드로 넘어감: {exc}")
                break
            items = FETCH_STATE.mark(data.get("items") or [])
            raw_count += len(items)
            if not items:
                break
            for row in items:
                xid = row.get("xid")
                if xid is None or xid in seen_xid:
                    continue
                seen_xid.add(xid)
                candidates.append(row)
            pagination = data.get("pagination") or {}
            total = pagination.get("total") or 0
            per_page = pagination.get("perPage") or 30
            if (page + 1) * per_page >= total:
                break
            time.sleep(REQUEST_DELAY_SECONDS)
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"[JETRO] 조회 대상(raw): {raw_count}건, 중복 제거 후 {len(candidates)}건")

    relevant = []
    excluded = 0
    for row in candidates:
        import html as html_lib
        title = html_lib.unescape(row.get("title") or "")
        ok, _reason = is_relevant(title)
        if ok:
            relevant.append(row)
        else:
            excluded += 1
    print(f"[JETRO] 제목 기준 관련성 없어 제외: {excluded}건 → 상세 확인 대상 {len(relevant)}건")

    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date()
    items = []
    detail_failed = 0
    for row in relevant:
        detail_url = DETAIL_URL_TMPL.format(xid=row.get("xid"), aid=row.get("aid"))
        try:
            html = fetch(detail_url, DETAIL_HEADERS, retries=2)
        except RuntimeError as exc:
            detail_failed += 1
            print(f"[JETRO] 상세 요청 실패(건너뜀): {exc}")
            continue
        fields = parse_detail(html)
        item = build_item(row, fields, detail_url)
        if item["postedDate"]:
            try:
                if datetime.strptime(item["postedDate"], "%Y-%m-%d").date() < cutoff:
                    continue
            except ValueError:
                pass
        items.append(item)
        time.sleep(REQUEST_DELAY_SECONDS)

    incomplete = sum(1 for i in items if i.get("translationIncomplete"))
    print(f"[JETRO] 상세 요청 실패: {detail_failed}건")
    print(f"[JETRO] 최종 포함: {len(items)}건 (번역 미완료 {incomplete}건)")
    # 이번에 새로 검증을 통과한 번역을 기억해 둔다 — 같은 원문이 다음 실행에
    # 다른 한국어로 바뀌지 않게 하기 위해서다(Argos 출력이 실행마다 다르다).
    if translation_memory.save():
        print(f"[JETRO] 번역 기억 갱신: {translation_memory.stats()}")
    return items
