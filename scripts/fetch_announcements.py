"""
나라장터(조달청) 입찰공고정보서비스에서 공고를 수집해
키워드로 필터링한 뒤 data/announcements.json으로 저장한다.

공공데이터포털 활용신청: "조달청_나라장터 입찰공고정보서비스"
- 서비스명: BidPublicInfoService
- 엔드포인트: https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc
- 인증키는 환경변수 G2B_API_KEY 로 전달한다 (GitHub Actions secrets 사용).

API 키가 없으면(로컬 테스트 등) 기존 JSON을 건드리지 않고 종료한다.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

API_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"

KEYWORDS = [
    "반도체 장비",
    "세정 설비",
    "디스플레이 장비",
    "트롤리",
    "자동화 설비",
    "검사 장비",
    "클린룸",
    "이송 시스템",
]

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "announcements.json")


def fetch_page(service_key: str, begin_dt: str, end_dt: str, page_no: int, num_of_rows: int = 100):
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
    with urllib.request.urlopen(url, timeout=30) as res:
        body = res.read().decode("utf-8")
    return json.loads(body)


def matches_keywords(title: str):
    return [kw for kw in KEYWORDS if kw.replace(" ", "") in title.replace(" ", "")]


def normalize_date(raw: str):
    # API가 "2026-07-10 18:00:00" 또는 "20260710" 형태로 줄 수 있어 앞 10자리만 사용
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) >= 10 and raw[4] == "-" :
        return raw[:10]
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw[:10]


def collect_items(service_key: str):
    now = datetime.now()
    begin = (now - timedelta(days=1)).strftime("%Y%m%d0000")
    end = now.strftime("%Y%m%d2359")

    items = []
    page_no = 1
    while True:
        payload = fetch_page(service_key, begin, end, page_no)
        body = payload.get("response", {}).get("body", {})
        rows = body.get("items", [])
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            break

        for row in rows:
            title = row.get("bidNtceNm", "")
            matched = matches_keywords(title)
            if not matched:
                continue
            due = normalize_date(row.get("bidClseDt") or row.get("opengDt"))
            if not due:
                continue
            items.append({
                "id": row.get("bidNtceNo") or f"{row.get('bidNtceOrd', '')}-{title}",
                "title": title,
                "org": row.get("ntceInsttNm", "발주기관 미상"),
                "dueDate": due,
                "keywords": matched,
                "url": row.get("bidNtceDtlUrl") or "https://www.g2b.go.kr",
            })

        total_count = int(body.get("totalCount", 0))
        if page_no * 100 >= total_count:
            break
        page_no += 1

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

    # 마감일이 지난 공고는 제외
    today = datetime.now().date()
    items = [
        item for item in items
        if datetime.strptime(item["dueDate"], "%Y-%m-%d").date() >= today
    ]

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
