"""
나노종합기술원(NNFC) 입찰공고 게시판 수집기.

공식 API/RSS 확인되지 않아 공개 게시판 HTML을 직접 파싱한다.
로그인/CAPTCHA/접근제한이 전혀 없는 공개 게시판만 대상으로 하며,
어떤 우회 기법도 사용하지 않는다.

게시판 구조 (2026-07 기준, 실제 페이지를 확인해 작성. eGovFrame 계열):
- 목록: https://www.nnfc.re.kr/bbs/BBSMSTR_000000000003/list.do?pageIndex={n}
  각 행: <button class="link btn-view" data-ntt-id="ID"><strong class="bbs-subject-txt">제목</strong>
         ... <td class="regDate">YYYY-MM-DD</td>
  페이지당 20건, 목록 조회 시점(2026-07) 기준 총 58페이지(약 1,156건)
- 상세: https://www.nnfc.re.kr/bbs/BBSMSTR_000000000003/view.do?nttId={ID}
  (JS는 form POST로 이동하지만 GET + nttId 쿼리파라미터로도 동일하게 렌더링됨을 확인함)
  마감일/예산은 본문 자유 텍스트에 있어 정규식으로 추출한다
  (예: "입찰서 제출 마감일시 : 2026.07.15. 10:00",
  "견적서제출마감일시 : 2026. 06. 04. 10:00",
  "사업예산 : 125,400,000원(VAT 포함)"). 못 찾으면 None으로 남겨
  프론트가 "마감일 확인 필요"로 표시하게 한다 (억지로 만들지 않는다).

분류 방식 (KANC와 다름, 아래 이유로 default-include 채택):
이 게시판은 "알림마당 > 입찰공고"라는 이름 그대로 나노종합기술원이 직접
발주하는 조달 공고만 모아둔 전용 게시판이다. 실제 목록을 확인해보면
"300mm 실리콘 건식식각 공정용 칠러", "200mm 수직형 산질화막 성장로"처럼
장비/부품명을 그대로 제목에 쓰고 "구매"/"장비" 같은 일반 키워드를 굳이
쓰지 않는 경우가 많아, KANC처럼 "장비 신호가 있어야 포함" 방식을 쓰면
실제 장비 공고를 놓치는 경우가 많았다(테스트로 확인). 따라서 여기서는
"서비스/행사/교육/결과안내 등 명백한 비-장비 신호가 없으면 기본 포함"
방식을 쓴다. 매각/취소는 그대로 하드 제외한다.
"""

import re
import time
import html as html_lib
import urllib.request
import urllib.error

from .common import normalize_text, TGV_STRONG_TERMS

SOURCE_NAME = "나노종합기술원"
SOURCE_CODE = "NNFC"

BASE_URL = "https://www.nnfc.re.kr"
LIST_URL_TMPL = BASE_URL + "/bbs/BBSMSTR_000000000003/list.do?pageIndex={page}"
DETAIL_URL_TMPL = BASE_URL + "/bbs/BBSMSTR_000000000003/view.do?nttId={ntt_id}"

LOOKBACK_DAYS = 30
MAX_LIST_PAGES = 10  # 페이지당 20건 * 10페이지 = 최대 200건까지만 확인 (충분한 버퍼)
REQUEST_TIMEOUT = 20
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3
PAGE_DELAY_SECONDS = 0.5

HARD_EXCLUDE_TERMS = ["매각", "취소"]

# 입찰이 아니라 이미 끝난 절차에 대한 안내(결과 발표)는 열려있는 기회가
# 아니므로 제외한다.
RESULT_NOTICE_TERMS = ["결과안내", "평가결과", "낙찰결과", "선정결과"]

# 서비스성/행사성 신호. 이 중 하나라도 있으면 제외한다(장비 관련 단어가
# 같이 있어도 이 신호가 우선한다 — 예: "XR 교육 플랫폼 제작 용역"은
# "장비"/"제작"이 있어도 "교육"이 있으므로 제외).
SERVICE_EXCLUDE_TERMS = [
    "용역", "교육", "전시", "고도화", "안전보건", "행사", "홍보", "위탁", "컨설팅",
]

CATEGORY_HINTS = {
    "디스플레이 장비": ["디스플레이", "oled", "lcd", "패널", "글라스"],
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
                print(f"[NNFC] 요청 실패({exc}), {RETRY_DELAY_SECONDS}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"NNFC 페이지 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def strip_tags(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


ROW_PATTERN = re.compile(
    r'data-ntt-id="(?P<nttid>[^"]+)".*?'
    r'bbs-subject-txt">(?P<title>[^<]+)<.*?'
    r'class="regDate">\s*(?P<date>\d{4}-\d{2}-\d{2})\s*</td>',
    re.S,
)


def parse_list_page(raw_html: str):
    rows = []
    for m in ROW_PATTERN.finditer(raw_html):
        title = html_lib.unescape(m.group("title")).strip()
        rows.append({
            "ntt_id": m.group("nttid"),
            "title": title,
            "list_date": m.group("date"),  # YYYY-MM-DD (이미 정규 형식)
        })
    return rows


def classify(title: str):
    t = normalize_text(title)
    if any(term in t for term in HARD_EXCLUDE_TERMS):
        return "exclude_hard"
    if any(normalize_text(term) in t for term in RESULT_NOTICE_TERMS):
        return "exclude_result"
    if any(normalize_text(term) in t for term in SERVICE_EXCLUDE_TERMS):
        return "exclude_service"
    return "include"


def match_categories(title: str):
    t = normalize_text(title)
    matched = [cat for cat, terms in CATEGORY_HINTS.items() if any(normalize_text(term) in t for term in terms)]
    # TGV는 유리기판/TGV 등 "강한 신호"가 있을 때만 인정한다. "도금"/"plating"
    # 단어만 있는 경우(예: 반도체용 일반 도금 장비)는 TGV로 보지 않는다.
    if any(normalize_text(term) in t for term in TGV_STRONG_TERMS):
        matched.append("TGV 장비")
    return matched or ["반도체 장비"]


def notice_type(title: str):
    return "소액수의계약" if "소액수의계약" in title else "정식입찰"


def extract_due_date(text: str, registered_date: str = None):
    patterns = [
        r"(?:입찰서|견적서)\s*제출\s*마감일시\s*[:：]\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})",
        r"마감일시\s*[:：]\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})",
        r"입찰\s*마감\s*[:：]\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})",
        r"견적\s*마감\s*[:：]\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})",
        r"접수\s*마감\s*[:：]\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})",
        # "입찰개시일 및 마감일 : 2026.06.19. 10:00 ~ 2026.06.30. 10:00" 처럼
        # 시작일~종료일 범위로 표기된 경우 종료일을 사용
        r"마감일\s*[:：].{0,40}?~\s*(\d{4})\.(\d{1,2})\.(\d{1,2})",
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
    m = re.search(r"(?:사업예산|배정예산|추정가격|기초금액)\s*[:：]\s*([\d,]+)\s*원", text)
    if m:
        try:
            amount = int(m.group(1).replace(",", ""))
        except ValueError:
            amount = 0
        if amount > 0:
            return f"{amount:,}원"

    # 외화로만 배정예산이 표기된 경우(예: "배정예산 : JPY(¥) 150,000,000")는
    # 원화로 임의 환산하지 않고 원래 통화 그대로 표시한다.
    m = re.search(r"(?:사업예산|배정예산)\s*[:：]\s*(USD|JPY|EUR|CNY)\s*[\(（][^)）]*[\)）]?\s*([\d,]+)", text)
    if m:
        currency, amount = m.groups()
        return f"{currency} {amount}"

    return None


def extract_notice_no(title: str):
    m = re.search(r"제\s*[\d\-–]+\s*호", title)
    if m:
        return re.sub(r"\s+", "", m.group(0))
    return None


def extract_labeled_text(text: str, label: str, max_len: int = 60):
    """NNFC 문서 템플릿이 "나. 라벨 : 값" 식과 "1.6. 라벨 : 값" 식이 섞여 있고,
    "납품장소 및 인도조건 : 값"처럼 라벨 뒤에 다른 말이 붙어 콜론이 바로
    오지 않는 경우도 있어, 라벨 뒤 30자 이내에서 가장 가까운 콜론을 찾아
    그 다음 값을 사용한다. 다음 항목 표시("나. ", "1.6. ")가 나오면 그 앞까지만 쓴다."""
    idx = text.find(label)
    if idx == -1:
        return None
    colon_idx = None
    for i in range(idx, min(idx + 30, len(text))):
        if text[i] in ":：":
            colon_idx = i
            break
    if colon_idx is None:
        return None
    raw = text[colon_idx + 1: colon_idx + 1 + max_len + 20]
    stop = re.search(r"\s(?:[가-힣]\s*[.)]|\d{1,2}\.\d{1,2}\.)\s", raw)
    if stop:
        raw = raw[:stop.start()]
    raw = raw[:max_len]
    if len(raw) == max_len and " " in raw:
        raw = raw[:raw.rfind(" ")]
    return raw.strip() or None


ATTACHMENT_PATTERN = re.compile(
    r'data-atch-file-id="(?P<file_id>[^"]+)"\s+data-file-sn="(?P<file_sn>[^"]+)"[^>]*>(?P<inner>.*?)</a>',
    re.S,
)


def extract_attachments(detail_html: str):
    attachments = []
    for m in ATTACHMENT_PATTERN.finditer(detail_html):
        name = strip_tags(m.group("inner"))
        name = re.sub(r"\s*\[[\d.]+\s*[KMG]?B\]\s*$", "", name).strip()
        if not name:
            continue
        url = f"{BASE_URL}/cmm/fms/{m.group('file_id')}/{m.group('file_sn')}/FileDown.do"
        attachments.append({"name": name, "url": url})
    return attachments


def build_item(ntt_id: str, list_title: str, list_date: str, detail_html: str):
    text = strip_tags(detail_html)

    # 상세페이지 <title> 태그는 "제목 입찰공고 < 알림마당 < 나노종합기술원"처럼
    # 사이트 브레드크럼이 붙어 나와 목록에서 이미 확인한 깔끔한 제목을 그대로 쓴다.
    title = list_title

    due_date = extract_due_date(text, registered_date=list_date)
    budget = extract_budget(text)
    notice_no = extract_notice_no(title)
    contract_method = extract_labeled_text(text, "계약방법")
    delivery_place = extract_labeled_text(text, "납품장소")

    description_parts = [f"공고유형: {notice_type(title)}"]
    if notice_no:
        description_parts.append(f"공고번호: {notice_no}")
    if contract_method:
        description_parts.append(f"계약방법: {contract_method}")
    description = " · ".join(description_parts)

    return {
        "id": f"nttid{ntt_id}",
        "title": title,
        "org": "나노종합기술원",
        "country": "국내",
        "countryCode": "KR",
        "status": "진행중",
        "dueDate": due_date,
        "postedDate": list_date,
        "keywords": match_categories(title),
        "budget": budget,
        "contractMethod": contract_method,
        "deliveryCondition": delivery_place,
        "paymentCondition": None,
        "eligibility": None,
        "description": description,
        "attachments": extract_attachments(detail_html),
        "url": DETAIL_URL_TMPL.format(ntt_id=ntt_id),
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "noticeType": notice_type(title),
    }


def collect():
    """NNFC 게시판을 최근 LOOKBACK_DAYS일 범위로 수집해 표준 스키마 아이템 리스트를 반환한다."""
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date()

    items = []
    stats = {
        "raw": 0,
        "hard_excluded": 0,
        "result_excluded": 0,
        "service_excluded": 0,
        "included": 0,
    }

    stop = False
    for page in range(1, MAX_LIST_PAGES + 1):
        if stop:
            break
        print(f"[NNFC {page}/{MAX_LIST_PAGES}] 목록 페이지 요청 중...")
        try:
            list_html = fetch_html(LIST_URL_TMPL.format(page=page))
        except RuntimeError as exc:
            print(f"[NNFC {page}] 목록 페이지 요청 실패, 이후 페이지 중단: {exc}")
            break

        rows = parse_list_page(list_html)
        if not rows:
            print(f"[NNFC {page}] 게시물 없음, 중단")
            break

        for row in rows:
            if row["list_date"] < cutoff.isoformat():
                stop = True
                break

            stats["raw"] += 1
            verdict = classify(row["title"])
            if verdict == "exclude_hard":
                stats["hard_excluded"] += 1
                continue
            if verdict == "exclude_result":
                stats["result_excluded"] += 1
                continue
            if verdict == "exclude_service":
                stats["service_excluded"] += 1
                continue

            try:
                detail_html = fetch_html(DETAIL_URL_TMPL.format(ntt_id=row["ntt_id"]))
            except RuntimeError as exc:
                print(f"[NNFC nttId={row['ntt_id']}] 상세 페이지 요청 실패(건너뜀): {exc}")
                continue

            item = build_item(row["ntt_id"], row["title"], row["list_date"], detail_html)
            items.append(item)
            stats["included"] += 1

            time.sleep(PAGE_DELAY_SECONDS)

        time.sleep(PAGE_DELAY_SECONDS)

    print(f"[NNFC] 조회 대상(raw): {stats['raw']}건")
    print(f"[NNFC] 매각/취소 등 하드 제외: {stats['hard_excluded']}건")
    print(f"[NNFC] 결과안내(마감된 절차) 제외: {stats['result_excluded']}건")
    print(f"[NNFC] 서비스성(용역/교육/전시 등) 제외: {stats['service_excluded']}건")
    print(f"[NNFC] 최종 포함: {stats['included']}건")

    return items


if __name__ == "__main__":
    result = collect()
    print(f"\n=== 테스트 결과: 총 {len(result)}건 수집 ===")
    for item in result[:5]:
        print(f"- [{item['noticeType']}] {item['title']} | 마감일: {item['dueDate']} | 예산: {item['budget']} | {item['keywords']}")
