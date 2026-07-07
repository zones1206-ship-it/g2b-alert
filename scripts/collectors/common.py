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
