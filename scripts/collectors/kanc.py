"""
한국나노기술원(KANC) 입찰공고 게시판 수집기.

공식 API/RSS가 없어(사전 조사 결과) 공개 게시판 HTML을 직접 파싱한다.
로그인/CAPTCHA/접근제한이 전혀 없는 공개 게시판만 대상으로 하며,
어떤 우회 기법도 사용하지 않는다.

게시판 구조 (2026-07 기준, 실제 페이지를 확인해 작성):
- 목록: https://kanc.re.kr/gnb04/snb02_01.do?page={n}&hcid=38
  각 행: <td class="hide">번호</td> <td class="list_title"><a href="...cid=N...">제목</a></td>
         <td class="list_date">YYYY.MM.DD</td> ...
- 상세: https://kanc.re.kr/gnb04/snb02_01.do?mode=view&page={n}&cid={cid}&hcid=38
  제목은 <p class="subject">...</p>, 등록일은 "등록일" 라벨 옆 span.
  마감일/예산은 표/본문 자유 텍스트 안에 있어 정규식으로 추출한다
  (예: "의견마감일시 2026-07-13", "입찰서제출 마감일시 : ~ 2026.07.08",
  "사업예산 : USD ... / KRW 704,573,000"). 못 찾으면 None으로 남겨
  프론트가 "마감일 확인 필요"로 표시하게 한다 (억지로 만들지 않는다).

분류 2단계:
1. 하드 제외: "매각", "취소" (공고 자체가 무효/반대 목적)
2. 장비 발주 신호(EQUIPMENT_INCLUDE_TERMS)가 있으면 포함 (서비스성 단어가
   같이 있어도 장비 신호가 우선한다 — 예: "반도체 연구용 장비 구매"는 포함)
3. 장비 신호 없이 서비스성 단어(SERVICE_EXCLUDE_TERMS)만 있으면 제외
4. 둘 다 없으면 기본 제외 (신호가 전혀 없는 공고는 보수적으로 걸러낸다)

noticeType: 제목에 "사전규격"이 있으면 "사전규격", 없으면 "정식입찰".
사전규격공개는 제외 대상이 아니라 오히려 우선 수집 대상이다.
"""

import re
import time
import html as html_lib
import urllib.request
import urllib.error

from .common import normalize_text

SOURCE_NAME = "한국나노기술원"
SOURCE_CODE = "KANC"

BASE_URL = "https://kanc.re.kr"
LIST_URL_TMPL = BASE_URL + "/gnb04/snb02_01.do?page={page}&hcid=38"
DETAIL_URL_TMPL = BASE_URL + "/gnb04/snb02_01.do?mode=view&page={page}&cid={cid}&hcid=38"

LOOKBACK_DAYS = 30
MAX_LIST_PAGES = 10  # 페이지당 10건 * 10페이지 = 최대 100건까지만 확인 (충분한 버퍼)
REQUEST_TIMEOUT = 20
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3
PAGE_DELAY_SECONDS = 0.5

HARD_EXCLUDE_TERMS = ["매각", "취소"]

SERVICE_EXCLUDE_TERMS = [
    "운영용역", "위탁", "교육", "행사", "컨설팅", "cctv", "유지관리용역", "관리용역", "홍보",
]

EQUIPMENT_INCLUDE_TERMS = [
    "구매", "제작", "설치", "개조", "구축", "사전규격",
    "식각", "증착", "세정", "검사", "자동화", "이송", "도금", "tgv",
    "장비", "설비", "장치", "시스템",
]

# KANC 자체가 이미 반도체/나노 장비 전문 기관 게시판이므로, 나라장터처럼
# 넓은 필터를 두지 않고 명확한 신호가 있을 때만 디스플레이/도금으로
# 분류하고 나머지는 기본값으로 반도체 장비에 둔다.
CATEGORY_HINTS = {
    "디스플레이 장비": ["디스플레이", "oled", "lcd", "패널", "글라스"],
    "도금 장비": ["도금", "plating", "tgv", "유리기판", "관통전극"],
}


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
                print(f"[KANC] 요청 실패({exc}), {RETRY_DELAY_SECONDS}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"KANC 페이지 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def strip_tags(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


ROW_PATTERN = re.compile(
    r'<td class="hide">(?P<no>\d+)</td>.*?'
    r'cid=(?P<cid>\d+)&amp;hcid=38">(?P<title>.*?)</a>.*?'
    r'<td class="list_date">(?P<date>[\d.]+)</td>',
    re.S,
)


def parse_list_page(raw_html: str):
    rows = []
    for m in ROW_PATTERN.finditer(raw_html):
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", m.group("title"))).strip()
        rows.append({
            "cid": m.group("cid"),
            "title": title,
            "list_date": m.group("date").strip(),  # YYYY.MM.DD
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
    return matched or ["반도체 장비"]


def notice_type(title: str):
    return "사전규격" if "사전규격" in title else "정식입찰"


def extract_due_date(text: str, registered_date: str = None):
    """마감일 후보를 우선순위대로 뽑되, 등록일보다 이전인 후보는 오타로 보고
    건너뛴다(실제로 KANC 게시물 중 '의견마감일시'에 연도를 잘못 적은 사례가 있었다:
    등록일 2026-06-24인데 의견마감일시가 2025-06-29로 표기됨).
    """
    patterns = [
        r"의견마감일시\s*[:：]?\s*(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})",
        r"마감일시\s*[:：]?\s*~?\s*(\d{4})\.(\d{1,2})\.(\d{1,2})",
        # "공고기간", "규격공개기간" 등 "...기간 : 시작일 - 종료일" 형태 전반을 잡고 종료일을 사용
        r"기간\s*[:：]?\s*\d{4}\.\d{1,2}\.\d{1,2}\.?(?:\([^)]*\))?\s*[-~]\s*(\d{4})\.(\d{1,2})\.(\d{1,2})",
    ]
    candidates = []
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            y, mo, d = m.groups()
            candidates.append(f"{int(y):04d}-{int(mo):02d}-{int(d):02d}")

    for candidate in candidates:
        if registered_date and candidate < registered_date:
            continue
        return candidate
    return None


def extract_budget(text: str):
    m = re.search(r"사업예산[^K]{0,60}KRW\s*([\d,]+)", text)
    if not m:
        return None
    try:
        amount = int(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if amount <= 0:
        return None
    return f"{amount:,}원"


def extract_notice_no(title: str, text: str):
    m = re.search(r"제\s*[\d\-]+\s*호", title)
    if m:
        return re.sub(r"\s+", "", m.group(0))
    m = re.search(r"공고번호\s*[:：]?\s*(제[\d\-]+호)", text)
    return m.group(1) if m else None


def extract_registered_date(text: str):
    m = re.search(r"등록일\s*(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})", text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


def build_item(cid: str, list_title: str, list_date: str, detail_html: str):
    text = strip_tags(detail_html)

    subject_m = re.search(r'<p class="subject">(.*?)</p>', detail_html, re.S)
    title = html_lib.unescape(re.sub(r"<[^>]+>", "", subject_m.group(1))).strip() if subject_m else list_title

    registered = extract_registered_date(text) or normalize_list_date(list_date)
    due_date = extract_due_date(text, registered_date=registered)
    budget = extract_budget(text)
    notice_no = extract_notice_no(title, text)

    description_parts = [f"공고유형: {notice_type(title)}"]
    if notice_no:
        description_parts.append(f"공고번호: {notice_no}")
    description = " · ".join(description_parts)

    return {
        "id": f"cid{cid}",
        "title": title,
        "org": "한국나노기술원",
        "dueDate": due_date,
        "keywords": match_categories(title),
        "budget": budget,
        "eligibility": None,
        "description": description,
        "url": DETAIL_URL_TMPL.format(page=1, cid=cid),
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "noticeType": notice_type(title),
        "registeredDate": registered,
    }


def normalize_list_date(list_date: str):
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", list_date)
    if not m:
        return None
    y, mo, d = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def collect():
    """KANC 게시판을 최근 LOOKBACK_DAYS일 범위로 수집해 표준 스키마 아이템 리스트를 반환한다."""
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date()

    items = []
    stats = {
        "raw": 0,
        "hard_excluded": 0,
        "service_excluded": 0,
        "no_signal_excluded": 0,
        "included": 0,
        "pre_spec": 0,
        "formal": 0,
    }

    stop = False
    for page in range(1, MAX_LIST_PAGES + 1):
        if stop:
            break
        print(f"[KANC {page}/{MAX_LIST_PAGES}] 목록 페이지 요청 중...")
        try:
            list_html = fetch_html(LIST_URL_TMPL.format(page=page))
        except RuntimeError as exc:
            print(f"[KANC {page}] 목록 페이지 요청 실패, 이후 페이지 중단: {exc}")
            break

        rows = parse_list_page(list_html)
        if not rows:
            print(f"[KANC {page}] 게시물 없음, 중단")
            break

        for row in rows:
            list_date = normalize_list_date(row["list_date"])
            if list_date and list_date < cutoff.isoformat():
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
                detail_html = fetch_html(DETAIL_URL_TMPL.format(page=page, cid=row["cid"]))
            except RuntimeError as exc:
                print(f"[KANC cid={row['cid']}] 상세 페이지 요청 실패(건너뜀): {exc}")
                continue

            item = build_item(row["cid"], row["title"], row["list_date"], detail_html)
            items.append(item)
            stats["included"] += 1
            if item["noticeType"] == "사전규격":
                stats["pre_spec"] += 1
            else:
                stats["formal"] += 1

            time.sleep(PAGE_DELAY_SECONDS)

        time.sleep(PAGE_DELAY_SECONDS)

    print(f"[KANC] 조회 대상(raw): {stats['raw']}건")
    print(f"[KANC] 매각/취소 등 하드 제외: {stats['hard_excluded']}건")
    print(f"[KANC] 서비스성(용역/위탁/교육 등) 제외: {stats['service_excluded']}건")
    print(f"[KANC] 신호 없음 제외: {stats['no_signal_excluded']}건")
    print(f"[KANC] 최종 포함: {stats['included']}건 (사전규격 {stats['pre_spec']}건 / 정식입찰 {stats['formal']}건)")

    return items


if __name__ == "__main__":
    result = collect()
    print(f"\n=== 테스트 결과: 총 {len(result)}건 수집 ===")
    for item in result[:5]:
        print(f"- [{item['noticeType']}] {item['title']} | 마감일: {item['dueDate']} | 예산: {item['budget']} | {item['keywords']}")
