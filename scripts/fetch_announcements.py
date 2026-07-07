"""
여러 공고 수집원(collector)을 실행해 결과를 합친 뒤 data/announcements.json으로 저장한다.

현재 등록된 수집원:
- collectors.kanc : 한국나노기술원(KANC) 입찰공고 게시판
- collectors.nnfc : 나노종합기술원(NNFC) 입찰공고 게시판

(과거 나라장터(G2B) 오픈API 수집기가 있었으나, 전체 공고 대비 실제
장비 구매 공고 비율이 낮고 502 오류·복잡한 필터링 문제로 제거했다.
KDIA/KOTRA는 조사 결과 자동 수집 가능한 공개 입찰 게시판을 찾지 못해
보류 중이다.)

새 수집원을 추가하려면:
1. scripts/collectors/<이름>.py 에 collect() -> list[dict] 함수를 구현
   (반환 형식은 scripts/collectors/common.py 상단 docstring 참고)
2. 아래 COLLECTORS 리스트에 추가

한 수집원이 실패해도(네트워크 오류, 인증키 문제 등) 다른 수집원과 기존
데이터에는 영향을 주지 않는다 — 실패한 수집원은 이전 실행 결과를 그대로
유지하고, 성공한 수집원의 결과만 새로 반영한다.
"""

import json
import os
from datetime import date, datetime

from collectors import kanc, nnfc

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "announcements.json")

COLLECTORS = [
    ("KANC", kanc),
    ("NNFC", nnfc),
]


def load_existing_items():
    if not os.path.exists(DATA_PATH):
        return []
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("items", [])
    except (json.JSONDecodeError, OSError):
        return []


def run_collector(name, module, existing_items):
    """수집기를 실행한다. 실패하면 해당 소스의 기존 데이터를 그대로 반환해
    다른 수집원이나 이미 저장된 데이터에 영향을 주지 않는다."""
    fallback = [item for item in existing_items if item.get("sourceCode") == name]
    try:
        items = module.collect()
    except Exception as exc:  # noqa: BLE001
        print(f"[{name}] 수집 중 오류로 이번 실행분은 건너뜁니다(기존 데이터 유지): {exc}")
        return fallback

    if not items:
        print(f"[{name}] 이번 실행에서 수집된 항목이 없어 기존 데이터를 유지합니다.")
        return fallback

    return items


def sort_key(item):
    # dueDate가 없는 공고("마감일 확인 필요")는 맨 뒤로 보낸다.
    due = item.get("dueDate")
    if not due:
        return (1, "")
    return (0, due)


def is_still_open(item):
    due = item.get("dueDate")
    if not due:
        return True  # 마감일을 알 수 없는 공고는 임의로 제외하지 않는다.
    try:
        return datetime.strptime(due, "%Y-%m-%d").date() >= date.today()
    except ValueError:
        return True


def main():
    existing_items = load_existing_items()

    all_items = []
    for name, module in COLLECTORS:
        all_items.extend(run_collector(name, module, existing_items))

    all_items = [item for item in all_items if is_still_open(item)]
    all_items.sort(key=sort_key)

    output = {
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "items": all_items,
    }

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    by_source = {}
    for item in all_items:
        code = item.get("sourceCode", "?")
        by_source[code] = by_source.get(code, 0) + 1
    summary = ", ".join(f"{code} {count}건" for code, count in by_source.items())
    print(f"총 {len(all_items)}건의 공고를 저장했습니다 ({summary}).")


if __name__ == "__main__":
    main()
