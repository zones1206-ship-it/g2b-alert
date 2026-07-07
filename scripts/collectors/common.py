"""
여러 공고 수집원(collector)이 공유하는 상수와 헬퍼.

새 수집원을 추가하려면 이 모듈의 SOURCES에 등록하고,
collectors/<이름>.py 에 collect() -> list[dict] 함수를 구현한 뒤
scripts/fetch_announcements.py의 COLLECTORS 목록에 추가하면 된다.
각 아이템 dict는 아래 스키마를 따른다:

{
    "id": str,                # 소스 내에서 고유한 원본 ID (orchestrator가 sourceCode를 붙여 전역 고유화함)
    "title": str,
    "org": str,
    "dueDate": "YYYY-MM-DD" | None,   # 확인 불가능하면 None (프론트가 "마감일 확인 필요"로 표시)
    "keywords": [str, ...],           # 매칭된 최상위 카테고리 (반도체 장비 / 디스플레이 장비 / 도금 장비)
    "budget": str | None,
    "eligibility": str | None,
    "description": str | None,
    "url": str,
    "source": str,             # 사람이 읽는 출처명, 예: "한국나노기술원"
    "sourceCode": str,         # 짧은 코드, 예: "KANC"
    "noticeType": str | None,  # 예: "사전규격" / "정식입찰" (수집원에 따라 없을 수 있음)
}
"""

# 사용자에게 노출되는 최상위 관심 분야 (홈 화면 토글 카드 / 결과 화면 그룹)
CATEGORIES = ["반도체 장비", "디스플레이 장비", "도금 장비"]

# 화면에 "수집 출처" 배지로 표시할 소스 목록 (orchestrator/collector가 사용하는 sourceCode와 일치해야 함)
SOURCES = [
    {"code": "G2B", "name": "나라장터"},
    {"code": "KANC", "name": "한국나노기술원"},
]


def normalize_text(text: str) -> str:
    return text.replace(" ", "").lower()
