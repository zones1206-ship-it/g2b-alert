"""
전 수집원 공통 "실제 장비 공고인가" 최종 판정기.

왜 필요한가 (2026-09-03 운영 데이터 점검에서 확인):
  출처별 필터가 제각각이라, "반도체/웨이퍼/칩/패키징" 같은 **산업 단어 하나만**
  있어도 장비 공고로 들어왔다. 실제로 ITRI에서 실리콘웨이퍼(재료), 연마비즈
  (소모품), 전력증폭기 패키징프레임(부품), 반도체 산업연감(책)까지 "반도체
  장비"로 잡혔다.

판정 규칙 — 두 조건을 **모두** 만족해야 장비다:
  조건 A 산업 관련성 : 반도체 / 디스플레이(OLED·AMOLED·TFT-LCD·MicroLED) /
                       TGV·유리기판 / 첨단 패키징
  조건 B 장비 성격   : 실제 구매 대상이 장비·설비·시스템·기계(Equipment,
                       System, Machine, Analyzer, Prober, Furnace, Etcher …)

  산업 신호만 있고 장비 신호가 없으면 장비가 아니다.

결과는 셋 중 하나다:
  "장비"      : 메인 공고 + Telegram 대상
  "검토 필요" : 장비인지 확정할 수 없음 — 메인 "지금 확인할 공고"와 Telegram에서
                제외하되 데이터는 남겨 사용자가 직접 볼 수 있게 한다
  "제외"      : 재료·소모품·부품·용역·공사·자료 등 명백한 비장비

이 모듈은 수집기를 대체하지 않는다. 각 수집기의 기존 1차 필터를 그대로 두고,
fetch_announcements가 수집 결과 전체에 이 최종 검증을 한 번 더 적용한다.
"""

import re

# ---------------------------------------------------------------------------
# 조건 A — 산업 관련성 (한국어 / 영어 / 간체 / 번체)
# ---------------------------------------------------------------------------
INDUSTRY_TERMS = [
    # 반도체
    "반도체", "웨이퍼", "semiconductor", "wafer", "半導體", "半导体", "晶圓", "晶圆",
    "집적회로", "integrated circuit", "集成电路", "積體電路", "cmos", "mems",
    "파운드리", "foundry", "클린룸", "cleanroom", "clean room", "팹", " fab ",
    # 디스플레이
    "디스플레이", "display", "顯示", "显示", "패널", "panel", "面板",
    "oled", "amoled", "tft-lcd", "lcd", "microled", "micro led", "액정", "液晶",
    # TGV·유리기판
    "tgv", "through glass via", "유리기판", "글라스", "glass substrate",
    "玻璃基板", "玻璃通孔", "유리 기반", "玻璃基",
    # 첨단 패키징
    "패키징", "packaging", "封裝", "封装", "인터포저", "interposer",
    "advanced packaging", "패널레벨", "웨이퍼레벨",
]

# 반도체·디스플레이 공정 고유 용어. 산업 단어(반도체/디스플레이)가 제목에
# 없어도 이 공정 장비를 산다면 우리 대상이다("湿法刻蚀机设备采购" 처럼
# 회사명·산업명 없이 공정 장비만 적힌 공고가 실제로 있다).
PROCESS_INDUSTRY_TERMS = [
    "식각", "etch", "etching", "刻蚀", "蝕刻",
    "스퍼터", "sputter", "sputtering", "濺鍍", "溅射",
    "증착", "deposition", "沉積", "沉积", "鍍膜", "镀膜",
    "pvd", "cvd", "pecvd", "mocvd", "ald", "cmp",
    "노광", "리소그래피", "lithography", "曝光", "微影",
    "포토레지스트", "photoresist", "光阻",
    "본딩", "bonding", "鍵合", "键合",
    "자동광학검사", "aoi", "自动光学检测", "自動光學檢測",
    "프로버", "prober", "probe station",
    "클린룸", "cleanroom", "웨이퍼 이면", "晶背",
    "성장로", "확산로", "열처리로", "furnace", "annealing", "어닐링", "rtp",
    "산질화막", "질화막", "산화막", "박막", "thin film", "薄膜",
    "세정 장비", "웨트벤치", "wet bench", "스크러버", "scrubber",
]

# ---------------------------------------------------------------------------
# 조건 B — 장비 성격
# ---------------------------------------------------------------------------
# (가) 확실한 장비 신호. 이게 있으면 "장비를 산다"고 볼 수 있다.
EQUIPMENT_TERMS = [
    # 일반 장비어
    "장비", "설비", "시스템", "장치", "기기", "설비류",
    "equipment", "system", "systems", "machine", "apparatus", "tool",
    "設備", "设备", "機台", "机台", "系統", "系统", "裝置", "装置", "儀器", "仪器",
    # 공정 장비
    "증착기", "증착 장비", "스퍼터", "sputter", "sputtering", "濺鍍設備", "溅射设备",
    "pvd", "cvd", "pecvd", "mocvd", "ald", "epitaxy", "에피",
    "식각기", "식각 장비", "etcher", "etching system", "蝕刻機", "刻蚀机", "刻蚀设备",
    "세정기", "세정 장비", "cleaner", "cleaning system", "清洗機", "清洗设备",
    "웨트벤치", "wet bench", "스크러버", "scrubber",
    "도금 장비", "plating system", "ecd", "전해 도금 장비",
    "cmp", "연마 장비", "polisher", "polishing system", "研磨設備",
    "열처리로", "성장로", "확산로", "furnace", "퍼니스", "rtp", "annealer", "어닐링 장비",
    "노광기", "노광장비", "stepper", "scanner", "lithography system", "曝光機", "微影設備",
    "본더", "bonder", "bonding system", "鍵合機", "键合机", "접합기",
    "프로버", "prober", "probe station", "探針台",
    "검사기", "검사 장비", "inspection system", "inspector", "檢測機", "检测机", "檢測設備",
    "자동광학검사", "aoi", "계측기", "계측 장비", "metrology system", "量測設備",
    "분석기", "analyzer", "分析儀", "分析仪", "시험기", "tester", "測試機",
    "현미경", "microscope", "顯微鏡", "显微镜", "엘립소미터", "ellipsometer",
    "프로파일로미터", "profilometer", "레이저 가공 장비", "laser processing system",
    "드릴링 장비", "drilling system", "코터", "coater", "디벨로퍼", "developer",
    "진공 장비", "真空設備", "챔버", "chamber", "生產線", "생산라인", "生产线",
    "產線", "产线", "시험라인", "试验线", "試驗線", "파일럿 라인", "pilot line",
    # 검출·센서·레이저는 단품이면 부품이지만, 아래처럼 "완성된 시스템"으로
    # 적힌 경우에는 독립 장비로 본다(지시문 No.008).
    "detector system", "검출 시스템", "검출기 시스템",
    "measurement system", "계측 시스템", "측정 시스템",
    "laser measurement", "레이저 계측", "laser system for", "분석 시스템",
    "test system", "시험 시스템", "시험기", "tester", "검사 시스템",
]

# (나) 애매한 신호 — 장비일 수도 부품일 수도 있다. 이것만 있으면 "검토 필요".
# 검출기·센서·레이저는 여기서 뺐다(지시문 No.008에서 원문 9건을 직접 확인한 결과):
#   - "X-ray sensors", "Germanium Semiconductor Detector"처럼 단품을 사는
#     공고가 대부분이라 부품으로 확정했다(아래 NON_EQUIPMENT_RULES "부품").
#   - 대신 "Detector System", "Inspection System", "Laser Measurement System"
#     처럼 그 자체가 완성 장비인 표현은 EQUIPMENT_TERMS에 넣어 장비로 본다.
AMBIGUOUS_EQUIPMENT_TERMS = [
    "모듈", "module", "模組", "模组", "척", "chuck", "承載盤",
    "광원", "light source",
]

# 구체적인 장비 이름. 이런 표현이 있으면 재료·부품 단어가 함께 있어도
# ("반도체 검출기의 개발을 위한 반자동 프로버") 장비 구매로 본다.
_GENERIC_EQUIPMENT = {"장비", "설비", "시스템", "장치", "기기", "설비류",
                      "equipment", "system", "systems", "machine", "apparatus",
                      "tool", "設備", "设备", "機台", "机台", "系統", "系统",
                      "裝置", "装置", "儀器", "仪器", "챔버", "chamber"}
SPECIFIC_EQUIPMENT_TERMS = [t for t in EQUIPMENT_TERMS if t not in _GENERIC_EQUIPMENT]

# ---------------------------------------------------------------------------
# 비장비 신호 — 장비 신호가 없을 때 "제외" 사유를 정한다.
# (장비 신호가 있으면 수식어로 보고 제외하지 않는다. 예: "Single-Wafer Spin
#  Etching System"의 wafer는 재료가 아니라 장비 이름의 일부다.)
# ---------------------------------------------------------------------------
NON_EQUIPMENT_RULES = [
    ("용역·서비스", ["용역", "컨설팅", "consulting", "자문", "위탁", "委託", "委托",
                     "대행", "교육", "training", "광고", "advertising",
                     "시험 분석", "분석 의뢰", "實作", "구현", "제작 재료",
                     "製作材料", "설계툴", "구독", "subscription", "라이선스",
                     "license", "검증 및", "驗證與", "패터닝 작도", "圖案化繪製",
                     "後端實作", "시제작", "試製作", "試作"]),
    ("공사·시설", ["건축공사", "전기공사", "배관공사", "설치공사", "토목", "시공",
                   "연결 공사", "제작 설치", "덕트", "duct",
                   "리모델링", "보수", "수선", "更換", "교체 및 설치",
                   "유틸리티 연결", "공조", "air handling", "ahu", "냉동기",
                   "冰水主機", "항온항습"]),
    ("자료·간행물", ["연감", "年鑑", "年鉴", "보고서", "서적", "도서",
                     "간행물", "yearbook", "백서", "출판", "出版"]),
    ("사업·행사", ["상담회", "설명회", "박람회", "전시회", "지원 사업", "지원사업",
                   "진입지원", "공급망 진입", "모집"]),
    # 반도체·디스플레이 제조와 무관한 완성 시스템. 실제로 들어온 사례:
    # 항공 관제 훈련 시스템(국토교통성), 경마장 LED 전광판(일본중앙경마회).
    ("산업 무관 시스템", ["approach control", "air traffic", "관제", "항공",
                          "training system", "훈련 시스템", "racing", "경마",
                          "racing association"]),
    ("완제품·전시장비", ["대형 스크린", "large screen", "digital signage",
                         "사이니지", "전광판", "정보 디스플레이 유닛",
                         "information display unit", "advertising display"]),
    ("일반 IT", ["컴퓨터", "노트북", "서버", "server", "gpu", "gpgpu",
                 "네트워크 장비", "소프트웨어", "software", "스토리지"]),
    ("소모품", ["소모품", "consumable", "연마재", "연마비즈", "研磨珠", "비즈",
                "석영관", "quartz tube"]),
    ("부품", ["부품", "零件", "元件", "구성품", "component", "프레임", "框架",
              "베이스플레이트", "底板", "브래킷", "bracket", "부속", "parts",
              "소자 구매", "센서(칩)", "칩 구매", "칩 모듈", "感測晶片",
              "測試晶片", "晶片模組", "패널 손상", "面板損壞",
              # 검출기·센서 단품(지시문 No.008에서 JETRO/KANC 원문 확인).
              # "…System"류는 위 EQUIPMENT_TERMS에서 먼저 장비로 잡힌다.
              "검출기", "detector", "detectors", "센서", "sensor", "sensors",
              "感測", "传感", "pcb", "인쇄회로기판", "정전척", "electrostatic chuck",
              "esc", "광원 구매", "solid state laser", "레이저 다이오드",
              "laser diode", "레이저 광원"]),
    ("재료", ["재료", "원재료", "소재", "材料", "素材", "웨이퍼片",
              "晶圓片", "晶圆片", "soi wafer", "기판재", "잉곳", "ingot",
              "타깃재", "타겟", "target material", "화학약품", "chemicals",
              "슬러리", "slurry", "포토레지스트", "光阻", "현상액", "박리액",
              "에천트", "etchant", "기반 웨이퍼", "based wafer",
              "웨이퍼 제작", "wafer fabrication", "마스크 및 웨이퍼"]),
]

# 장비 단어가 함께 있어도 공고 성격 자체가 장비 구매가 아님이 분명한 신호.
# (예: "委託濺鍍背面金屬化製程" — 스퍼터링이라는 장비/공정 단어가 있지만
#  실제로는 위탁 가공 용역이다.)
STRONG_NON_EQUIPMENT_TERMS = [
    "위탁", "委託", "委托", "용역", "설계툴", "구독", "subscription",
    "연감", "年鑑", "年鉴", "상담회", "진입지원", "공급망 진입",
    "advertising", "digital signage", "법률자문",
    # 공사 — 공고명 자체가 공사면 장비 구매가 아니다(NNFC "ALD 장비 외 11종
    # 유틸리티 연결 공사"는 공고문에 "공사명/공사내용/공사기간"으로 적혀 있다).
    "유틸리티 연결", "연결 공사", "설치 공사", "제작 설치", "교체 및 설치",
    # 디스플레이 완제품(제조 장비가 아니라 표시장치 자체)
    "대형 스크린", "large screen", "전광판", "정보 디스플레이 유닛",
    "information display unit",
    # 우리 산업과 무관한 완성 시스템
    "approach control", "training system", "훈련 시스템", "racing association",
]

# 공고 본문에 늘 붙는 서식 문구. 판정에 쓰면 "services"/"procurement" 같은
# 단어가 항상 걸려 오판한다(JETRO 상세 본문이 대표적).
BOILERPLATE_PHRASES = [
    "classification of the products to be procured",
    "classification of the services to be procured",
    "nature and quantity of the products to be purchased",
    "official in charge of disbursement of the procuring entity",
    "fiscal services and procurement group",
    "procurement division", "contracting entity",
    "subject matter of the contract",
    "time limit of tender", "delivery period", "delivery place",
]

# ---------------------------------------------------------------------------
# 공정 분류 (지시 15번). 원문에서 실제로 확인되는 것만 붙인다.
# 순서가 중요하다 — 구체적인 것부터 본다.
# ---------------------------------------------------------------------------
PROCESS_RULES = [
    ("습식 식각", ["습식 식각", "wet etch", "湿法刻蚀", "濕蝕刻", "spin etch"]),
    ("건식 식각", ["건식 식각", "dry etch", "干法刻蚀", "乾蝕刻"]),
    ("DRIE", ["drie", "deep reactive ion"]),
    ("RIE", ["rie", "반응성 이온"]),
    ("식각", ["식각", "etch", "etching", "刻蚀", "蝕刻"]),
    ("ALD", ["ald", "원자층증착", "原子层沉积"]),
    ("CVD", ["cvd", "pecvd", "mocvd", "화학기상증착", "chemical vapor deposition"]),
    ("PVD", ["pvd", "물리기상증착"]),
    ("스퍼터링", ["스퍼터", "sputter", "濺鍍", "溅射"]),
    ("증착", ["증착", "deposition", "沉積", "沉积", "鍍膜", "镀膜", "蒸鍍"]),
    ("CMP", ["cmp", "화학기계연마", "화학기계적 평탄화"]),
    ("도금 / ECD", ["도금", "plating", "ecd", "電鍍", "电镀", "전해", "electroplat"]),
    ("세정", ["세정", "cleaning", "清洗", "clean"]),
    ("열처리 / Annealing", ["열처리", "어닐링", "anneal", "退火", "furnace", "퍼니스",
                            "성장로", "확산로", "rtp", "산질화막 성장"]),
    ("노광 / Lithography", ["노광", "리소그래피", "lithography", "曝光", "微影",
                            "stepper", "e-beam lithography", "전자빔 리소그래피"]),
    ("본딩 / Bonding", ["본딩", "bonding", "본더", "bonder", "鍵合", "键合", "접합"]),
    ("패키징", ["패키징", "packaging", "封裝", "封装"]),
    ("TGV 가공", ["tgv", "through glass via", "玻璃通孔", "유리 관통"]),
    ("레이저 / Via 가공", ["레이저 가공", "레이저 드릴", "laser drill", "laser processing",
                           "激光加工", "雷射加工", "비아 가공"]),
    ("검사", ["검사", "inspection", "檢測", "检测", "aoi", "자동광학검사", "점등 검사"]),
    ("계측", ["계측", "metrology", "量測", "측정", "현미경", "microscope",
              "분석기", "analyzer", "프로버", "prober"]),
]

# 산업 표기(지시 14번). item["keywords"]가 있으면 그걸 우선한다.
INDUSTRY_LABELS = [
    ("디스플레이", ["디스플레이", "display", "顯示", "显示", "oled", "amoled",
                    "tft-lcd", "lcd", "패널", "面板", "액정"]),
    ("TGV / 유리기판", ["tgv", "유리기판", "glass substrate", "玻璃基板", "玻璃通孔",
                        "유리 기반", "玻璃基"]),
    ("반도체", ["반도체", "semiconductor", "半導體", "半导体", "웨이퍼", "wafer",
                "집적회로", "cmos", "패키징", "packaging", "封裝", "封装"]),
]

QUANTITY_PATTERN = re.compile(
    r"(\d+)\s*(식|대|개|세트|台|套|条|sets?|units?|ea)\b", re.I)
_QUANTITY_KO = {"set": "식", "sets": "식", "unit": "대", "units": "대",
                "ea": "개", "台": "대", "套": "식", "条": "개"}


def _title_text_of(item):
    """장비 성격 판정용 텍스트. 무엇을 사는지는 제목·품목에 적힌다.
    상세 본문은 담당자·분류코드 같은 서식 문구가 길어 오탐을 만든다
    (실측: X-ray 센서 공고가 본문의 다른 문장 때문에 장비로 통과)."""
    parts = [item.get("title"), item.get("originalTitle"),
             item.get("originalSummary"), item.get("translatedSummary")]
    return " " + " ".join(p for p in parts if p).lower() + " "


def _text_of(item):
    """판정에 쓰는 텍스트. 번역 제목만 보면 원문의 신호를 놓친다."""
    parts = [item.get("title"), item.get("originalTitle"), item.get("description"),
             item.get("originalSummary"), item.get("translatedSummary")]
    text = " " + " ".join(p for p in parts if p).lower() + " "
    for phrase in BOILERPLATE_PHRASES:
        text = text.replace(phrase, " ")
    return text


def _has(text, term):
    """한글·한자는 그대로, 영문은 단어 경계로 확인한다('sem'이 'assembly'에
    우연히 걸리는 식의 오탐을 막는다)."""
    term = term.lower()
    if re.search(r"[가-힣一-鿿]", term):
        return term in text
    return re.search(r"(?<![a-z0-9])" + re.escape(term.strip()) + r"(?![a-z0-9])", text) is not None


def _first_match(text, terms):
    return next((t for t in terms if _has(text, t)), None)


def industry_of(item):
    """산업 표기. 수집기가 이미 분야를 확정했으면 그걸 쓴다."""
    kws = item.get("keywords") or []
    if kws:
        return kws[0].replace(" 장비", "")
    text = _text_of(item)
    for label, terms in INDUSTRY_LABELS:
        if _first_match(text, terms):
            return label
    return None


def process_of(item):
    """공정 분류. 원문에서 확인되는 것만 돌려준다(추론하지 않는다)."""
    text = _text_of(item)
    for label, terms in PROCESS_RULES:
        if _first_match(text, terms):
            return label
    return None


# 장비명으로 보여주기에는 너무 일반적인 낱말 — 이것만 잡히면 장비명을 비운다.
_TOO_GENERIC_EQUIPMENT = {"장비", "설비", "시스템", "장치", "기기", "equipment",
                          "system", "systems", "machine", "tool", "設備", "设备",
                          "系統", "系统", "裝置", "装置", "챔버", "chamber"}


def equipment_name_of(item):
    """장비명. 제목에 실제로 적힌 장비 표현을 그대로 쓴다(지어내지 않는다).
    "장비"처럼 너무 일반적인 낱말만 잡히면 값을 만들지 않고 행을 숨긴다."""
    title = (item.get("title") or "")
    low = " " + title.lower() + " "
    # 긴 표현부터 본다 — "식각 장비"가 있는데 "장비"만 뽑으면 의미가 없다.
    for term in sorted(EQUIPMENT_TERMS, key=len, reverse=True):
        if not _has(low, term):
            continue
        if term in _TOO_GENERIC_EQUIPMENT:
            continue
        # 제목에 적힌 원래 표기 그대로 돌려준다.
        m = re.search(re.escape(term), title, re.I)
        return m.group(0) if m else term
    return None


def quantity_of(item):
    m = QUANTITY_PATTERN.search(item.get("title") or "")
    if not m:
        m = QUANTITY_PATTERN.search(item.get("originalTitle") or "")
    if not m:
        return None
    unit = m.group(2)
    unit_ko = _QUANTITY_KO.get(unit.lower(), unit)
    return f"{m.group(1)}{unit_ko}"


GENERATION_PATTERN = re.compile(r"(第\s*[0-9.]+\s*代|제\s*[0-9.]+\s*세대|g[0-9]\.[0-9])", re.I)


# 반도체 전용 국가 나노팹을 운영하는 기관. 이 기관들이 사는 공정·시험 장비는
# 제목에 "반도체"라는 단어가 없어도 우리 산업 장비다(한국나노기술원·나노종합
# 기술원 모두 반도체 파운드리/나노팹 전용 기관).
SEMICONDUCTOR_FAB_SOURCES = {"KANC", "NNFC"}


def classify(item):
    """(판정, 사유) — 판정은 "장비" / "검토 필요" / "제외"."""
    text = _text_of(item)          # 산업·비장비 판정용(상세 본문 포함)
    buy = _title_text_of(item)     # 장비 성격 판정용(제목·품목만)

    industry = _first_match(text, INDUSTRY_TERMS) or _first_match(text, PROCESS_INDUSTRY_TERMS)
    if not industry and item.get("sourceCode") in SEMICONDUCTOR_FAB_SOURCES:
        industry = f"{item.get('sourceCode')} 반도체 나노팹"
    equipment = _first_match(buy, EQUIPMENT_TERMS)
    ambiguous = _first_match(buy, AMBIGUOUS_EQUIPMENT_TERMS)
    non_equipment = next(((label, t) for label, terms in NON_EQUIPMENT_RULES
                          for t in terms if _has(text, t)), None)

    # 세대 표기(第8.6代 / 제8.5세대)는 디스플레이·반도체 팹 라인에만 쓰는
    # 표기라, 산업 신호와 함께 있으면 생산라인 프로젝트로 본다.
    if not equipment and industry and GENERATION_PATTERN.search(buy):
        equipment = "세대별 생산라인 프로젝트"

    strong_pre = _first_match(text, STRONG_NON_EQUIPMENT_TERMS)
    if strong_pre:
        return "제외", f"장비 구매가 아님이 분명함 (신호: {strong_pre})"

    if not industry:
        if non_equipment and not equipment:
            return "제외", f"{non_equipment[0]} 구매 / 장비 아님 (신호: {non_equipment[1]})"
        if equipment:
            # 장비를 사는 것은 맞지만 우리 산업인지 확인할 수 없다. 지어내지 않는다.
            return "검토 필요", f"장비({equipment})이지만 반도체/디스플레이/TGV 산업 신호를 확인하지 못함"
        return "제외", "반도체/디스플레이/TGV 산업 신호 없음"

    strong = _first_match(text, STRONG_NON_EQUIPMENT_TERMS)
    if strong:
        return "제외", f"장비 구매가 아님이 분명함 (신호: {strong})"

    if equipment:
        specific = _first_match(buy, SPECIFIC_EQUIPMENT_TERMS)
        # 재료·부품·소모품 단어는 구체적인 장비 이름이 있으면 수식어로 본다
        # ("반도체 검출기의 개발을 위한 반자동 프로버" → 프로버를 사는 것).
        if non_equipment and non_equipment[0] in ("재료", "부품", "소모품") and specific:
            return "장비", f"산업({industry}) + 장비({specific})"
        if non_equipment and non_equipment[0] != "소모품":
            return "검토 필요", f"장비 신호({equipment})와 {non_equipment[0]} 신호({non_equipment[1]})가 함께 있음"
        return "장비", f"산업({industry}) + 장비({equipment})"

    if non_equipment:
        return "제외", f"{non_equipment[0]} 구매 / 장비 아님 (신호: {non_equipment[1]})"

    if ambiguous:
        return "검토 필요", f"장비인지 부품인지 확정 불가 (신호: {ambiguous})"

    return "검토 필요", f"산업({industry}) 신호만 있고 장비 성격을 확인하지 못함"


def annotate(item):
    """판정 결과와 구조화 필드를 item에 채워 넣는다(원문 필드는 건드리지 않는다)."""
    verdict, reason = classify(item)
    item["equipmentStatus"] = verdict
    item["equipmentReason"] = reason
    # 장비가 아닌 것으로 판정된 공고에는 "장비명"을 남기지 않는다 —
    # 화면에서 빠지긴 하지만, 데이터만 봐도 오해가 없도록 비운다.
    name = equipment_name_of(item) if verdict != "제외" else None
    for field, value in (("industry", industry_of(item)),
                         ("process", process_of(item)),
                         ("equipmentName", name),
                         ("quantity", quantity_of(item))):
        if value:
            item[field] = value
        else:
            item.pop(field, None)
    return item
