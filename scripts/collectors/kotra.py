"""
KOTRA(대한무역투자진흥공사) "사업신청" 목록에서 반도체·디스플레이·TGV/유리기판
장비 관련 해외 프로젝트/상담회 정보를 수집한다.

KOTRA는 일반적인 "입찰 사이트"가 아니다. 여기서 찾는 것은 정식 입찰공고가
아니라 수출상담회, 구매상담회, 공급사/파트너사 모집, 해외 신규 투자·증설
프로젝트처럼 장비 발주로 이어질 수 있는 "영업 기회 정보"다. 그래서
noticeType도 "사전규격"/"정식입찰"이 아니라 "프로젝트 정보"/"공급사 모집"/
"수출상담회"/"구매상담회"로 분류한다.

사이트 구조 (2026-07 기준, 사용자가 제공한 실제 상세 URL을 기준으로 분석):
- 목록은 두 개의 POST 기반 AJAX 엔드포인트에서 서버 렌더링 HTML 카드로 온다
  (공식 JSON API/RSS는 없음):
    1) /module/subhome/bizAply/selectBmBizRcritYListNewAjax.do
       (sch_appl_yn=N&sch_nation_cd=Y) — 신청기한이 있는 사업
    2) /module/subhome/bizAply/selectBmBizAllListAjax.do
       (sch_appl_yn=Y&sch_nation_cd=Y) — 상시신청 가능 사업
  페이지네이션은 pageNo/pageNo2/pageNoA + startCount=(pageNo-1)*listCount
  오프셋 방식이다. 연속으로 여러 조합을 빠르게 시도하면 500 에러가 나는
  것을 확인했는데(파라미터 자체 문제가 아니라 요청 간격이 짧을 때 발생),
  요청 사이에 지연을 두면 정상 응답한다 — 실제로 수 초 대기 후 재시도해
  정상 동작을 확인했다. 이는 접근 제한 우회가 아니라 일반적인 크롤링
  예의(요청 속도 제한)이며, 로그인/CAPTCHA는 전혀 필요하지 않다.
- 상세: /subList/20000020753/subhome/bizAply/selectBizMntInfoDetail.do?dtlBizMntNo={ID}&cpbizYn=N
  GET 요청만으로 정상 렌더링됨을 사용자가 제공한 실제 URL로 확인했다.
  제목(hidden input dtlBizName), 사업유형/신청기간/개최기간/사업진행장소/
  주관부서, 본문 textarea#txtArea(사업내용 요약), 태그 목록(nHtagArea —
  국가명이 태그로 직접 들어있어 국가 판별에 사용), 첨부파일
  (data-atch-file-id 아님, storFileId/fileSn 기반 다운로드 링크)이 모두
  서버 렌더링 HTML에 그대로 있다.

분류: KOTRA는 전 산업 분야를 다루므로 G2B처럼 관련성 판단이 중요하다.
제목에 반도체/디스플레이/TGV 관련 키워드가 있는 경우에만 상세페이지를
가져와 태그·본문까지 포함해 다시 한 번 관련성을 확인한다("장비", "자동화",
"유리" 같은 단어 하나만으로는 포함하지 않는다 — 예: "사무실 자동화
프로그램", "유리 공예 전시회"는 제외되어야 한다).

마감 처리: 신청기간이 이미 지난 프로젝트라도 향후 재발주·후속 프로젝트
가능성이 있어 삭제하지 않는다. 대신 status를 "진행중"/"마감임박"/"마감"으로
구분해 저장하고, orchestrator가 KOTRA는 날짜 기준으로 걸러내지 않도록
예외 처리한다(다른 수집원에는 영향 없음).
"""

import re
import time
import html as html_lib
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta

from .common import normalize_text, TGV_STRONG_TERMS

SOURCE_NAME = "대한무역투자진흥공사"
SOURCE_CODE = "KOTRA"
SOURCE_SITE_URL = "https://www.kotra.or.kr/"

BASE_URL = "https://www.kotra.or.kr"
DETAIL_URL_TMPL = BASE_URL + "/subList/20000020753/subhome/bizAply/selectBizMntInfoDetail.do?dtlBizMntNo={biz_no}&cpbizYn=N"

LIST_ENDPOINTS = [
    # (엔드포인트, sch_appl_yn) — 신청기한 있는 사업 / 상시신청 가능 사업
    ("/module/subhome/bizAply/selectBmBizRcritYListNewAjax.do", "N"),
    ("/module/subhome/bizAply/selectBmBizAllListAjax.do", "Y"),
]

PAGE_SIZE = 20
MAX_LIST_PAGES = 6  # 리스트당 최대 120건까지 확인 (실측 총량 71~104건 커버)
REQUEST_TIMEOUT = 20
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 4
PAGE_DELAY_SECONDS = 2.0  # 짧은 간격 연속 요청 시 500 에러가 나는 것을 확인해 넉넉히 대기

# --- 사용자가 지정한 산업 관련성 키워드 (단어 하나만으로 포함하지 않고,
# 이 목록에 있는 비교적 구체적인 용어가 있어야 관련성이 있다고 판단한다) ---
SEMI_TERMS = [
    "반도체", "semiconductor", "wafer", "웨이퍼", "etch", "etching", "식각",
    "세정", "cleaning", "ald", "cvd", "pvd", "plasma", "vacuum", "진공",
    "scrubber", "efem", "foup", "loadport", "load port", "후공정", "패키징",
    "advancedpackaging", "advanced packaging",
]
DISPLAY_TERMS = [
    "디스플레이", "display", "oled", "microoled", "micro oled", "microled",
    "micro led", "lcd", "panel", "패널", "glass", "유리기판", "세정장비",
    "식각장비", "이송장비", "물류장비", "자동화장비",
]
# TGV 카테고리는 common.TGV_STRONG_TERMS(유리기판/TGV 등 명확한 신호)만 쓴다.
# "도금"/"plating"만 있는 경우(반도체 일반 도금 공정 등)는 TGV로 보지 않는다
# (common.TGV_WEAK_PLATING_TERMS로 정의돼 있지만 카테고리 매칭에는 쓰지 않음 —
# 완전히 삭제한 건 아니고, 강한 신호와 함께 있을 때를 위해 남겨둔 참고 목록).
CATEGORY_TERM_MAP = {
    "반도체 장비": SEMI_TERMS,
    "디스플레이 장비": DISPLAY_TERMS,
    "TGV 장비": TGV_STRONG_TERMS,
}

NOTICE_TYPE_RULES = [
    ("수출상담회", ["수출상담회"]),
    ("구매상담회", ["구매상담회", "바이어상담"]),
    ("공급사 모집", ["공급사모집", "파트너모집", "파트너사모집"]),
]

COUNTRY_NAME_TO_CODE = {
    "중국": "CN", "베트남": "VN", "인도": "IN", "미국": "US", "일본": "JP",
    "독일": "DE", "대만": "TW", "태국": "TH", "인도네시아": "ID",
    "말레이시아": "MY", "멕시코": "MX", "브라질": "BR", "러시아": "RU",
    "싱가포르": "SG", "필리핀": "PH", "캄보디아": "KH", "영국": "GB",
    "프랑스": "FR", "이탈리아": "IT", "스페인": "ES", "캐나다": "CA",
    "호주": "AU", "튀르키예": "TR", "폴란드": "PL", "아랍에미리트": "AE",
    "사우디": "SA", "사우디아라비아": "SA",
}


def fetch(url: str, data: bytes = None) -> str:
    req = urllib.request.Request(
        url, data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; g2b-alert-bot/1.0)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST" if data is not None else "GET",
    )
    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
                return res.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < MAX_RETRY_ATTEMPTS:
                print(f"[KOTRA] 요청 실패({exc}), {RETRY_DELAY_SECONDS}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"KOTRA 페이지 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def strip_tags(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


CARD_TITLE_PATTERN = re.compile(
    r'dtlBizMntNo=(?P<id>[A-Za-z0-9]+)&(?:amp;)?cpbizYn=N\'?\);">(?P<title>[^<]+)</a>',
)


def fetch_list_page(endpoint: str, sch_appl_yn: str, page_no: int) -> str:
    start_count = (page_no - 1) * PAGE_SIZE
    form = {
        "pageNo": page_no, "pageNo2": page_no, "pageNoA": page_no,
        "pageSize": PAGE_SIZE, "listCount": PAGE_SIZE,
        "query": "", "collection": "business_application", "sch_biz_name": "",
        "schwrdVal": "", "sch_appl_yn": sch_appl_yn, "sch_nation_cd": "Y",
        "startCount": start_count,
    }
    body = "&".join(f"{k}={v}" for k, v in form.items())
    return fetch(BASE_URL + endpoint, data=body.encode("utf-8"))


def parse_list_cards(raw_html: str):
    cards = []
    for m in CARD_TITLE_PATTERN.finditer(raw_html):
        title = html_lib.unescape(m.group("title")).strip()
        cards.append({"biz_no": m.group("id"), "title": title})
    return cards


def term_matches(text: str, term: str):
    """공백 제거 후 부분일치로 찾되, 한글 2글자 이하의 짧고 일반적인 단어는
    다른 단어 속 우연한 부분 문자열로 걸리는 사례가 있어("세정"이 "관세정책"
    안에 포함되는 식) 공백으로 구분된 독립 토큰일 때만 인정한다."""
    is_short_korean = len(term) <= 2 and re.fullmatch(r"[가-힣]+", term)
    if is_short_korean:
        padded = f" {text.lower()} "
        return f" {term} " in padded
    return normalize_text(term) in normalize_text(text)


def has_industry_signal(text: str):
    return any(
        term_matches(text, term)
        for terms in CATEGORY_TERM_MAP.values()
        for term in terms
    )


def match_categories(text: str):
    matched = []
    for category, terms in CATEGORY_TERM_MAP.items():
        if any(term_matches(text, term) for term in terms):
            matched.append(category)
    return matched


def notice_type(text: str):
    t = normalize_text(text)
    for label, terms in NOTICE_TYPE_RULES:
        if any(normalize_text(term) in t for term in terms):
            return label
    return "프로젝트 정보"


def parse_date(raw: str):
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def extract_period(html_text: str, label: str):
    """상세페이지 표의 "라벨</th> ... <td>YYYY-MM-DD ~ YYYY-MM-DD</td>" 형태를 찾는다.
    caption 설명문("사업유형, 모집회원구분, 개최기간, 신청기간, ...")에도 라벨
    텍스트가 먼저 나오기 때문에, 실제 표 헤더 셀(뒤에 </th>가 바로 오는 경우)만
    찾도록 "라벨\\s*</th>" 패턴으로 매칭한다."""
    m = re.search(re.escape(label) + r"\s*</th>", html_text)
    if not m:
        return None, None
    window = html_text[m.end():m.end() + 300]
    if "상시" in strip_tags(window)[:20]:
        return None, None
    dates = re.findall(r"(\d{4}-\d{1,2}-\d{1,2})", window)
    if not dates:
        return None, None
    start = parse_date(dates[0])
    end = parse_date(dates[1]) if len(dates) > 1 else start
    return start, end


def extract_tags(detail_html: str):
    m = re.search(r'class="nHtagArea"\s*>\s*<ul>(.*?)</ul>', detail_html, re.S)
    if not m:
        return []
    return [html_lib.unescape(t).strip() for t in re.findall(r"<li>([^<]+)</li>", m.group(1))]


def extract_summary(detail_html: str):
    m = re.search(r'id="txtArea"[^>]*>(.*?)</textarea>', detail_html, re.S)
    if not m:
        return None
    text = html_lib.unescape(m.group(1))
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text or None


def extract_country(tags: list, location_hint: str):
    for tag in tags:
        if tag in COUNTRY_NAME_TO_CODE:
            return tag, COUNTRY_NAME_TO_CODE[tag]
    if location_hint == "국내":
        return "국내", "KR"
    if location_hint == "해외":
        return "해외(국가 확인 필요)", None
    return "확인 필요", None


def extract_organization(detail_html: str):
    """caption 설명문에도 "주관부서"가 먼저 나오므로, 실제 표 헤더 셀
    (뒤에 </th>가 바로 오는 경우)만 찾아 바로 다음 <td> 내용을 사용한다."""
    m = re.search(r"주관부서\s*</th>\s*<td>\s*(.*?)\s*</td>", detail_html, re.S)
    if not m:
        return None
    value = strip_tags(m.group(1))
    return value or None


def extract_attachments(detail_html: str):
    pattern = re.compile(
        r'href="(/kmodule/file/fileDown\.do\?storFileId=[^"]+)"[^>]*>\s*([^<]+?)\s*</a>',
    )
    attachments = []
    for href, name in pattern.findall(detail_html):
        attachments.append({
            "name": html_lib.unescape(name).strip(),
            "url": BASE_URL + html_lib.unescape(href),
        })
    return attachments


def compute_status(deadline: str):
    if not deadline:
        return "진행중"  # 상시신청 등 마감일이 없는 경우
    try:
        d = datetime.strptime(deadline, "%Y-%m-%d").date()
    except ValueError:
        return "진행중"
    today = date.today()
    if d < today:
        return "마감"
    if d - today <= timedelta(days=7):
        return "마감임박"
    return "진행중"


def build_item(biz_no: str, list_title: str, detail_html: str):
    detail_text = strip_tags(detail_html)
    tags = extract_tags(detail_html)
    summary = extract_summary(detail_html)

    combined_text = " ".join(filter(None, [list_title, summary, " ".join(tags)]))
    if not has_industry_signal(combined_text):
        return None  # 상세까지 확인해도 관련성 없음 -> 제외

    apply_start, apply_end = extract_period(detail_html.replace("&nbsp;", " "), "신청기간")
    event_start, event_end = extract_period(detail_html.replace("&nbsp;", " "), "개최기간")

    location_hint = None
    if "사업진행장소" in detail_text:
        idx = detail_text.find("사업진행장소")
        window = detail_text[idx:idx + 60]
        if "해외" in window:
            location_hint = "해외"
        elif "국내" in window:
            location_hint = "국내"

    country, country_code = extract_country(tags, location_hint)
    org = extract_organization(detail_html) or "확인 필요"

    return {
        "id": f"kotra{biz_no}",
        "title": list_title,
        "org": org,
        "country": country,
        "countryCode": country_code,
        "status": compute_status(apply_end),
        "dueDate": apply_end,
        "postedDate": apply_start,
        "keywords": match_categories(combined_text),
        "budget": None,  # KOTRA 사업신청 페이지에는 예산/참가비 정보가 없는 경우가 대부분
        "contractMethod": None,
        "deliveryCondition": None,
        "paymentCondition": None,
        "eligibility": None,
        "description": summary,
        "attachments": extract_attachments(detail_html),
        "url": DETAIL_URL_TMPL.format(biz_no=biz_no),
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "sourceSiteUrl": SOURCE_SITE_URL,
        "noticeType": notice_type(combined_text),
        "eventPeriod": f"{event_start} ~ {event_end}" if event_start else None,
    }


def collect():
    """KOTRA 사업신청 목록에서 반도체/디스플레이/TGV 관련 프로젝트만 수집한다."""
    items = []
    seen_ids = set()
    stats = {"raw": 0, "title_prefiltered_out": 0, "detail_excluded": 0, "included": 0}

    for endpoint, sch_appl_yn in LIST_ENDPOINTS:
        for page_no in range(1, MAX_LIST_PAGES + 1):
            print(f"[KOTRA] {endpoint} 페이지 {page_no}/{MAX_LIST_PAGES} 요청 중...")
            try:
                list_html = fetch_list_page(endpoint, sch_appl_yn, page_no)
            except RuntimeError as exc:
                print(f"[KOTRA] 목록 페이지 요청 실패, 이 목록은 여기서 중단: {exc}")
                break

            cards = parse_list_cards(list_html)
            if not cards:
                break

            for card in cards:
                if card["biz_no"] in seen_ids:
                    continue
                stats["raw"] += 1

                if not has_industry_signal(card["title"]):
                    stats["title_prefiltered_out"] += 1
                    continue

                seen_ids.add(card["biz_no"])
                try:
                    detail_html = fetch(DETAIL_URL_TMPL.format(biz_no=card["biz_no"]))
                except RuntimeError as exc:
                    print(f"[KOTRA {card['biz_no']}] 상세 페이지 요청 실패(건너뜀): {exc}")
                    continue

                item = build_item(card["biz_no"], card["title"], detail_html)
                if item is None:
                    stats["detail_excluded"] += 1
                    continue

                items.append(item)
                stats["included"] += 1
                time.sleep(PAGE_DELAY_SECONDS)

            time.sleep(PAGE_DELAY_SECONDS)

    print(f"[KOTRA] 조회 대상(raw): {stats['raw']}건")
    print(f"[KOTRA] 제목 단계에서 관련성 없어 제외: {stats['title_prefiltered_out']}건")
    print(f"[KOTRA] 상세 확인 후 관련성 없어 제외: {stats['detail_excluded']}건")
    print(f"[KOTRA] 최종 포함: {stats['included']}건")

    return items


if __name__ == "__main__":
    result = collect()
    print(f"\n=== 테스트 결과: 총 {len(result)}건 수집 ===")
    for item in result:
        print(f"- [{item['noticeType']}] {item['title']} | 국가: {item['country']} | 신청마감: {item['dueDate']} | 상태: {item['status']} | {item['keywords']}")
