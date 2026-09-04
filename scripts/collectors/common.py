"""
여러 공고 수집원(collector)이 공유하는 상수와 헬퍼.

새 수집원을 추가하려면 이 모듈의 SOURCES에 등록하고,
collectors/<이름>.py 에 collect() -> list[dict] 함수를 구현한 뒤
scripts/fetch_announcements.py의 COLLECTORS 목록에 추가하면 된다.
각 아이템 dict는 아래 스키마를 따른다:

{
    "id": str,                # 소스 내에서 고유한 원본 ID (orchestrator가 sourceCode를 붙여 전역 고유화함)
    "title": str,
    "org": str,                # 발주기관/수요기업
    "country": str,            # "국내" / "중국" 등 사람이 읽는 국가명
    "countryCode": str,        # "KR" / "CN" 등
    "dueDate": "YYYY-MM-DD" | None,   # 확인 불가능하면 None (프론트가 "마감일 확인 필요"로 표시)
    "postedDate": "YYYY-MM-DD" | None,
    "status": str | None,      # 예: "진행중" (원문에서 확인 가능한 경우만)
    "keywords": [str, ...],    # 매칭된 최상위 카테고리 (반도체 장비 / 디스플레이 장비 / TGV 장비)
    "budget": str | None,
    "contractMethod": str | None,   # 계약방법 (원문에서 확인된 경우만)
    "deliveryCondition": str | None,  # 인도조건/납품장소 (원문에서 확인된 경우만)
    "paymentCondition": str | None,   # 지급조건 (원문에서 확인된 경우만)
    "eligibility": str | None,
    "description": str | None,  # 핵심 요약 (원문 요약, 지어내지 않음)
    "attachments": [{"name": str, "url": str}, ...],
    "url": str,
    "source": str,             # 사람이 읽는 출처명, 예: "한국나노기술원"
    "sourceCode": str,         # 짧은 코드, 예: "KANC"
    "noticeType": str | None,  # "사전규격"/"정식입찰"(국내 입찰),
                               # "프로젝트 정보"/"공급사 모집"/"수출상담회"/
                               # "구매상담회"(KOTRA류 해외 프로젝트 정보),
                               # "낙찰·수주결과"(EBNEW류 낙찰/심사결과 공고)
}

개별 수집원(collect())은 firstSeenAt을 채우지 않는다 — scripts/fetch_announcements.py의
stamp_first_seen()이 모든 소스를 합친 뒤 한 번에 부여한다(같은 id가 이전
실행에도 있었으면 그때 값을 그대로 이어받아 재수집돼도 "신규"로 되돌아가지
않는다). 프론트엔드는 이 필드로 NEW 배지(48시간)를 판단하며, 공고 자체의
등록일/마감일과는 무관하다.

중국 등 원문이 한국어가 아닌 출처는 위 스키마에 아래 필드를 추가로 채운다
(common 스키마에는 없지만 프론트가 있으면 표시하고 없으면 생략한다):
    "translatedTitle" / "originalTitle"     : 번역/원문 제목
    "translatedSummary" / "originalSummary" : 번역/원문 요약
    "originalUrl"      : 원문 URL(= url과 동일해도 명시적으로 보관)
    "sourceCountry"     : 출처 사이트의 국가 코드(예: "CN") — 프로젝트 대상
                          국가(country/countryCode)와는 다른 개념이다.
    "sourceType"        : 예: "China Site"
    "detectedLanguage"  : 예: "zh-CN"
번역은 실제 번역 API가 연결돼 있지 않아 collectors/zh_translate.py의
용어집 치환 기반 "최선 노력" 번역이며, 원문은 항상 보존한다.

수집원별로 위 스키마에 없는 추가 필드를 넣어도 된다(예: KOTRA의
`sourceSiteUrl`, `eventPeriod`). 프론트엔드는 없는 필드를 만나면
그냥 표시를 생략하므로 다른 수집원에 영향이 없다.
"""

import email.utils
import http.client
import urllib.error

# 사용자에게 노출되는 최상위 관심 분야 (홈 화면 토글 카드 / 결과 화면 그룹)
CATEGORIES = ["반도체 장비", "디스플레이 장비", "TGV 장비"]

# TGV(Through Glass Via) 장비 카테고리 세부 검색어. "강한 신호"(유리기판/TGV 등
# 명확히 유리 공정 맥락)와 "약한 신호"(도금/plating처럼 반도체 일반 공정에도
# 흔히 쓰이는 단어)를 분리해서, 약한 신호만 있는 경우(예: 반도체용 일반 도금
# 장비)는 TGV로 분류하지 않고 다른 카테고리(기본값 반도체 장비 등)로 남긴다.
TGV_STRONG_TERMS = [
    "TGV", "Through Glass Via", "유리기판", "글라스 기판", "Glass Substrate",
    "Glass Core", "Glass Interposer", "유리 관통홀", "유리 관통전극", "관통전극",
    "Glass Via", "Glass Etching", "유리 식각", "HF Etching", "Laser Drilling",
    "Via Filling", "유리 세정", "Glass Cleaning", "Glass Handling",
]
TGV_WEAK_PLATING_TERMS = [
    "도금", "plating", "전해도금", "무전해도금", "Cu Plating", "Copper Plating",
]

# 화면에 "수집 출처" 배지로 표시할 소스 목록 (orchestrator/collector가 사용하는 sourceCode와 일치해야 함)
SOURCES = [
    {"code": "KANC", "name": "한국나노기술원"},
    {"code": "NNFC", "name": "나노종합기술원"},
    {"code": "KOTRA", "name": "대한무역투자진흥공사"},
    {"code": "EBNEW", "name": "중국 비롄왕(EBNEW)"},
    {"code": "MOFCOM", "name": "중국국제초표망(MOFCOM)"},
    {"code": "KRISS", "name": "한국표준과학연구원"},
    {"code": "JETRO", "name": "JETRO (일본)"},
    {"code": "DGIST", "name": "DGIST (한국)"},
    {"code": "ITRI", "name": "ITRI (대만)"},
    {"code": "KAIST", "name": "KAIST (한국)"},
]

# 실제로 접근을 시도했으나 현재 수집이 불가능해 미구현 상태로 남겨둔
# 중국 사이트들. 완전히 삭제하지 않고 "추후 연동 후보"로 목록만 남겨둔다.
# status: "현재 수집 불가" — 접근 자체가 막혀 있어 즉시 재시도해도 실패함.
BLOCKED_SOURCES = [
    {
        "name": "중국 입찰투찰 공공서비스 플랫폼(cebpubservice.cn)",
        "siteUrl": "http://www.cebpubservice.com/",
        "status": "현재 수집 불가",
        "reason": "WAF(방화벽)가 자동화된 요청을 차단함 — 브라우저 UA로도 접근 실패 확인",
    },
    {
        "name": "CXMT SRM(공급사·소싱 플랫폼)",
        "siteUrl": "https://srm.cxmt.com/",
        "status": "현재 수집 불가",
        "reason": "공급사 전용 로그인이 필수라 비로그인 공개 목록이 없음",
    },
    {
        "name": "중국 구매·입찰망(chinabidding.com.cn)",
        "siteUrl": "https://www.chinabidding.com.cn/",
        "status": "현재 수집 불가",
        "reason": "회원 로그인 후에만 공고 상세/목록 열람 가능함을 확인",
    },
]


def normalize_text(text: str) -> str:
    return text.replace(" ", "").lower()


# 네트워크 계층 예외 — 모든 수집기의 fetch 재시도에서 공통으로 잡는다.
#
# KOTRA 장애(2026-09-03)를 분석하며, 대부분의 수집기가
# except (urllib.error.URLError, TimeoutError) 만 잡고 있어
# RemoteDisconnected/ConnectionResetError가 발생하면 재시도되지 않고
# collect() 밖으로 그대로 튀어나가는 잠재 버그를 발견했다. 원인은
# http.client.RemoteDisconnected가 URLError의 하위 클래스가 아니라서다.
#
# 이 튜플은 그 문제를 근본적으로 막는다. urllib.error.URLError,
# TimeoutError(=socket.timeout), ConnectionResetError,
# http.client.RemoteDisconnected는 전부 OSError의 하위 클래스이므로
# OSError 하나로 다 잡힌다(실측 확인). http.client.HTTPException은
# OSError 계열이 아니라서(BadStatusLine 등) 따로 추가했다.
#
# 의도적으로 bare Exception을 쓰지 않는다 — 파싱 오류(KeyError/TypeError
# 등 코드·데이터 버그)까지 "네트워크 재시도"로 숨기면 진짜 버그를 놓친다.
NETWORK_EXCEPTIONS = (OSError, http.client.HTTPException)

# 재시도할 가치가 있는 HTTP 상태코드.
#   429      요청이 몰렸다는 신호 — 잠시 뒤 재시도(Retry-After 존중)
#   5xx 일부 서버 쪽 일시 장애 — 제한 재시도
# 403/404/그 외 4xx는 서버가 "명확한 답"을 준 것이므로 재시도하지 않는다.
# (403이 간헐적으로 정상 복구된 근거가 있는 출처가 생기면 그때 개별 판단한다.)
RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})

# Retry-After를 그대로 믿으면 워크플로가 몇 분씩 멈출 수 있어 상한을 둔다.
RETRY_AFTER_MAX_SECONDS = 30


def should_retry(exc) -> bool:
    """네트워크 예외를 재시도할지 판단한다.

    urllib.error.HTTPError는 URLError→OSError 계열이라 NETWORK_EXCEPTIONS에
    같이 잡힌다. 그대로 두면 403·404까지 재시도하게 되므로 여기서 먼저
    분리해 상태코드로 판단한다. 연결 계층 오류(timeout/RemoteDisconnected/
    ConnectionReset 등)는 전부 재시도 대상이다."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRYABLE_HTTP_STATUS
    return True


def retry_delay(exc, base_delay):
    """대기 시간을 정한다. 429/503이 Retry-After를 주면 그걸 존중한다.

    Retry-After는 초(delta-seconds) 또는 HTTP-date 두 형식이 모두 허용되므로
    둘 다 처리하고, RETRY_AFTER_MAX_SECONDS로 상한을 둔다(무한 대기 방지).
    헤더가 없거나 해석할 수 없으면 각 수집기의 기존 backoff 값을 쓴다."""
    if not isinstance(exc, urllib.error.HTTPError):
        return base_delay
    raw = None
    try:
        raw = exc.headers.get("Retry-After") if exc.headers else None
    except AttributeError:
        raw = None
    if not raw:
        return base_delay
    raw = raw.strip()
    seconds = None
    if raw.isdigit():
        seconds = int(raw)
    else:
        try:
            when = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            when = None
        if when is not None:
            import datetime
            now = datetime.datetime.now(when.tzinfo) if when.tzinfo else datetime.datetime.now()
            seconds = max(0, (when - now).total_seconds())
    if seconds is None:
        return base_delay
    return min(max(seconds, base_delay), RETRY_AFTER_MAX_SECONDS)


# 게시판이 "진짜로 비어 있다"고 페이지가 직접 말하는 문구.
# 목록 행이 0건일 때 이 문구가 있으면 정상 빈 게시판으로 본다. 문구가 없으면
# 페이지 구조가 바뀐 것일 수 있으므로 보수적으로 장애로 남긴다(정상으로
# 잘못 판정하면 낡은 데이터가 조용히 사라진다).
EMPTY_BOARD_MARKERS = (
    "게시물이 없습니다", "게시글이 없습니다", "게시물이 존재하지 않습니다",
    "검색결과가 없습니다", "검색 결과가 없습니다", "조회된 결과가 없습니다",
    "조회된 내용이 없습니다", "등록된 자료가 없습니다", "자료가 없습니다",
    "데이터가 없습니다", "결과가 없습니다", "내역이 없습니다",
    "no data", "no result", "no records",
    "沒有資料", "查無資料", "無資料", "暂无数据", "没有数据", "无数据",
)


def looks_like_empty_board(body) -> bool:
    """페이지가 스스로 "목록이 비었다"고 알려주는지 확인한다."""
    if not body:
        return False
    low = body.lower()
    return any(m.lower() in low for m in EMPTY_BOARD_MARKERS)


class FetchState:
    """수집기가 원본 목록을 어디까지 성공했는지 단계별로 기록한다.

    왜 필요한가 (2026-09-03 ITRI에서 실제로 발생):
      장비 전용 필터를 세게 걸면 사이트는 멀쩡한데 조건을 통과한 공고가
      0건이 될 수 있다. 그때 fetch_announcements가 "수집 실패"로 오인하면
      낡은 데이터를 붙들고, Health를 장애로 기록하고, 연속 3회면 잘못된
      장애 Telegram까지 나간다.

    처음에는 "목록 행이 1건 이상이면 성공"으로만 판단했는데, 그러면
    **게시판이 진짜로 0건인 날**도 장애로 잡힌다. 그래서 네 가지를 분리한다:

      network_fetched : 목록 페이지 본문을 실제로 받았는가
      parse_succeeded : 그 페이지가 우리가 아는 구조였는가
                        (행이 0건이어도 목록 컨테이너가 있으면 True)
      item_count      : 원본 목록에서 파싱한 행 수
      filtered_count  : 우리 조건을 통과한 수(수집기가 알려줄 때만)

    판정:
      network_fetched=True, parse_succeeded=True, item_count=0  → 정상 0건
      network_fetched=False 또는 parse_succeeded=False           → 장애

    사용법(수집기):
        FETCH_STATE = FetchState("KANC")            # 모듈 상단
        def collect():
            FETCH_STATE.reset()                     # 실행 시작 시
            html = fetch_html(url)
            FETCH_STATE.mark_page(html)             # 본문 수신 기록
            rows = FETCH_STATE.mark(parse_list_page(html),
                                    structure_ok=has_list_container(html))
    """

    __slots__ = ("name", "network_fetched", "parse_succeeded",
                 "item_count", "filtered_count")

    def __init__(self, name):
        self.name = name
        self.reset()

    def reset(self):
        self.network_fetched = False
        self.parse_succeeded = False
        self.item_count = 0
        self.filtered_count = None

    def mark_page(self, body):
        """목록 페이지 본문을 받았음을 기록한다(내용 판단은 하지 않는다)."""
        if body:
            self.network_fetched = True
        return body

    def mark(self, rows, structure_ok=None):
        """파싱 결과를 그대로 돌려주면서 단계별 상태를 갱신한다.

        rows가 비어 있어도 structure_ok=True(목록 컨테이너를 찾았다)면
        "진짜 빈 게시판"으로 보고 파싱 성공으로 기록한다. structure_ok를
        주지 않으면 예전과 같이 행이 있을 때만 성공으로 본다(보수적).
        """
        rows = rows or []
        if rows:
            self.network_fetched = True
            self.parse_succeeded = True
            self.item_count += len(rows)
        elif structure_ok:
            self.network_fetched = True
            self.parse_succeeded = True
        return rows

    def mark_filtered(self, count):
        """우리 조건을 통과한 건수를 기록한다(로그·판정 근거용)."""
        self.filtered_count = count

    @property
    def fetched(self):
        """정상 수집으로 볼 수 있는가(=정상 0건 포함).

        fetch_announcements가 이 값만 보고 "정상 0건 / 장애"를 가른다.
        예전 이름을 그대로 두어 호출부를 바꾸지 않았다."""
        return self.network_fetched and self.parse_succeeded

    def summary(self):
        return (f"network={self.network_fetched} parse={self.parse_succeeded} "
                f"items={self.item_count} filtered={self.filtered_count}")


# ---------------------------------------------------------------------------
# 상세 페이지 일시 실패로 기존 공고를 잃지 않기 위한 공용 도구
# ---------------------------------------------------------------------------
# 목록에는 분명히 있는 공고인데 상세 페이지만 실패한 것은 "공고가 삭제된 것"이
# 아니라 "이번에 상세를 못 읽은 것"이다. 둘을 같게 처리하면 공고가 데이터에서
# 사라지고 firstSeenAt까지 없어져, 다음 실행에 돌아올 때 "신규 공고"로
# 오인되어 Telegram이 다시 나간다(2026-09-04 JETRO에서 실제로 발생).
#
# 사용법 — 수집기에서:
#   PREVIOUS_ITEMS = []                      # 모듈 상단에 선언(orchestrator가 채운다)
#   prev = previous_index(PREVIOUS_ITEMS)    # collect() 시작부
#   ...
#   except RuntimeError as exc:
#       kept = keep_or_defer(prev, f"cid{row['cid']}", "KANC", exc)
#       if kept: items.append(kept)
#       continue


class DetailFetchFailed(RuntimeError):
    """상세 페이지 요청이 실패했다는 신호.

    "장비 공고가 아니라 걸러냈다"(정상)와 "상세를 못 읽었다"(일시 장애)를
    호출부에서 구분하기 위해 따로 둔다. 둘 다 None으로 돌려주면 일시 장애
    때문에 빠진 공고를 삭제된 공고와 똑같이 취급하게 된다."""


def previous_index(previous_items):
    """직전 실행 결과를 id로 찾을 수 있게 만든다."""
    return {i.get("id"): i for i in (previous_items or []) if i.get("id")}


def keep_or_defer(prev_index, item_id, tag, exc):
    """상세 실패 시 유지할 기존 공고를 돌려준다(없으면 None).

    반환값이 있으면 호출부가 그대로 결과에 넣으면 된다. None이면 처음 보는
    공고라 유지할 것이 없다는 뜻이며, 목록 정보만으로 상세를 지어내지 않고
    다음 실행으로 미룬다."""
    kept = prev_index.get(item_id)
    if kept:
        print(f"[{tag}] 상세 요청 실패 — 목록에는 있으므로 기존 공고 유지: "
              f"{item_id} ({exc})")
    else:
        print(f"[{tag}] 상세 요청 실패 — 기존 데이터가 없는 신규 공고라 "
              f"이번 실행에서는 보류: {item_id} ({exc})")
    return kept
