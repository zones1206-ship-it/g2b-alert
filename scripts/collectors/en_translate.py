"""
영문 공고 제목/기관명을 한국어 화면에 표시하기 위한 변환기.

zh_translate.py와 같은 원칙이다 — 이 환경에는 번역 API가 연결돼 있지
않으므로 **문장을 통째로 지어내지 않는다.** 대신 반도체/디스플레이/TGV
공정 용어와 기관명처럼 뜻이 확정된 표현만 용어집으로 치환하고, 남은
부분은 영문 그대로 둔다(영문은 한자와 달리 한국어 화면에서도 그대로
읽을 수 있으므로 로마자 표기 같은 추가 변환이 필요 없다).

translate()의 두 번째 반환값 ok는 "제목의 의미를 이루는 부분이 충분히
한국어로 바뀌었는가"를 뜻한다. False면 호출한 수집기가
translationIncomplete=True로 표시하고, 화면에는 기존 "번역 미완료" 배지가
붙는다(원문 제목과 원문 링크는 상세에서 항상 확인할 수 있다).

원문(영문 그대로)은 항상 originalTitle/originalOrg에 보존한다.
"""

import re

# --- 공정/장비 용어 (사용자가 지정한 수집 대상 키워드 중심) ---
# 길이가 긴 표현이 먼저 치환되도록 아래에서 정렬해 사용한다.
PROCESS_TERMS = {
    # 반도체 일반
    "semiconductor manufacturing": "반도체 제조",
    "semiconductor packaging": "반도체 패키징",
    "advanced packaging": "첨단 패키징",
    "semiconductor": "반도체",
    "wafer bonding": "웨이퍼 본딩",
    "wafer": "웨이퍼",
    "cleanroom": "클린룸",
    "clean room": "클린룸",
    "fab": "팹",
    # 디스플레이
    "display panel": "디스플레이 패널",
    "display": "디스플레이",
    "microled": "마이크로 LED",
    "micro led": "마이크로 LED",
    "oled": "OLED",
    "lcd": "LCD",
    "panel": "패널",
    # TGV / 유리
    "through glass via": "유리관통전극(TGV)",
    "glass substrate": "유리기판",
    "glass interposer": "글라스 인터포저",
    "glass drilling": "유리 드릴링",
    "via formation": "비아 형성",
    "tgv": "TGV",
    # 증착
    "sputtering system": "스퍼터링 장비",
    "sputtering": "스퍼터링",
    "sputter": "스퍼터",
    "evaporation": "증착(Evaporation)",
    "pecvd": "PECVD",
    "cvd": "CVD",
    "pvd": "PVD",
    "ald": "ALD",
    # 식각 / 세정
    "dry etching": "건식 식각",
    "wet etching": "습식 식각",
    "dry etch": "건식 식각",
    "wet etch": "습식 식각",
    "etching system": "식각 장비",
    "etching": "식각",
    "etcher": "식각 장비",
    "etch": "식각",
    "plasma cleaning": "플라즈마 세정",
    "wet cleaning": "습식 세정",
    "wet bench": "웨트벤치",
    "cleaning system": "세정 장비",
    "cleaning": "세정",
    "drie": "DRIE",
    "rie": "RIE",
    "icp": "ICP",
    # 도금 / 금속
    "copper plating": "구리 도금",
    "cu plating": "구리 도금",
    "electroplating": "전해 도금",
    "seed layer": "시드층",
    "ecd": "ECD",
    # CMP / 열처리
    "chemical mechanical polishing": "화학적 기계 연마(CMP)",
    "cmp": "CMP",
    "polishing": "연마",
    "annealing": "어닐링",
    "furnace": "furnace(열처리로)",
    "rtp": "RTP",
    # 본딩 / 패키징
    "hybrid bonding": "하이브리드 본딩",
    "die bonding": "다이 본딩",
    "bonder": "본더",
    "packaging": "패키징",
    # 노광 / 패터닝
    "photolithography": "포토리소그래피",
    "lithography": "리소그래피",
    "photoresist": "포토레지스트",
    "stepper": "스테퍼",
    "exposure": "노광",
    "laser": "레이저",
    # 검사 / 계측
    "film thickness": "박막 두께",
    "profilometer": "표면조도 측정기",
    "ellipsometer": "엘립소미터",
    "metrology": "계측",
    "inspection": "검사",
    "sem": "SEM",
    "tem": "TEM",
    # 조달 일반 용어
    "notice of procurement": "조달 공고",
    "invitation to tender": "입찰 공고",
    "invitation to quote": "견적 요청",
    "request for quotation": "견적 요청",
    "request for proposal": "제안 요청",
    "open tender": "일반경쟁입찰",
    "selective tendering": "지명경쟁입찰",
    "goods and services": "물품 및 용역",
    "goods & services": "물품 및 용역",
    "procurement": "조달",
    "tender": "입찰",
    "supply and installation": "공급 및 설치",
    "supply, delivery and installation": "공급·납품·설치",
    "supply and delivery": "공급 및 납품",
    "installation": "설치",
    "maintenance": "유지보수",
    "calibration": "교정",
    "upgrade": "업그레이드",
    "system": "시스템",
    "equipment": "장비",
    "apparatus": "장치",
    "instrument": "장비",
    "spare parts": "예비부품",
    "1 set": "1식",
    "one set": "1식",
    "1 unit": "1대",
    "one unit": "1대",
}

# --- 기관명: 한국어 이름 + 공식 약어 병기 ---
# 화면에서 약어가 앞에 오면 어느 기관인지 바로 읽히지 않는다.
# 한국어 이름을 앞세우고 공식 약어만 괄호로 남긴다(지시문 No.015 4번).
ORG_TERMS = {
    "National Institute of Advanced Industrial Science and Technology": "일본 산업기술종합연구소(AIST)",
    "Japan Atomic Energy Agency": "일본 원자력연구개발기구(JAEA)",
    "National Institute for Materials Science": "일본 물질·재료연구기구(NIMS)",
    "National Institutes for Quantum Science and Technology": "일본 양자과학기술연구개발기구(QST)",
    "Japan Aerospace Exploration Agency": "일본 우주항공연구개발기구(JAXA)",
    "New Energy and Industrial Technology Development Organization": "일본 신에너지산업기술종합개발기구(NEDO)",
    "National Institute of Information and Communications Technology": "일본 정보통신연구기구(NICT)",
    "Industrial Technology Research Institute": "대만 산업기술연구원(ITRI)",
    "RIKEN": "일본 이화학연구소(RIKEN)",
    "University of Tokyo": "도쿄대학",
    "Kyoto University": "교토대학",
    "Osaka University": "오사카대학",
    "Tohoku University": "도호쿠대학",
    "Nagoya University": "나고야대학",
    "Kyushu University": "규슈대학",
    "Hokkaido University": "홋카이도대학",
    "Tokyo Institute of Technology": "도쿄공업대학",
    "Institute of Science Tokyo": "도쿄과학대학",
}

# 치환 후 남은 영문 단어 중 "번역 안 돼도 괜찮은" 것들.
# (1) 기능어/단위/숫자 — 원래 번역 대상이 아니다.
# (2) 업계에서 한국어 문서에도 영문 그대로 쓰는 기술 약어 — 이걸 미번역으로
#     세면 멀쩡한 제목이 "번역 미완료"로 잘못 표시된다.
_IGNORABLE_TOKEN = re.compile(
    r"^(?:[0-9]+(?:\.[0-9]+)?|[ivxlc]+|"
    r"and|or|of|for|the|a|an|to|in|on|at|with|by|from|per|set|sets|unit|units|"
    r"pcs|ea|kg|mm|cm|nm|um|inch|kw|kv|mhz|ghz|no|nos|etc|type|model|ver|"
    r"fy[0-9]{2,4}|20[0-9]{2}|"
    r"oled|lcd|led|tgv|cvd|pvd|ald|pecvd|cmp|sem|tem|rie|icp|drie|rtp|ecd|"
    r"euv|duv|uv|ic|pcb|mems|si|sic|gan|cu|au|ag|ti|ta|w|mo)$",
    re.I,
)

# 남은 실질 영단어가 이 개수를 넘으면 "제목만으로 내용 파악이 어렵다"고 보고
# 번역 미완료로 표시한다(원문은 상세에서 항상 확인 가능).
MAX_UNTRANSLATED_WORDS = 3


def _sorted_terms(mapping):
    return sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)


_PROCESS_SORTED = _sorted_terms(PROCESS_TERMS)
_ORG_SORTED = _sorted_terms(ORG_TERMS)


def _replace_terms(text, terms):
    """대소문자를 구분하지 않고 단어 경계 기준으로 치환한다. 이미 한국어로
    바뀐 구간을 다시 건드리지 않도록 긴 표현부터 순서대로 처리한다."""
    replaced = 0
    for src, dst in terms:
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(src) + r"(?![A-Za-z0-9])", re.I)
        text, n = pattern.subn(dst, text)
        replaced += n
    return text, replaced


def _completeness(text):
    """치환 후 남은 '실질적인 영문 단어' 개수로 번역 완성도를 본다.
    기능어/숫자/단위와 업계에서 영문 그대로 쓰는 약어는 세지 않는다."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]*", text)
    meaningful = [w for w in words if not _IGNORABLE_TOKEN.match(w)]
    if not meaningful:
        return True
    if not re.search(r"[가-힣]", text):
        return False
    return len(meaningful) <= MAX_UNTRANSLATED_WORDS


def translate_title(text):
    """영문 제목 → (한국어 우선 표기, ok). ok=False면 translationIncomplete."""
    if not text:
        return text, True
    result = html_unescape(text)
    result, _ = _replace_terms(result, _ORG_SORTED)
    result, n = _replace_terms(result, _PROCESS_SORTED)
    result = re.sub(r"\s{2,}", " ", result).strip()
    if n == 0:
        # 아는 용어가 하나도 없었다 — 뜻을 지어내지 않고 원문을 그대로 두되
        # 미완료로 표시해 상세에서 원문을 확인하게 한다.
        return result, False
    return result, _completeness(result)


def translate_org(text):
    """발주기관명 → (한국어 병기 표기, ok). 기관명은 모르면 원문 유지가 정답이라
    ok는 항상 True로 둔다(제목과 달리 의미 파악을 막지 않는다)."""
    if not text:
        return text, True
    result, _ = _replace_terms(html_unescape(text), _ORG_SORTED)
    return re.sub(r"\s{2,}", " ", result).strip(), True


def html_unescape(text):
    import html as html_lib
    return html_lib.unescape(text or "")
