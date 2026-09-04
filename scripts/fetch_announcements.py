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
from collectors import equipment_filter
from collectors.common import normalize_text

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
    # 상세 페이지 한 건이 일시적으로 실패했다고 그 공고를 잃으면 안 된다.
    # 공고가 데이터에서 빠지면 firstSeenAt까지 사라져, 다음 실행에 돌아올 때
    # "신규 공고"로 오인되어 Telegram이 다시 나간다(2026-09-04에 실제로 발생).
    # 그래서 직전 실행 결과가 필요한 수집기에는 넘겨준다. 이 속성을 선언한
    # 수집기만 받으며, 나머지 수집기의 동작은 그대로다.
    if hasattr(module, "PREVIOUS_ITEMS"):
        module.PREVIOUS_ITEMS = fallback
    try:
        items = module.collect()
    except Exception as exc:  # noqa: BLE001
        print(f"[{name}] 수집 중 오류로 이번 실행분은 건너뜁니다(기존 데이터 유지): {exc}")
        log[name] = {"status": "오류", "detail": str(exc)[:200], "count": len(fallback)}
        return fallback

    if not items:
        # 목록을 정상적으로 받아왔는데 필터를 통과한 공고가 0건인 경우가 있다
        # (장비 전용 필터를 세게 건 ITRI가 대표적). 이건 수집 실패가 아니므로
        # 낡은 데이터를 붙들지 않고, 장애로도 표시하지 않는다.
        state = getattr(module, "FETCH_STATE", None)
        if state is not None and state.fetched:
            log[name] = {"status": "정상", "detail": None, "count": 0}
            # 검색 기반이라 과거 공고를 계속 보여주는 출처(KOTRA/EBNEW/MOFCOM)는
            # 정상 0건이라고 기존 데이터를 지우지 않는다 — 검색 기간 밖으로
            # 밀려났을 뿐 공고 자체가 없어진 것이 아니기 때문이다.
            # 게시판 최신 목록을 그대로 반영하는 출처는 0건이면 정리한다.
            if name in KEEP_EXPIRED_SOURCES:
                print(f"[{name}] 목록은 정상 수집했지만 조건에 맞는 공고가 없습니다"
                      f"(0건). 과거 공고 {len(fallback)}건은 그대로 둡니다.")
                return fallback
            print(f"[{name}] 목록은 정상 수집했지만 조건에 맞는 공고가 없습니다(0건).")
            return []
        print(f"[{name}] 이번 실행에서 수집된 항목이 없어 기존 데이터를 유지합니다.")
        log[name] = {"status": "결과 없음(기존 유지)", "detail": None, "count": len(fallback)}
        return fallback

    # 목록은 정상 수집됐다. 다만 수집 범위(며칠치/몇 페이지/상위 N건) 밖으로
    # 밀린 **진행 중** 공고가 있으면 되살린다 — 자세한 이유는 아래 함수 참고.
    items = preserve_active_missing_items(name, items, fallback)
    log[name] = {"status": "정상", "detail": None, "count": len(items)}
    return items


SCHEDULED = "scheduled"
MANUAL = "manual-validation"


def run_mode():
    """이번 실행이 정기 수집인지 수동 검증인지 돌려준다.

    왜 필요한가 — No.018 검증 때 한 시간 안에 Actions를 4번 손으로 돌렸고,
    그중 3번 KAIST가 timeout 났다. 사이트는 멀쩡했고(같은 시각 로컬에서
    4.6초에 정상 수집) 검증 실행 자체가 만든 실패였는데, 연속 실패가 그대로
    쌓여 임계값 3회에 닿아 **실제 장애 알림이 사용자에게 발송됐다**.

    수동 검증은 수집도 하고 데이터도 갱신하지만, 정기 운영의 장애 판단까지
    오염시켜서는 안 된다. RUN_MODE가 없으면 정기 실행으로 본다(로컬에서
    돌릴 때 기존 동작이 그대로 유지되도록).
    """
    value = (os.environ.get("RUN_MODE") or "").strip().lower()
    return MANUAL if value == MANUAL else SCHEDULED


def build_source_health(log, previous_health, now_iso, mode=SCHEDULED):
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
        if succeeded:
            failures = 0
        elif mode == MANUAL:
            # 수동 검증에서의 실패는 세지 않는다. 실패했다는 사실 자체는
            # lastStatus/lastError에 그대로 남으므로 로그에서는 보인다.
            failures = prev_failures
        else:
            failures = prev_failures + 1
        health[name] = {
            "ok": succeeded,
            "lastStatus": info["status"],
            "lastError": info["detail"],
            "collectedThisRun": info["count"] if succeeded else 0,
            "lastRunAt": now_iso,
            "lastSuccessAt": now_iso if succeeded else prev.get("lastSuccessAt"),
            "consecutiveFailures": failures,
            "failureAlertSent": bool(prev.get("failureAlertSent")),
            "lastRunMode": mode,
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


def project_key(item):
    """출처 + 공고번호. 같은 공고인지 판단하는 가장 강한 근거다.

    signature(제목·기관·날짜)만으로는 부족하다 — 실제로 제목·기관·게시일·
    마감일이 모두 같은 **별개 공고**가 있다.

      JETRO  aid 2026090300090003 / …0004  (같은 장비 2건을 따로 공고)
      MOFCOM 4197-254CSOTGZT11/10 / …/12   (한 프로젝트의 다른 로트)

    반대로 사이트가 내부 id를 새로 매겨 재색인해도 공고번호는 그대로라,
    재색인은 같은 공고로 알아본다.

    공고번호가 없으면 None을 돌려주고, 호출부가 signature로 폴백한다."""
    project_no = item.get("projectNo") or item.get("g2bBidNo")
    if not project_no:
        return None
    return (item.get("sourceCode"), normalize_text(str(project_no)))


def announcement_signature(item):
    """같은 공고인지 판단하는 지문. 사이트가 내부 id를 새로 부여해 재색인해도
    (MOFCOM에서 실제로 발생) 같은 공고임을 알아보기 위한 것이다.
    마감일·공고유형이 바뀌면 다른 지문이 되므로, 정정·변경·재공고 같은 실제
    새 정보는 그대로 신규로 잡힌다."""
    return (
        item.get("sourceCode"),
        normalize_text(item.get("originalTitle") or item.get("title") or ""),
        normalize_text(item.get("originalOrg") or item.get("org") or ""),
        item.get("postedDate"),
        item.get("dueDate"),
        item.get("noticeType"),
    )


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
    # id가 바뀌어도 같은 공고면 최초 발견 시각을 이어받는다 — 그러지 않으면
    # 사이트 재색인만으로 NEW 배지가 다시 뜬다.
    previous_by_signature = {
        announcement_signature(item): item.get("firstSeenAt")
        for item in existing_items
        if item.get("firstSeenAt")
    }
    # 다만 signature만 보면 **별개 공고가 남의 발견 시각을 물려받는다**.
    # MOFCOM 4197-264BOECDCZ02 의 로트 /02 와 /03 은 제목·기관·게시일·
    # 마감일이 모두 같아 signature가 같은데, 실제로는 다른 공고다. 실측에서
    # 새로 올라온 /02 두 건이 /03 의 firstSeenAt(이틀 전)을 물려받아 NEW
    # 배지가 뜨지 않았다. 공고번호가 이전에 없던 것이면 별개 공고로 본다.
    previous_projects = {p for p in (project_key(item) for item in existing_items) if p}
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    for item in all_items:
        inherited = previous_first_seen.get(item.get("id"))
        if not inherited:
            key = project_key(item)
            if not (key and key not in previous_projects):
                inherited = previous_by_signature.get(announcement_signature(item))
        item["firstSeenAt"] = inherited or now_iso


# 원문에서 취소·폐기가 확인된 공고는 마감일이 남아 있어도 붙들지 않는다.
# 새 상태머신을 만들지 않고 기존 status/title 표기를 그대로 본다.
CANCELLED_MARKERS = ("취소", "폐기", "철회", "무효", "재공고로 대체")


def looks_cancelled(item):
    text = " ".join(str(item.get(f) or "")
                    for f in ("status", "title", "originalTitle", "noticeType"))
    return any(marker in text for marker in CANCELLED_MARKERS)


def has_future_deadline(item, today=None):
    """마감일이 오늘 이후인가. 마감일을 못 읽으면 False."""
    due = item.get("dueDate")
    if not due:
        return False
    try:
        return datetime.strptime(due, "%Y-%m-%d").date() >= (today or date.today())
    except ValueError:
        return False


def preserve_active_missing_items(name, collected, fallback, today=None):
    """수집 범위 밖으로 밀린 **진행 중** 공고를 되살린다.

    수집기마다 조회 범위가 다르다 — 며칠치만 보거나(LOOKBACK_DAYS), 앞
    몇 페이지만 읽거나(MAX_LIST_PAGES), 검색 상위 N건만 가져온다. 그래서
    **아직 마감 전인 공고가 새 공고에 밀려 목록 밖으로 나가면 데이터에서
    사라졌다.** 실제로 두 번 발생했다.

      - EBNEW: 게시일이 14일 조회 창을 벗어남(마감은 3주 뒤였다)
      - KAIST: 첫 페이지 10건 밖으로 밀림(마감은 나흘 뒤였다)

    공고가 사라지면 firstSeenAt까지 없어져, 나중에 다시 잡히면 "신규
    공고"로 Telegram이 다시 나간다.

    여기서는 **목록 수집이 정상이었을 때만** 동작한다(목록 자체가 실패하면
    run_collector가 이미 기존 데이터를 통째로 유지한다). 되살리는 조건은
    셋 다 만족해야 한다.

      1. 직전 실행에 있던 공고인데 이번 결과에 없다
      2. 마감일이 아직 남아 있다   ← 마감된 공고는 붙들지 않는다
      3. 취소·폐기 표기가 없다     ← 취소된 공고도 붙들지 않는다

    마감일이 지나면 자동으로 빠지므로 "영구 보존"이 되지 않는다."""
    if not collected or not fallback:
        return collected
    collected_ids = {i.get("id") for i in collected}
    collected_signatures = {announcement_signature(i) for i in collected}
    # 재색인은 내부 id만 바뀌고 공고번호와 지문은 그대로다. 그래서 둘을
    # **쌍으로** 본다 — 어느 한쪽만 같은 것은 재색인이 아니다.
    collected_pairs = {(project_key(i), announcement_signature(i))
                       for i in collected if project_key(i)}
    revived = []
    for old in fallback:
        if old.get("id") in collected_ids:
            continue
        # 같은 공고인지 판단할 때 signature만 보면 안 된다. 제목·기관·날짜가
        # 같은 **별개 공고**가 실제로 있다(한 프로젝트의 여러 로트, 같은
        # 장비를 여러 건으로 나눠 낸 공고).
        #
        # 그렇다고 공고번호가 같다는 이유만으로 버려서도 안 된다. 한 공고번호
        # 아래에 원공고와 정정·변경 공고가, 또 1차와 2차 공고가 별개 항목으로
        # 함께 올라온다(EBNEW·MOFCOM에서 실제로 확인).
        #
        # 그래서 공고번호는 **지키는 근거**로만 쓴다. 번호가 이번 수집분에
        # 없으면 확실히 별개 공고이므로 유지하고, 버리는 판단은 제목·기관·
        # 날짜까지 모두 같을 때(= 내부 id만 바뀐 재색인)에만 내린다.
        old_project = project_key(old)
        old_signature = announcement_signature(old)
        if old_project:
            # 공고번호가 있으면 지문 단독으로 판단하지 않는다. 실제로 로트
            # /02(마감 09-16)와 로트 /03(마감 09-16)은 제목·기관·게시일·
            # 마감일·공고종류가 모두 같아 지문이 일치한다 — 지문만 보면
            # 목록에서 밀린 /02 를 /03 이 있다는 이유로 버리게 된다.
            if (old_project, old_signature) not in collected_pairs:
                pass  # 공고번호와 지문이 함께 일치하지 않는다 — 별개 공고다
            else:
                print(f"[{name}] 재색인으로 보여 유지하지 않습니다: "
                      f"{old.get('id')} ({old.get('projectNo')})")
                continue
        elif old_signature in collected_signatures:
            # 공고번호가 없는 출처에서만 지문을 단독으로 쓴다.
            print(f"[{name}] 같은 공고로 보여 유지하지 않습니다: {old.get('id')}")
            continue
        if not has_future_deadline(old, today):
            continue
        if looks_cancelled(old):
            print(f"[{name}] 취소·폐기 표기가 있어 유지하지 않습니다: {old.get('id')}")
            continue
        revived.append(old)
        print(f"[{name}] 진행 중 공고 유지: {old.get('id')} "
              f"목록 범위 밖 / 마감 {old.get('dueDate')}")
    if revived:
        print(f"[{name}] 수집 범위 밖 진행 중 공고 {len(revived)}건을 유지했습니다.")
    return collected + revived


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
    mode = run_mode()
    print(f"RUN_MODE={mode}")
    if mode == MANUAL:
        print("수동 검증 실행입니다 — 수집은 정상 수행하되 연속 실패를 세지 "
              "않고 장애/복구 알림도 보내지 않습니다.")
    existing_items, previous_health = load_existing_data()
    run_started = datetime.now()

    log = {}
    all_items = []
    for name, module in COLLECTORS:
        all_items.extend(run_collector(name, module, existing_items, log))

    all_items = [item for item in all_items if is_still_open(item)]
    # 출처별 1차 필터를 통과한 뒤, 공통 기준으로 "실제 장비 공고인가"를 한 번 더
    # 본다(equipmentStatus: 장비 / 검토 필요 / 제외). 데이터는 지우지 않고
    # 상태만 남긴다 — 지우면 id가 사라져 나중에 다시 신규로 잡히기 때문이다.
    for item in all_items:
        equipment_filter.annotate(item)
    stamp_first_seen(all_items, existing_items)
    all_items.sort(key=sort_key)

    now = datetime.now().astimezone()
    source_health = build_source_health(
        log, previous_health, now.isoformat(timespec="seconds"), mode)
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
