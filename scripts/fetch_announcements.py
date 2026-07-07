"""
나라장터(조달청) 입찰공고정보서비스에서 공고를 수집해
카테고리로 분류한 뒤 data/announcements.json으로 저장한다.

공공데이터포털 활용신청: "조달청_나라장터 입찰공고정보서비스"
- 서비스명: BidPublicInfoService
- 오퍼레이션: getBidPblancListInfoServc
- 엔드포인트: https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc
- 인증키는 환경변수 G2B_API_KEY 로 전달한다 (GitHub Actions secrets 사용).

API 키가 없으면(로컬 테스트 등) 기존 JSON을 건드리지 않고 종료한다.

주의: data.go.kr 오픈API는 인증키가 잘못되었거나 승인 대기 중이면
type=json을 요청해도 XML 에러 응답을 준다. 이 스크립트는 그런 경우를
감지해서 에러 메시지를 출력하고 기존 데이터를 보존한 채 종료한다.

분류 방식: 나라장터 API의 공고명 검색 파라미터(bidNtceNm)는 실제로는
서버 단에서 제목을 필터링해주지 않는 것으로 확인되어(모든 검색어에 대해
같은 전체 목록이 돌아옴), 사용에 의존하지 않는다. 대신 조회 기간 내
전체 공고를 한 번의 페이지네이션으로 받아온 뒤, 카테고리별 내부 검색어
사전(CATEGORY_MATCH_TERMS)으로 로컬에서 제목을 검사해 분류한다.
공고 제목에 카테고리명 자체("반도체 장비" 등)가 그대로 있어야 하는 게
아니라, 사전에 등록된 세부 검색어 중 하나라도 포함되면 매칭된다.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta

API_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"

# 사용자에게 노출되는 최상위 관심 분야 (홈 화면 토글 카드 / 결과 화면 그룹)
CATEGORIES = ["반도체 장비", "디스플레이 장비", "도금 장비"]

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

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "announcements.json")

# 하루 1회 실행이지만 실행 지연/실패에 대비해 최근 한 달을 조회해 누락을 방지하고,
# 마지막에 공고번호 기준으로 중복 제거한다.
LOOKBACK_DAYS = 30
NUM_OF_ROWS = 500
MAX_PAGES = 100


def fetch_page(service_key: str, begin_dt: str, end_dt: str, page_no: int, num_of_rows: int = NUM_OF_ROWS):
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
        raise RuntimeError(f"API 요청 실패 (HTTP {exc.code}): {exc.read().decode('utf-8', 'ignore')[:300]}") from exc

    raw = raw.strip()
    if raw.startswith("<"):
        # 인증키 오류 등으로 XML 에러 응답이 온 경우
        raise RuntimeError(f"API가 JSON이 아닌 응답을 반환했습니다 (인증키/승인 상태를 확인하세요): {raw[:300]}")

    payload = json.loads(raw)
    header = payload.get("response", {}).get("header", {})
    result_code = str(header.get("resultCode", ""))
    if result_code not in ("00", "0"):
        raise RuntimeError(f"API 에러 응답: {header.get('resultCode')} {header.get('resultMsg')}")

    return payload


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


def normalize_text(text: str):
    return text.replace(" ", "").lower()


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
    }


def collect_items(service_key: str):
    now = datetime.now()
    begin = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d0000")
    end = now.strftime("%Y%m%d2359")

    print(f"조회 기간: {begin} ~ {end} (최근 {LOOKBACK_DAYS}일)")

    seen_ids = set()
    items = []
    page_no = 1
    raw_count = 0
    skipped_invalid = 0
    unmatched_count = 0

    while page_no <= MAX_PAGES:
        payload = fetch_page(service_key, begin, end, page_no)
        rows, total_count = extract_rows(payload)
        if page_no == 1:
            print(f"API 응답 totalCount(전체 공고 수, 카테고리 분류 전): {total_count}")
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
                print(f"공고 파싱 중 오류(건너뜀): {exc}")
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

    print(f"전체 조회 건수(raw): {raw_count}")
    print(f"카테고리 매칭 안 되어 제외된 건수: {unmatched_count}")
    print(f"제목/마감일 누락 등으로 제외된 건수: {skipped_invalid}")
    print(f"최종 저장 대상 건수(중복 제거 후): {len(items)}")
    for category in CATEGORIES:
        count = sum(1 for item in items if category in item["keywords"])
        print(f"  - {category}: {count}건")

    return items


def main():
    service_key = os.environ.get("G2B_API_KEY")
    if not service_key:
        print("G2B_API_KEY가 설정되지 않아 수집을 건너뜁니다 (기존 데이터 유지).")
        sys.exit(0)

    try:
        items = collect_items(service_key)
    except Exception as exc:  # noqa: BLE001
        print(f"공고 수집 중 오류 발생: {exc}")
        sys.exit(1)

    # 마감일이 지난 공고는 제외하고, 마감일 기준으로 정렬
    today = datetime.now().date()
    items = [
        item for item in items
        if datetime.strptime(item["dueDate"], "%Y-%m-%d").date() >= today
    ]
    items.sort(key=lambda item: item["dueDate"])

    output = {
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "items": items,
    }

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"{len(items)}건의 공고를 저장했습니다.")


if __name__ == "__main__":
    main()
