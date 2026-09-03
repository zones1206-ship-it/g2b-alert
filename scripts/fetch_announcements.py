"""
여러 공고 수집원(collector)을 실행해 결과를 합친 뒤 data/announcements.json으로 저장한다.

현재 등록된 수집원:
- collectors.kanc  : 한국나노기술원(KANC) 입찰공고 게시판
- collectors.nnfc  : 나노종합기술원(NNFC) 입찰공고 게시판
- collectors.kotra : KOTRA 사업신청 목록 중 반도체/디스플레이/TGV 관련 프로젝트
- collectors.ebnew  : 중국 비롄왕(必联网/EBNEW) 입찰/구매/낙찰결과 공고
                     (China Site — 용어집 기반 최선노력 한국어 번역, 원문 보존)
- collectors.mofcom : 중국국제초표망(chinabidding.mofcom.gov.cn, 상무부) 입찰공고
                     (China Site — EBNEW와 동일한 번역/관련성 판정 로직 재사용)
- collectors.kriss  : 한국표준과학연구원(KRISS) 입찰공고 게시판
                     (KANC와 동일한 4단계 관련성 판정 로직 재사용)
- collectors.jetro  : JETRO(일본무역진흥기구) 일본 정부조달 데이터베이스
                     (AIST/RIKEN/NIMS/일본 대학 공고가 이 한 곳에 모인다 —
                      기관별 수집기를 따로 두지 않고 여기서 먼저 수집한다.
                      영문 공고라 en_translate 용어집으로 한국어 우선 표기)
- collectors.dgist  : 대구경북과학기술원(DGIST) 입찰정보 게시판
                     (국내 공고라 번역 불필요. Actions에서 간헐적 연결
                      끊김이 있어 재시도로 커버한다)
- collectors.itri   : ITRI(대만 산업기술연구원) 採購資訊 詢價案 목록
                     (번체 중국어 — 수집기 내부 번체 용어집으로 한국어
                      표기 후 남은 한자는 zh_translate 로마자 폴백)
- collectors.kaist  : 한국과학기술원(KAIST) 입찰/구매 공고 게시판
                     (상세가 나라장터 링크로 바로 연결돼 g2bBidNo를 함께 저장)

(과거 나라장터(G2B) 오픈API 수집기가 있었으나, 전체 공고 대비 실제
장비 구매 공고 비율이 낮고 502 오류·복잡한 필터링 문제로 제거했다.
cebpubservice(중국 입찰투찰 공공서비스 플랫폼)/CXMT SRM(공급사·소싱
플랫폼)/중국구매입찰망(chinabidding.com.cn)은 WAF 차단 또는 로그인
필요로 접근 자체가 불가능해 보류 중이다 — collectors/common.py의
BLOCKED_SOURCES에 "추후 연동 후보"로 남겨두었다(완전 삭제하지 않음).)

KOTRA/EBNEW는 다른 수집원과 달리 "마감된 프로젝트"도 삭제하지 않는다
(신규 투자/후속 프로젝트/낙찰 동향 추적 등 영업 정보 가치가 있기 때문).
그래서 is_still_open()에서 이 두 출처는 날짜 필터링 대상에서 제외한다.

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
import sys
from datetime import date, datetime

# Windows 콘솔 등 cp949 같은 비-UTF-8 코드페이지에서 실행되면 중국어/특수문자
# print()가 UnicodeEncodeError로 죽는 걸 막는다(GitHub Actions는 기본 UTF-8
# 이라 원래 문제 없지만, 로컬 실행 환경까지 안전하게 만든다).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from collectors import kanc, nnfc, kotra, ebnew, mofcom, kriss, jetro, dgist, itri, kaist

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "announcements.json")

COLLECTORS = [
    ("KANC", kanc),
    ("NNFC", nnfc),
    ("KOTRA", kotra),
    ("EBNEW", ebnew),
    ("MOFCOM", mofcom),
    ("KRISS", kriss),
    ("JETRO", jetro),
    ("DGIST", dgist),
    ("ITRI", itri),
    ("KAIST", kaist),
]

# 마감돼도 삭제하지 않고 계속 보여줄 출처 (영업 정보로서 가치가 있는 경우)
KEEP_EXPIRED_SOURCES = {"KOTRA", "EBNEW", "MOFCOM"}


def load_existing_data():
    """이전 실행 결과 전체(items + sourceHealth)를 읽는다. sourceHealth는
    수집원별 마지막 정상 수집 시각/연속 실패 횟수를 실행 간에 이어받기
    위해 필요하다(파일이 유일한 저장소라 여기 같이 보관한다)."""
    if not os.path.exists(DATA_PATH):
        return [], {}
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", []), data.get("sourceHealth", {}) or {}
    except (json.JSONDecodeError, OSError):
        return [], {}


def run_collector(name, module, existing_items, log):
    """수집기를 실행한다. 실패하면 해당 소스의 기존 데이터를 그대로 반환해
    다른 수집원이나 이미 저장된 데이터에 영향을 주지 않는다."""
    fallback = [item for item in existing_items if item.get("sourceCode") == name]
    try:
        items = module.collect()
    except Exception as exc:  # noqa: BLE001
        print(f"[{name}] 수집 중 오류로 이번 실행분은 건너뜁니다(기존 데이터 유지): {exc}")
        log[name] = {"status": "오류", "detail": str(exc)[:200], "count": len(fallback)}
        return fallback

    if not items:
        print(f"[{name}] 이번 실행에서 수집된 항목이 없어 기존 데이터를 유지합니다.")
        log[name] = {"status": "결과 없음(기존 유지)", "detail": None, "count": len(fallback)}
        return fallback

    log[name] = {"status": "정상", "detail": None, "count": len(items)}
    return items


def build_source_health(log, previous_health, now_iso):
    """수집원별 상태를 계산한다 — 수집이 실패해도 워크플로는 성공으로 끝나기
    때문에, 어느 수집원이 언제부터 고장났는지 여기에 남겨야 알 수 있다.

    - ok               : 이번 실행에서 새로 수집됐는지
    - lastSuccessAt    : 마지막으로 정상 수집된 시각(실패해도 이전 값 유지)
    - consecutiveFailures : 연속 실패 횟수(성공하면 0으로 초기화)
    - lastStatus/lastError : 이번 실행 결과와 오류 요약
    - failureAlertSent : 이 장애를 Telegram으로 이미 알렸는지(중복 발송 방지)

    failureAlertSent는 이 함수가 만들지 않고 **이전 실행 값을 그대로 이어받는다**.
    예전에는 매 실행마다 상태를 새로 만들면서 이 플래그를 빠뜨렸고, 그래서
    notify_source_health가 매번 "아직 안 알렸다"고 판단해 연속 실패 4회·5회에도
    장애 알림을 다시 보냈다(KOTRA에서 실제로 발생). 플래그를 지우는 것은
    notify_source_health가 복구 알림을 보낸 뒤에만 한다.
    """
    health = {}
    for name, info in log.items():
        prev = previous_health.get(name, {})
        succeeded = info["status"] == "정상"
        prev_failures = prev.get("consecutiveFailures", 0) or 0
        health[name] = {
            "ok": succeeded,
            "lastStatus": info["status"],
            "lastError": info["detail"],
            "collectedThisRun": info["count"] if succeeded else 0,
            "lastRunAt": now_iso,
            "lastSuccessAt": now_iso if succeeded else prev.get("lastSuccessAt"),
            "consecutiveFailures": 0 if succeeded else prev_failures + 1,
            "failureAlertSent": bool(prev.get("failureAlertSent")),
        }
    return health


def print_health_summary(health, by_source):
    """GitHub Actions 로그에 수집원별 상태를 출력한다. 실패한 수집원은
    ::warning:: 로 출력해 Actions 실행 화면 상단 주석으로 뜨게 한다
    (워크플로 자체는 계속 성공으로 끝내되, 장애는 눈에 보이게 한다)."""
    print("--- 수집원 Health Check ---")
    for name, h in health.items():
        reflected = by_source.get(name, 0)
        if h["ok"]:
            print(f"  [{name}] 정상 — 이번 수집 {h['collectedThisRun']}건 / 최종 반영 {reflected}건")
            continue
        last_success = h.get("lastSuccessAt") or "기록 없음"
        detail = f" — {h['lastError']}" if h.get("lastError") else ""
        print(
            f"::warning title=수집원 장애 ({name})::[{name}] {h['lastStatus']}{detail} "
            f"| 연속 실패 {h['consecutiveFailures']}회 | 마지막 정상 수집 {last_success} "
            f"| 현재 화면에는 이전 수집분 {reflected}건이 그대로 남아 있음"
        )


def sort_key(item):
    # dueDate가 없는 공고("마감일 확인 필요")는 맨 뒤로 보낸다.
    due = item.get("dueDate")
    if not due:
        return (1, "")
    return (0, due)


def stamp_first_seen(all_items, existing_items):
    """각 공고에 firstSeenAt(우리 시스템이 실제로 처음 발견한 시각, ISO 8601)을
    부여한다. 공고 자체의 등록일/마감일과는 무관하다 — 이전 실행에서 같은
    id로 이미 저장된 적이 있으면 그때의 firstSeenAt을 그대로 이어받아서
    재수집돼도 다시 "신규"가 되지 않게 하고, 이번에 처음 보는 id만 지금
    시각을 새로 기록한다(프론트엔드는 이 필드를 기준으로 48시간 이내면
    NEW 배지를 표시한다)."""
    previous_first_seen = {
        item.get("id"): item.get("firstSeenAt")
        for item in existing_items
        if item.get("id") and item.get("firstSeenAt")
    }
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    for item in all_items:
        item["firstSeenAt"] = previous_first_seen.get(item.get("id")) or now_iso


def is_still_open(item):
    if item.get("sourceCode") in KEEP_EXPIRED_SOURCES:
        return True  # 마감돼도 영업 정보 가치가 있어 유지 (status 필드로 구분 표시)
    due = item.get("dueDate")
    if not due:
        return True  # 마감일을 알 수 없는 공고는 임의로 제외하지 않는다.
    try:
        return datetime.strptime(due, "%Y-%m-%d").date() >= date.today()
    except ValueError:
        return True


def main():
    existing_items, previous_health = load_existing_data()
    run_started = datetime.now()

    log = {}
    all_items = []
    for name, module in COLLECTORS:
        all_items.extend(run_collector(name, module, existing_items, log))

    all_items = [item for item in all_items if is_still_open(item)]
    stamp_first_seen(all_items, existing_items)
    all_items.sort(key=sort_key)

    now = datetime.now().astimezone()
    source_health = build_source_health(log, previous_health, now.isoformat(timespec="seconds"))
    output = {
        "updatedAt": now.isoformat(timespec="seconds"),
        "sourceHealth": source_health,
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

    # 실행 로그 요약 (마지막 검색 시간 / 사이트별 성공-실패 / 최종 반영 건수)
    elapsed = (datetime.now() - run_started).total_seconds()
    print(f"--- 실행 로그 ({now.strftime('%Y-%m-%d %H:%M:%S')}, 소요 {elapsed:.0f}초) ---")
    for name, info in log.items():
        detail = f" ({info['detail']})" if info["detail"] else ""
        print(f"  [{name}] {info['status']}{detail} — 최종 반영 {by_source.get(name, 0)}건")
    print("  다음 자동 실행: 매일 07:00(KST), .github/workflows/fetch-announcements.yml 참고")

    print_health_summary(source_health, by_source)


if __name__ == "__main__":
    main()
