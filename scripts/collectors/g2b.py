"""
나라장터(조달청) 입찰공고정보서비스 수집기.

공공데이터포털 활용신청: "조달청_나라장터 입찰공고정보서비스"
- 서비스명: BidPublicInfoService
- 오퍼레이션: getBidPblancListInfoServc
- 엔드포인트: https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc
- 인증키는 환경변수 G2B_API_KEY 로 전달한다 (GitHub Actions secrets 사용).

환경변수가 없으면(로컬 테스트 등) collect()가 빈 리스트를 반환한다
(orchestrator가 기존 G2B 데이터를 그대로 유지하도록 처리).

주의: data.go.kr 오픈API는 인증키가 잘못되었거나 승인 대기 중이면
type=json을 요청해도 XML 에러 응답을 준다. 이 스크립트는 그런 경우를
감지해서 에러를 던지고, orchestrator가 이를 잡아 기존 데이터를 보존한다.

분류 방식: 나라장터 API의 공고명 검색 파라미터(bidNtceNm)는 실제로는
서버 단에서 제목을 필터링해주지 않는 것으로 확인되어(모든 검색어에 대해
같은 전체 목록이 돌아옴), 사용에 의존하지 않는다. 대신 조회 기간 내
전체 공고를 한 번의 페이지네이션으로 받아온 뒤, 카테고리별 내부 검색어
사전(CATEGORY_MATCH_TERMS)으로 로컬에서 제목을 검사해 분류한다.

안정성: 조회 기간(30일) 전체 공고 수가 수만 건에 달해 페이지 요청이
많다 보니 나라장터 서버가 일시적으로 502/503/504를 반환하는 경우가
있다. fetch_page()는 이런 일시적 오류를 감지해 점진적으로 대기시간을
늘려가며(3초→10초→20초→40초→60초) 최대 5회까지 재시도하고, 정상
페이지 요청 사이에도 0.7초씩 쉬어 서버 부하를 줄인다. 페이지당 요청
건수(NUM_OF_ROWS)는 응답 크기가 커지면 502 가능성이 높아질 수 있어
500건으로 유지한다.
"""

import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from .common import CATEGORIES, normalize_text

SOURCE_NAME = "나라장터"
SOURCE_CODE = "G2B"

API_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"

# 카테고리별 내부 매칭 사전. 공고 제목에 카테고리명이 그대로 없어도,
# 아래 세부 검색어 중 하나라도 포함되면 해당 카테고리로 분류된다.
CATEGORY_MATCH_TERMS = {
    "반도체 장비": [
        "반도체", "웨이퍼", "wafer", "세정", "검사 장비", "자동화 설비",
        "이송 시스템", "로봇", "EFEM", "FOUP", "클린룸", "공정 장비",
    ],
    "디스플레이 장비": [
        "디스플레이", "OLED", "LCD", "패널", "글라스", "세정",
        "검사 장비", "자동화 설비", "이송 시스템", "트롤리",
    ],
    "도금 장비": [
        "도금", "plating", "전해도금", "무전해도금", "TGV",
        "Through Glass Via", "유리기판", "관통전극", "glass substrate",
    ],
}

# 하루 1회 실행이지만 실행 지연/실패에 대비해 최근 한 달을 조회해 누락을 방지하고,
# 마지막에 공고번호 기준으로 중복 제거한다.
LOOKBACK_DAYS = 30
NUM_OF_ROWS = 500  # 응답 크기가 커지면 502 가능성이 높아질 수 있어 우선 유지
MAX_PAGES = 100
PAGE_DELAY_SECONDS = 0.7  # 정상 페이지 요청 사이의 대기시간 (0.5~1초 권장)

# 502/503/504 등 일시적 오류에 대한 재시도 설정
MAX_RETRY_ATTEMPTS = 5
RETRY_DELAYS = [3, 10, 20, 40, 60]  # 재시도 1~5회차 전 대기 시간(초), 점진적으로 증가
RETRYABLE_HTTP_CODES = {502, 503, 504}


class RetryableAPIError(Exception):
    """502/503/504 등 재시도하면 성공할 가능성이 있는 일시적 오류."""

    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


def request_once(service_key: str, begin_dt: str, end_dt: str, page_no: int, num_of_rows: int):
    params = {
        "serviceKey": service_key,
        "pageNo": str(page_no),
        "numOfRows": str(num_of_rows),
        "inqryDiv": "1",  # 1: 공고게시일시 기준 조회
        "inqryBgnDt": begin_dt,  # yyyyMMddHHmm
        "inqryEndDt": end_dt,
        "type": "json",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as res:
            raw = res.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")[:300]
        if exc.code in RETRYABLE_HTTP_CODES:
            raise RetryableAPIError(body, status_code=exc.code) from exc
        raise RuntimeError(f"API 요청 실패 (HTTP {exc.code}): {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        # 타임아웃/연결 오류도 일시적일 가능성이 높아 재시도 대상으로 처리
        raise RetryableAPIError(f"네트워크 오류: {exc}") from exc

    raw = raw.strip()
    if raw.startswith("<"):
        # 인증키 오류 등으로 XML 에러 응답이 온 경우 (재시도해도 소용없는 오류)
        raise RuntimeError(f"API가 JSON이 아닌 응답을 반환했습니다 (인증키/승인 상태를 확인하세요): {raw[:300]}")

    payload = json.loads(raw)
    header = payload.get("response", {}).get("header", {})
    result_code = str(header.get("resultCode", ""))
    if result_code not in ("00", "0"):
        raise RuntimeError(f"API 에러 응답: {header.get('resultCode')} {header.get('resultMsg')}")

    return payload


def fetch_page(service_key: str, begin_dt: str, end_dt: str, page_no: int, num_of_rows: int = NUM_OF_ROWS, total_pages=None):
    """502/503/504, 네트워크 오류는 점진적으로 대기시간을 늘려가며 최대 5회 재시도한다.

    로그 예시:
      [12/32] 페이지 수집 완료
      [13/32] HTTP 502 발생 - 3초 후 재시도 1/5
      [13/32] 재시도 성공
    """
    prefix = f"[G2B {page_no}/{total_pages}]" if total_pages else f"[G2B {page_no}]"

    for attempt in range(MAX_RETRY_ATTEMPTS + 1):  # 0 = 최초 시도, 1~5 = 재시도
        try:
            payload = request_once(service_key, begin_dt, end_dt, page_no, num_of_rows)
            print(f"{prefix} {'재시도 성공' if attempt > 0 else '페이지 수집 완료'}")
            return payload
        except RetryableAPIError as exc:
            status_label = f"HTTP {exc.status_code}" if exc.status_code else "네트워크 오류"
            if attempt < MAX_RETRY_ATTEMPTS:
                delay = RETRY_DELAYS[attempt]
                print(f"{prefix} {status_label} 발생 - {delay}초 후 재시도 {attempt + 1}/{MAX_RETRY_ATTEMPTS}")
                time.sleep(delay)
            else:
                print(f"{prefix} {status_label} - {MAX_RETRY_ATTEMPTS}회 재시도 후에도 실패")
                raise RuntimeError(
                    f"페이지 {page_no} 요청이 {status_label} 상태로 {MAX_RETRY_ATTEMPTS}회 재시도 후에도 실패했습니다."
                ) from exc


def extract_rows(payload: dict):
    body = payload.get("response", {}).get("body", {})
    items_field = body.get("items", [])

    # data.go.kr 오픈API는 items가 배열이거나, {"item": [...]} 형태로 한 번 더
    # 감싸져 오는 경우가 있어 두 형태 모두 처리한다.
    if isinstance(items_field, dict):
        rows = items_field.get("item", [])
    else:
        rows = items_field

    if isinstance(rows, dict):
        rows = [rows]

    return rows, int(body.get("totalCount", 0) or 0)


def match_categories(title: str):
    """제목에 카테고리별 내부 검색어가 하나라도 포함되면 그 카테고리를 매칭시킨다.
    한 공고가 여러 카테고리에 해당하면 모두 반환한다(중복 표시 허용)."""
    norm_title = normalize_text(title)
    matched = []
    for category, terms in CATEGORY_MATCH_TERMS.items():
        if any(normalize_text(term) in norm_title for term in terms):
            matched.append(category)
    return matched


def normalize_date(raw: str):
    # API가 "2026-07-10 18:00:00" 또는 "20260710" 형태로 줄 수 있어 앞 10자리만 사용
    if not raw:
        return None
    raw = str(raw).strip()
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return None


def format_budget(row: dict):
    raw = row.get("asignBdgtAmt") or row.get("presmptPrce") or row.get("presmptAmt")
    if not raw:
        return None
    try:
        amount = int(str(raw).replace(",", "").strip())
    except ValueError:
        return str(raw)
    if amount <= 0:
        return None
    return f"{amount:,}원"


def build_description(row: dict):
    parts = []
    if row.get("ntceKindNm"):
        parts.append(f"공고종류: {row['ntceKindNm']}")
    if row.get("bidMethdNm"):
        parts.append(f"입찰방식: {row['bidMethdNm']}")
    if row.get("cntrctCnclsMthdNm"):
        parts.append(f"계약방법: {row['cntrctCnclsMthdNm']}")
    if row.get("dminsttNm"):
        parts.append(f"수요기관: {row['dminsttNm']}")
    return " · ".join(parts) if parts else None


def build_detail_url(row: dict):
    return (
        row.get("bidNtceDtlUrl")
        or row.get("bidNtceUrl")
        or "https://www.g2b.go.kr"
    )


def build_item(row: dict, matched: list):
    title = row.get("bidNtceNm", "").strip()
    due = normalize_date(row.get("bidClseDt") or row.get("opengDt"))
    if not title or not due:
        return None

    bid_no = row.get("bidNtceNo", "")
    bid_ord = row.get("bidNtceOrd", "")

    return {
        "id": f"{bid_no}-{bid_ord}" if bid_no else title,
        "title": title,
        "org": row.get("ntceInsttNm") or row.get("dminsttNm") or "발주기관 미상",
        "dueDate": due,
        "keywords": matched,
        "budget": format_budget(row),
        "eligibility": row.get("bidprcPsblIndstrytyNm") or row.get("prtcptPsblRgnNm"),
        "description": build_description(row),
        "url": build_detail_url(row),
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "noticeType": None,
    }


def collect():
    """G2B 공고를 수집해 표준 스키마의 아이템 리스트를 반환한다.
    G2B_API_KEY가 없으면 빈 리스트를 반환한다(orchestrator가 기존 데이터를 유지)."""
    service_key = os.environ.get("G2B_API_KEY")
    if not service_key:
        print("[G2B] G2B_API_KEY가 설정되지 않아 수집을 건너뜁니다.")
        return []

    now = datetime.now()
    begin = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d0000")
    end = now.strftime("%Y%m%d2359")

    print(f"[G2B] 조회 기간: {begin} ~ {end} (최근 {LOOKBACK_DAYS}일)")

    seen_ids = set()
    items = []
    page_no = 1
    raw_count = 0
    skipped_invalid = 0
    unmatched_count = 0
    total_pages = None

    while page_no <= MAX_PAGES:
        payload = fetch_page(service_key, begin, end, page_no, total_pages=total_pages)
        rows, total_count = extract_rows(payload)
        if page_no == 1:
            print(f"[G2B] API 응답 totalCount(전체 공고 수, 카테고리 분류 전): {total_count}")
            total_pages = max(1, -(-total_count // NUM_OF_ROWS))  # ceil division
            print(f"[G2B] 총 {total_pages}페이지를 요청할 예정입니다.")
        if not rows:
            break
        raw_count += len(rows)

        for row in rows:
            title = row.get("bidNtceNm", "")
            matched = match_categories(title)
            if not matched:
                unmatched_count += 1
                continue
            try:
                item = build_item(row, matched)
            except Exception as exc:  # noqa: BLE001
                print(f"[G2B] 공고 파싱 중 오류(건너뜀): {exc}")
                skipped_invalid += 1
                continue
            if not item:
                skipped_invalid += 1
                continue
            if item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            items.append(item)

        if page_no * NUM_OF_ROWS >= total_count:
            break
        page_no += 1
        time.sleep(PAGE_DELAY_SECONDS)  # 연속 요청으로 인한 서버 부하/502 방지

    print(f"[G2B] 전체 조회 건수(raw): {raw_count}")
    print(f"[G2B] 카테고리 매칭 안 되어 제외된 건수: {unmatched_count}")
    print(f"[G2B] 제목/마감일 누락 등으로 제외된 건수: {skipped_invalid}")
    print(f"[G2B] 최종 수집 건수(중복 제거 후): {len(items)}")
    for category in CATEGORIES:
        count = sum(1 for item in items if category in item["keywords"])
        print(f"[G2B]   - {category}: {count}건")

    return items
