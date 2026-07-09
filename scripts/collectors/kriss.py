"""
한국표준과학연구원(KRISS) 입찰공고 게시판 수집기.

KANC(kanc.py)와 완전히 동일한 구조(목록 파싱 → 4단계 관련성 판정 →
상세 페이지 파싱 → 표준 스키마 변환)를 그대로 따른다. 공식 API/RSS가
없어 공개 게시판 HTML을 직접 파싱하며, 로그인/CAPTCHA 없이 접근 가능한
공개 게시판만 대상으로 한다.

게시판 구조 (2026-07 기준, 실제 페이지를 확인해 작성):
- 목록: https://www.kriss.re.kr/board.es?mid=a10506000000&bid=0005&nPage={page}
  표 헤더: 공고번호 / 제목 / 공고일 / 입찰일
  각 행(<tr>): <td class="m_hidden">공고번호</td>
              <td class="txt_left"><a href="...list_no=N...">제목</a></td>
              <td>공고일 YYYY/MM/DD</td> <td>입찰일 YYYY/MM/DD</td>
- 상세: https://www.kriss.re.kr/board.es?mid=a10506000000&bid=0005&act=view&list_no={list_no}
  "작성일자 YYYY-MM-DD HH:MM", 바로 아래 "한국표준과학연구원 입찰공고 제 XX-XX-XXX-XX 호"
  첨부파일: <div class="file"><ul class="list"><li>파일명 텍스트 + 뒤에
    <a href="/boardDownload.es?bid=0005&list_no=N&seq=M">다운로드</a>
  나라장터 공고번호가 본문에 있으면 "R26BK01589633-000" 같은 형식(영문
  1자+연도2자리+영문2자리+숫자8자리-숫자3자리)으로 등장한다(항상 있는 건
  아니다 — 없으면 g2bBidNo는 None으로 둔다).

분류는 KANC와 동일한 4단계:
1. 하드 제외: 공고 자체가 무효/일반 생활용역인 경우
2. 장비 발주 신호(EQUIPMENT_INCLUDE_TERMS, 사용자가 지정한 반도체/디스플레이
   /TGV 관련 키워드)가 있으면 포함
3. 장비 신호 없이 서비스성 단어만 있으면 제외
4. 둘 다 없으면 기본 제외(보수적으로 걸러낸다 — 관련 없어 보이는 일반
   연구장비/시약/소모품 공고까지 전부 가져오지 않는다)
"""

import re
import time
import html as html_lib
import urllib.request
import urllib.error

from .common import normalize_text, TGV_STRONG_TERMS

SOURCE_NAME = "한국표준과학연구원"
SOURCE_CODE = "KRISS"

BASE_URL = "https://www.kriss.re.kr"
LIST_URL_TMPL = BASE_URL + "/board.es?mid=a10506000000&bid=0005&nPage={page}"
DETAIL_URL_TMPL = BASE_URL + "/board.es?mid=a10506000000&bid=0005&act=view&list_no={list_no}"

LOOKBACK_DAYS = 30
MAX_LIST_PAGES = 10
REQUEST_TIMEOUT = 20
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3
PAGE_DELAY_SECONDS = 0.5

HARD_EXCLUDE_TERMS = ["매각", "취소"]

# 일반 생활/사무 용역 — 장비 신호가 같이 있어도 이런 단어가 제목에 있으면
# 대부분 시설관리성 공고라 제외한다(KANC의 SERVICE_EXCLUDE_TERMS와 같은 역할).
SERVICE_EXCLUDE_TERMS = [
    "복사실", "청소", "경비", "차량", "위탁", "교육", "행사", "홍보",
    "컨설팅", "cctv", "인쇄", "다과", "급식", "이사", "보험", "임차",
    "청사", "시설관리",
]

# 사용자가 지정한 반도체/디스플레이/TGV 관련 장비 키워드 목록을 그대로 쓴다.
EQUIPMENT_INCLUDE_TERMS = [
    "반도체", "디스플레이", "oled", "tgv", "유리기판", "glass", "웨이퍼", "wafer",
    "플라즈마", "plasma", "진공", "vacuum", "식각", "etch", "etching",
    "증착", "deposition", "pvd", "cvd", "ald", "cmp", "세정", "cleaning",
    "레이저", "laser", "검사", "inspection", "측정", "measurement",
    "분석장비", "계측장비", "공정장비", "장비 구매", "시스템 구매", "설비",
    "챔버", "chamber", "펌프", "pump", "rf", "euv", "센서", "정밀측정",
    "나노", "박막", "thin film",
]

CATEGORY_HINTS = {
    "디스플레이 장비": ["디스플레이", "oled", "lcd", "패널", "글라스"],
}

LIST_ROW_PATTERN = re.compile(
    r'<td class="m_hidden"[^>]*>(?P<notice_no>[^<]*)</td>\s*'
    r'<td class="txt_left"[^>]*>\s*'
    r'<a href="[^"]*list_no=(?P<list_no>\d+)[^"]*"[^>]*>\s*(?P<title>.*?)</a>\s*</td>\s*'
    r'<td>(?P<posted>[\d/]+)</td>\s*'
    r'<td>(?P<due>[\d/]+)</td>',
)

G2B_BID_NO_PATTERN = re.compile(r"\b[A-Z]\d{2}[A-Z]{2}\d{8}-\d{3}\b")


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; g2b-alert-bot/1.0)"})
    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
                return res.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < MAX_RETRY_ATTEMPTS:
                print(f"[KRISS] 요청 실패({exc}), {RETRY_DELAY_SECONDS}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"KRISS 페이지 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def strip_tags(raw_html: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", raw_html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_slash_date(date_str: str):
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_str.strip())
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def parse_list_page(raw_html: str):
    rows = []
    for m in LIST_ROW_PATTERN.finditer(raw_html):
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group("title"))).strip()
        if not title:
            continue
        rows.append({
            "list_no": m.group("list_no"),
            "notice_no": html_lib.unescape(m.group("notice_no")).strip() or None,
            "title": title,
            "posted": normalize_slash_date(m.group("posted")),
            "due": normalize_slash_date(m.group("due")),
        })
    return rows


def classify(title: str):
    t = normalize_text(title)
    if any(term in t for term in HARD_EXCLUDE_TERMS):
        return "exclude_hard"
    if any(normalize_text(term) in t for term in EQUIPMENT_INCLUDE_TERMS):
        return "include"
    if any(normalize_text(term) in t for term in SERVICE_EXCLUDE_TERMS):
        return "exclude_service"
    return "exclude_no_signal"


def match_categories(title: str):
    t = normalize_text(title)
    matched = [cat for cat, terms in CATEGORY_HINTS.items() if any(normalize_text(term) in t for term in terms)]
    if any(normalize_text(term) in t for term in TGV_STRONG_TERMS):
        matched.append("TGV 장비")
    return matched or ["반도체 장비"]


def notice_type(title: str):
    if "사전규격" in title:
        return "사전규격"
    if "제안서 평가 결과" in title or "낙찰" in title or "개찰" in title:
        return "낙찰·수주결과"
    return "정식입찰"


def extract_attachments(detail_html: str):
    """<div class="file"><ul class="list"><li>파일명 ... <a href="/boardDownload...">
    구조에서 파일명(li의 첫 텍스트 노드)과 다운로드 링크를 함께 추출한다.
    첨부파일이 없는 공고도 정상 수집돼야 하므로 못 찾으면 빈 리스트를 반환한다."""
    file_block_m = re.search(r'<div class="file">(.*?)</div>\s*(?:</div>|<div class="(?!file))', detail_html, re.S)
    block = file_block_m.group(1) if file_block_m else detail_html
    attachments = []
    for li_m in re.finditer(r"<li>(.*?)</li>", block, re.S):
        li = li_m.group(1)
        href_m = re.search(r'<a[^>]+href="(/boardDownload\.es\?[^"]+)"', li)
        if not href_m:
            continue
        # <li> 안에서 <img.../> 다음, <span class="txt">... 앞에 오는 텍스트가 파일명이다.
        name_m = re.search(r"/>\s*([^<]{2,150}?)\s*<span", li, re.S)
        name = html_lib.unescape(name_m.group(1)).strip() if name_m else None
        if not name:
            continue
        attachments.append({
            "name": name,
            "url": BASE_URL + html_lib.unescape(href_m.group(1)),
        })
    return attachments


def extract_g2b_bid_no(detail_text: str):
    m = G2B_BID_NO_PATTERN.search(detail_text)
    return m.group(0) if m else None


def build_item(row: dict, detail_html: str):
    detail_text = strip_tags(detail_html)
    attachments = extract_attachments(detail_html)
    g2b_bid_no = extract_g2b_bid_no(detail_text)

    description_parts = [f"공고유형: {notice_type(row['title'])}"]
    if row["notice_no"]:
        description_parts.append(f"공고번호: {row['notice_no']}")
    description = " · ".join(description_parts)

    return {
        "id": f"kriss{row['list_no']}",
        "title": row["title"],
        "org": SOURCE_NAME,
        "country": "국내",
        "countryCode": "KR",
        "status": "진행중",
        "dueDate": row["due"],
        "postedDate": row["posted"],
        "keywords": match_categories(row["title"]),
        "budget": None,
        "contractMethod": None,
        "deliveryCondition": None,
        "paymentCondition": None,
        "eligibility": None,
        "description": description,
        "attachments": attachments,
        "url": DETAIL_URL_TMPL.format(list_no=row["list_no"]),
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "noticeType": notice_type(row["title"]),
        "projectNo": row["notice_no"],
        "g2bBidNo": g2b_bid_no,
    }


def collect():
    """KRISS 입찰공고 게시판을 최근 LOOKBACK_DAYS일 범위로 수집해 표준 스키마
    아이템 리스트를 반환한다. 반도체/디스플레이/TGV 장비 관련 신호가 있는
    공고만 포함한다(전체 공고를 무조건 다 가져오지 않는다)."""
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date().isoformat()

    items = []
    stats = {"raw": 0, "hard_excluded": 0, "service_excluded": 0, "no_signal_excluded": 0, "included": 0}

    stop = False
    for page in range(1, MAX_LIST_PAGES + 1):
        if stop:
            break
        print(f"[KRISS {page}/{MAX_LIST_PAGES}] 목록 페이지 요청 중...")
        try:
            list_html = fetch_html(LIST_URL_TMPL.format(page=page))
        except RuntimeError as exc:
            print(f"[KRISS {page}] 목록 페이지 요청 실패, 이후 페이지 중단: {exc}")
            break

        rows = parse_list_page(list_html)
        if not rows:
            print(f"[KRISS {page}] 게시물 없음, 중단")
            break

        for row in rows:
            if row["posted"] and row["posted"] < cutoff:
                stop = True
                break

            stats["raw"] += 1
            verdict = classify(row["title"])
            if verdict == "exclude_hard":
                stats["hard_excluded"] += 1
                continue
            if verdict == "exclude_service":
                stats["service_excluded"] += 1
                continue
            if verdict == "exclude_no_signal":
                stats["no_signal_excluded"] += 1
                continue

            try:
                detail_html = fetch_html(DETAIL_URL_TMPL.format(list_no=row["list_no"]))
            except RuntimeError as exc:
                print(f"[KRISS list_no={row['list_no']}] 상세 페이지 요청 실패(건너뜀): {exc}")
                continue

            item = build_item(row, detail_html)
            items.append(item)
            stats["included"] += 1
            time.sleep(PAGE_DELAY_SECONDS)

        time.sleep(PAGE_DELAY_SECONDS)

    print(f"[KRISS] 조회 대상(raw): {stats['raw']}건")
    print(f"[KRISS] 하드 제외: {stats['hard_excluded']}건")
    print(f"[KRISS] 서비스성 제외: {stats['service_excluded']}건")
    print(f"[KRISS] 신호 없음 제외: {stats['no_signal_excluded']}건")
    print(f"[KRISS] 최종 포함: {stats['included']}건")

    return items


if __name__ == "__main__":
    result = collect()
    print(f"\n=== 테스트 결과: 총 {len(result)}건 수집 ===")
    for item in result[:8]:
        print(f"- [{item['noticeType']}] {item['title']} | 마감:{item['dueDate']} | g2b:{item['g2bBidNo']} | {item['keywords']}")
