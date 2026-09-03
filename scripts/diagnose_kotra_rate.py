"""
KOTRA 요청 성공률 측정 (로컬 / GitHub Actions 비교용).

계층 진단(diagnose_kotra.py)에서 DNS·TCP·TLS·HTTP가 모두 정상인데도 간헐적으로
연결이 끊기는 것이 확인됐다. 여기서는 **수집기가 실제로 쓰는 요청**을 재시도
없이 여러 번 보내 "요청당 실패율"을 그대로 잰다. 재시도로 덮을 수 있는
수준인지 판단하기 위한 것이다.

과도한 요청은 하지 않는다 — 목록 12회, 상세 6회, 3초 간격.
운영 데이터는 건드리지 않는다.
"""

import os
import sys
import time

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collectors import kotra  # noqa: E402

LIST_TRIES = 12
DETAIL_TRIES = 6
GAP_SECONDS = 3


def once(fn):
    t0 = time.time()
    try:
        html = fn()
        return True, len(html), time.time() - t0, ""
    except Exception as exc:  # noqa: BLE001
        return False, 0, time.time() - t0, f"{type(exc).__name__}: {exc}"


def main():
    where = "GitHub Actions" if "--actions" in sys.argv else "로컬"
    print(f"KOTRA 요청 성공률 측정 — 실행 위치: {where}")

    kotra.MAX_RETRY_ATTEMPTS = 1  # 재시도 없이 순수 실패율을 본다

    endpoint, appl = kotra.LIST_ENDPOINTS[0]
    print(f"\n=== 목록 AJAX {LIST_TRIES}회 (재시도 없음, {GAP_SECONDS}초 간격) ===")
    ok = 0
    results = []
    for i in range(1, LIST_TRIES + 1):
        good, size, sec, err = once(lambda: kotra.fetch_list_page(endpoint, appl, 1))
        ok += good
        results.append(good)
        print(f"  {i:2d}/{LIST_TRIES} {'OK  ' if good else 'FAIL'} {size:>7,}B {sec:5.2f}s {err}")
        if i < LIST_TRIES:
            time.sleep(GAP_SECONDS)
    print(f"  → 목록 성공 {ok}/{LIST_TRIES} ({ok / LIST_TRIES * 100:.0f}%)")

    # 연속 실패가 몇 번까지 이어지는지 — 재시도 횟수를 정하는 근거가 된다.
    longest, run = 0, 0
    for good in results:
        run = 0 if good else run + 1
        longest = max(longest, run)
    print(f"  → 최장 연속 실패 {longest}회")

    detail_no = None
    for _ in range(3):
        good, _size, _sec, _err = once(lambda: kotra.fetch_list_page(endpoint, appl, 1))
        if good:
            cards = kotra.parse_list_cards(kotra.fetch_list_page(endpoint, appl, 1))
            detail_no = cards[0]["biz_no"] if cards else None
            break
        time.sleep(GAP_SECONDS)

    if not detail_no:
        print("\n상세 페이지 측정 생략(목록에서 대상 사업번호를 얻지 못함)")
        return

    print(f"\n=== 상세 페이지 {DETAIL_TRIES}회 (사업번호 {detail_no}) ===")
    ok2 = 0
    for i in range(1, DETAIL_TRIES + 1):
        good, size, sec, err = once(
            lambda: kotra.fetch(kotra.DETAIL_URL_TMPL.format(biz_no=detail_no)))
        ok2 += good
        print(f"  {i}/{DETAIL_TRIES} {'OK  ' if good else 'FAIL'} {size:>7,}B {sec:5.2f}s {err}")
        if i < DETAIL_TRIES:
            time.sleep(GAP_SECONDS)
    print(f"  → 상세 성공 {ok2}/{DETAIL_TRIES} ({ok2 / DETAIL_TRIES * 100:.0f}%)")


if __name__ == "__main__":
    main()
