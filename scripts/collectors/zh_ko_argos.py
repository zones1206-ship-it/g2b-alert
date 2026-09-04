"""
중국어 공고 제목을 한국어로 옮기는 번역기 (EBNEW 전용, PoC의 C″ 방식).

처리 순서:
  중국어 원문
  → 회사명·지역·전문용어·약어·세대·숫자단위 보호(자리표시자 치환)
  → 자리표시자 양옆 공백 분리
  → 남은 문장만 Argos zh→en→ko (한국어 직접 모델이 없어 영어를 경유한다)
  → 보호한 표현 복원 → 한국 반도체 장비 용어 후처리
  → 자동 검증 → 통과하면 채택, 실패하면 기존 zh_translate 결과(A안)로 폴백

왜 이렇게 하나 (지시문 No.002 PoC에서 실측한 근거):
  - Argos 단독(B안)은 회사명을 11건 중 11건 모두 잃었다(京东方→"동부 광 발전",
    广州华星→"중국 스타"). 원문과 무관한 완전 환각도 1건 나왔다
    (京东方第6代… → "교토시 정부의 최신뉴스를 게재하고 있습니다"). 보호가 필수다.
  - 중국어는 단어 사이 공백이 없어서, 자리표시자를 그냥 끼워 넣으면 인접
    한자와 한 덩어리로 번역되며 뭉개진다(실측: "선양TERTERMERM유한책임공사").
    토큰 양옆에 공백을 넣자 변형·중복이 8건·2건 → 0건이 됐다.
  - 그래도 토큰이 통째로 사라지는 경우가 남는다. 그런 공고는 번역을 쓰지
    않고 기존 A안(용어집+로마자 표기)을 그대로 유지한다.

MOFCOM은 이 모듈을 쓰지 않는다. PoC에서 MOFCOM은 기존 A안이 숫자·약어·
회사명·세대 표기 전부 만점이라 바꿀 이유가 없다고 확인했다.

안전장치:
  Argos나 모델이 없으면(로컬 개발 환경, Actions 캐시 실패 등) 예외를 내지 않고
  기존 zh_translate 결과로 조용히 폴백한다 — 번역 때문에 수집 전체가 실패하면
  안 되기 때문이다.
"""

import re

from . import zh_translate
from . import translation_memory

# ---------------------------------------------------------------------------
# 1) 보호 대상 — 기존 중국어 용어집을 그대로 재사용하고, PoC에서 Argos가
#    실제로 틀린 표현만 보강한다(운영 중인 zh_translate는 수정하지 않는다).
# ---------------------------------------------------------------------------

COMPANY_TERMS = dict(zh_translate.COMPANY_TERMS)

# 실제 EBNEW 운영 데이터(공고 21건의 제목·발주기관)에 나오는 회사·기관명만
# 등록한다. 데이터에 없는 중국 기업을 미리 대량 등록하지 않는다.
# 표기 원칙:
#   1) 공식 영문명이 확인되면 "한국어 표기(공식 영문명)"
#   2) 공식 영문명을 확인하지 못하면 한국어 독음만 쓴다 — 뜻을 추측해
#      한국어 회사명을 지어내지 않는다(深南→"딥 사우스" 같은 오역 금지).
#   3) 기존에 이미 잘 처리되던 BOE(징둥팡)/TCL CSOT(화싱광전)/Tianma(톈마)는
#      표기를 그대로 둔다.
# 이 사전은 EBNEW 전용이다. zh_translate(=MOFCOM이 함께 쓰는 용어집)에는
# 넣지 않는다 — MOFCOM 번역 결과를 바꾸지 않기 위해서다.
ORG_NAME_TERMS = {
    # (1) 공식 영문명 확인됨
    # 자사 영문 표기는 syxh.crsc.cn 에서 확인했으나, 한국어 이름이 이미
    # 앞에 있으므로 화면에 영문을 중복해 두지 않는다(지시문 No.015 5번).
    "沈阳铁路信号": "선양철도신호",
    "深圳职业技术大学": "선전직업기술대학(Shenzhen Polytechnic University)",  # english.szpu.edu.cn
    "深南电路": "선난(Shennan Circuits)",                    # 선전 상장사 深南电路(002916)
    "芯联微电子": "신롄 마이크로전자(Xinlian Microelectronics)",
    "芯联": "신롄(Xinlian)",
    "华星光电": "TCL CSOT(화싱광전)",  # 제목의 TCL华星 표기와 맞춘다
    # (2) 공식 영문명 미확인 — 한국어 독음만 쓴다
    "康源": "캉위안",
    "威微": "웨이웨이",
    "芯业时代": "신예스다이",
    "创元": "촹위안",
    "继彰": "지장",
}

REGION_TERMS = dict(zh_translate._REGION_WITH_SUFFIX)
REGION_TERMS.update(zh_translate.REGION_TERMS)
# 실제 EBNEW 데이터에 나오지만 기존 지역 사전에 없던 지명.
REGION_TERMS.update({"南通": "난퉁", "南通市": "난퉁"})
# 기존 사전은 山西(산시)와 구분하려고 "산시성(陕西)"처럼 한자를 병기해 두었고,
# 그 한자가 다시 로마자로 떨어져 "산시성(ShanXi)"로 보인다. EBNEW에서는
# 중국 정부 공식 로마자 표기(Shaanxi)를 써서 구분한다.
# 陕西(섬서)와 山西(산서)는 한국어로 둘 다 "산시성"이라 구분이 필요하다.
# 로마자 대신 한국어 한자음으로 구분한다(화면에 외국어를 남기지 않는다).
REGION_TERMS.update({"陕西": "산시성(섬서)", "陕西省": "산시성(섬서)",
                     "山西": "산시성(산서)", "山西省": "산시성(산서)"})

# 기존 반도체/TGV 용어집 + 지시문 5번 목록 중 기존 용어집에 없던 항목,
# 그리고 PoC에서 Argos가 실제로 틀린 표현만 보강한다.
TECH_TERMS = dict(zh_translate.TECH_TERMS)
TECH_TERMS.update({
    # 지시문 5번 보호 목록 보강
    "溅射": "스퍼터링(Sputtering)", "溅镀": "스퍼터링(Sputtering)",
    "物理气相沉积": "물리기상증착(PVD)", "化学气相沉积": "화학기상증착(CVD)",
    "原子层沉积": "원자층증착(ALD)",
    "化学机械抛光": "화학기계연마(CMP)", "化学机械研磨": "화학기계연마(CMP)",
    "电化学沉积": "전기화학증착(ECD)",
    "深反应离子刻蚀": "심부 반응성 이온 식각(DRIE)",
    "反应离子刻蚀": "반응성 이온 식각(RIE)",
    "干法刻蚀": "건식 식각(Dry Etching)",
    "刻蚀设备": "식각 장비", "清洗": "세정", "抛光": "연마",
    "玻璃": "유리", "基板": "기판",
    # PoC에서 Argos 오역이 실측된 표현
    "点灯检查机": "점등 검사기", "点灯检查": "점등 검사",
    "自动光学检测机": "자동광학검사(AOI) 장비",
    "湿法刻蚀机": "습식 식각 장비", "刻蚀机": "식각 장비",
    "集成电路": "집적회로", "封装载板": "패키징 기판",
    "载板": "기판", "芯片": "칩", "晶背": "웨이퍼 이면",
    "炉管": "퍼니스 튜브", "光电": "광전", "显示": "디스플레이",
    "产线": "생산라인", "工艺": "공정", "测试中心": "테스트 센터",
    "研发试验线": "연구개발 시험라인", "激光加工": "레이저 가공",
    "声光扫描": "음향광학 스캐닝", "高性能": "고성능",
    "印刷": "인쇄", "新型": "신형", "柔性": "플렉시블",
    "有源矩阵": "능동형 매트릭스", "有机发光": "유기발광",
    "盲孔": "블라인드 비아", "塞孔": "홀 플러깅", "检验": "검사",
    "玻璃基": "유리 기반", "微电子": "마이크로전자", "电路": "회로",
    "职业技术": "직업기술", "大学": "대학", "研发": "연구개발",
    "试验线": "시험라인", "中心": "센터", "技术": "기술", "特色": "특화",
    "时代": "시대", "高速": "고속", "扫描": "스캐닝", "加工": "가공",
    "生产线": "생산라인", "生产基地": "생산기지", "工厂": "공장",
    # 발주기관 이름에 붙는 일반 명사(회사 고유명이 아니라 업종·법인격 표기).
    "电子材料": "전자재료", "电子": "전자",
    "传感技术": "센서 기술", "传感": "센서",
    "印刷显示技术": "인쇄 디스플레이 기술", "印刷显示": "인쇄 디스플레이",
    "工程造价咨询": "공사비 견적 자문", "咨询": "자문",
})

# 행정 상용어. 여기서 보호 대상을 늘릴수록 Argos에 들어가는 문장이 거의
# 전부 자리표시자가 되고, 그러면 같은 단어를 수십 번 반복하는 퇴행 출력이
# 나온다(용어집을 통째로 보호한 재시험에서 21건 중 8건 발생, 채택 7→2건).
# 그래서 PoC에서 실제로 오역이 확인된 표현만 최소한으로 보호하고, 나머지
# 행정 낱말(公告/项目/采购 등)은 번역기에 맡긴 뒤 후처리로 다듬는다.
ADMIN_TERMS = {
    "重新招标": "재입찰",          # → "rebidding" 오역
    "中标结果": "낙찰 결과",        # → "우승 결과" 오역
    "评标结果": "심사결과",
    "谈判采购": "협상 구매",        # → "터미널" 오역
    "第一批": "1차", "第二批": "2차", "第三批": "3차",  # → "두 번째" 등
    "一期": "1단계", "二期": "2단계", "三期": "3단계",  # → "문제"/"상" 오역
    "前段": "전공정", "后段": "후공정",
    "澄清或变更": "정정·변경",      # → "Clarification 또는 변화" 오역
    "国际招标": "국제입찰",          # → "International Soft"/"국제 부드러운" 오역
    # 회사 형태 — 남겨두면 "제한"/"주식 회사"로 옮겨져 회사명이 뭉개진다.
    "股份有限公司": "주식회사",
    "有限责任公司": "유한책임공사",
    "有限公司": "유한공사",
}

# 보호하지 않고 번역기에 맡기지만, 로마자 표기 판정(아래 _protect의 고유명사
# 처리)에서는 "아는 단어"로 취급해야 하는 기존 용어집 항목들.
_KNOWN_GENERIC = sorted(zh_translate.GENERIC_TERMS, key=len, reverse=True)

# 원문에 그대로 살아 있어야 하는 영문 약어(지시문 8번).
ACRONYMS = ["AMOLED", "TFT-LCD", "OLED", "LCD", "TFT", "PVD", "CVD", "ALD",
            "PECVD", "CMP", "ECD", "DRIE", "RIE", "TGV", "AOI", "LED",
            "HBM", "TSV", "PLP", "WLP", "3D", "2D", "XR", "IC", "CMOS"]

# 세대 표기(第6代, 第8.6代)와 연도·숫자+단위. 값이 바뀌면 안 된다.
GEN_PATTERN = re.compile(r"第\s*([0-9]+(?:\.[0-9]+)?)\s*代")
YEAR_PATTERN = re.compile(r"([0-9]{4})\s*年")
_UNIT_KO = {"台": "대", "套": "식", "条": "개", "个": "개", "片": "장",
            "吋": "인치", "英寸": "인치", "万件": "만개", "万片": "만장",
            "万台": "만대", "万平米": "만㎡"}
UNIT_PATTERN = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*(万平米|万件|万片|万台|英寸|台|套|条|个|片|吋)")

# 자리표시자: 같은 글자가 연속되지 않는 토큰만 쓴다(Argos가 글자를 덧붙인다).
# 중국어 제목은 영문보다 보호 대상이 훨씬 많아(용어집을 통째로 재사용한다)
# JETRO용(20개)보다 넉넉히 만들어 둔다.
_ALPHABET = "ABCDEFGHIJKLNOPQRSTUVWXYZ"  # M은 접두사 끝 글자라 첫 자리에서 제외
_TOKENS = [f"TERM{a}{b}" for a in _ALPHABET for b in _ALPHABET if a != b][:80]

# 후처리 결과에 남아도 되는 영문(우리가 의도적으로 만드는 표기).
_LATIN_ALLOWLIST = {"aoi", "oled", "amoled", "lcd", "tft", "pvd", "cvd", "ald",
                    "cmp", "ecd", "drie", "rie", "tgv", "led", "hbm", "tsv",
                    "plp", "wlp", "pecvd", "cmos", "ic", "xr",
                    "sputtering", "dry", "etching", "wet", "glass", "substrate",
                    "cleaning", "equipment", "inspection", "interposer",
                    "advanced", "packaging", "through", "via", "single",
                    "crystal", "growth", "furnace", "bonder", "etcher",
                    "copper", "electroplating", "electroless", "plating",
                    "laser", "drilling", "formation", "filling", "cu", "micro"}

_CJK_RE = re.compile(r"[一-鿿]")
_CJK_RUN_RE = re.compile(r"[一-鿿]+")
# 어느 용어집에도 없는 한자 덩어리 중 이 길이 범위는 고유명사로 보고
# 로마자 표기한다. 5자를 넘으면 서술어구일 가능성이 커서 번역기에 맡긴다.
_PROPER_NOUN_MIN_LEN = 2
_PROPER_NOUN_MAX_LEN = 5
# 보호하고 남은 한자가 이 개수 이하면 용어집만으로 처리한다(번역기 미호출).
_MT_MIN_HANZI = 4


# ---------------------------------------------------------------------------
# 2) Argos 로딩 — 없으면 조용히 폴백
# ---------------------------------------------------------------------------

_argos_translate = None
_argos_ready = None
_argos_reason = ""


def _load_argos():
    """Argos와 zh→en / en→ko 모델이 둘 다 실제로 쓸 수 있는지 한 번만 확인한다."""
    global _argos_translate, _argos_ready, _argos_reason
    if _argos_ready is not None:
        return _argos_ready
    try:
        import argostranslate.translate as tr
        english = tr.translate("半导体设备", "zh", "en")
        if not english or not re.search(r"[A-Za-z]", english):
            _argos_ready = False
            _argos_reason = "zh→en 모델이 설치돼 있지 않음(영어 결과 없음)"
            return _argos_ready
        korean = tr.translate("semiconductor equipment", "en", "ko")
        if not korean or not re.search(r"[가-힣]", korean):
            _argos_ready = False
            _argos_reason = "en→ko 모델이 설치돼 있지 않음(한국어 결과 없음)"
            return _argos_ready
        _argos_translate = tr
        _argos_ready = True
    except Exception as exc:  # noqa: BLE001
        _argos_ready = False
        _argos_reason = f"{type(exc).__name__}: {str(exc)[:80]}"
    return _argos_ready


def argos_status():
    """호출부에서 로그로 남길 수 있도록 상태를 알려준다."""
    return _load_argos(), _argos_reason


# ---------------------------------------------------------------------------
# 3) 보호 → 번역 → 복원
# ---------------------------------------------------------------------------

# EBNEW 제목 끝에 붙는 일련번호 "(1)". 번역기에 넣으면 통째로 사라져서
# 숫자 검증에 걸리므로 미리 떼어내고 마지막에 다시 붙인다.
_SERIAL_SUFFIX = re.compile(r"\s*[(（]\s*(\d+)\s*[)）]\s*$")


def _split_serial_suffix(text):
    m = _SERIAL_SUFFIX.search(text or "")
    if not m:
        return text, ""
    return text[:m.start()].rstrip(), f"({m.group(1)})"


# 제목 끝에 붙는 공고 유형 문구. 이 구간까지 자리표시자로 만들면 문장이
# 자리표시자 투성이가 되어 번역기가 끝부분을 통째로 잘라먹거나 같은 단어를
# 수십 번 반복한다(실측). JETRO에서 "1 set" 수량 접미사를 떼어낸 것과 같은
# 방식으로, 여기서도 통째로 떼어내 우리 표기로 붙인다 — 항상 보존된다.
_NOTICE_SUFFIXES = [
    ("国际招标澄清或变更公告", "국제입찰 정정·변경 공고"),
    ("重新招标澄清或变更公告", "재입찰 정정·변경 공고"),
    ("国际招标资格预审公告", "국제입찰 참가자격 사전심사 공고"),
    ("招标澄清或变更公告", "입찰 정정·변경 공고"),
    ("评标结果公示公告", "심사결과 공시 공고"),
    ("中标候选人公示公告", "낙찰 후보자 공시 공고"),
    ("澄清或变更公告", "정정·변경 공고"),
    ("资格预审公告", "입찰참가자격 사전심사 공고"),
    ("谈判采购公告", "협상 구매 공고"),
    ("中标结果公告", "낙찰 결과 공고"),
    ("招标结果公告", "입찰 결과 공고"),
    ("国际招标公告", "국제 입찰공고"),
    ("重新招标公告", "재입찰 공고"),
    ("设备采购公告", "장비 구매 공고"),
    ("评标结果公示", "심사결과 공시"),
    ("中标结果公示", "낙찰 결과 공시"),
    ("采购公告", "구매 공고"),
    ("变更公告", "변경 공고"),
    ("成交公告", "낙찰 공고"),
    ("招标公告", "입찰공고"),
    ("中标公告", "낙찰 공고"),
    ("公示公告", "공시 공고"),
    ("公告", "공고"),
    ("公示", "공시"),
]


def _split_notice_suffix(text):
    """('본문', '한국어 공고유형') 로 나눈다. 없으면 두 번째 값은 ''."""
    for zh, ko in _NOTICE_SUFFIXES:
        if text.endswith(zh):
            return text[:-len(zh)].rstrip(), ko
    return text, ""


def _protect(text):
    """(보호된 문장, 매핑). 토큰 양옆에 공백을 넣어 인접 한자와 분리한다."""
    mapping = {}
    result = text
    idx = 0

    def take_token():
        nonlocal idx
        if idx >= len(_TOKENS):
            return None
        token = _TOKENS[idx]
        idx += 1
        return token

    # 회사명 > 지역 > 전문용어 > 행정용어 순. 각 그룹 안에서는 긴 표현부터
    # 치환해야 짧은 표현이 그 일부를 잘못 먹지 않는다.
    # 회사·기관 고유명을 가장 먼저 치환한다. "深南电路"처럼 일반 명사(电路)를
    # 품은 회사명이 있어서, 뒤 그룹이 먼저 손대면 이름이 쪼개진다.
    for group in (ORG_NAME_TERMS, COMPANY_TERMS, REGION_TERMS, ADMIN_TERMS, TECH_TERMS):
        for term, korean in sorted(group.items(), key=lambda kv: len(kv[0]), reverse=True):
            if term not in result:
                continue
            token = take_token()
            if token is None:
                break
            mapping[token] = korean
            result = result.replace(term, f" {token} ")

    for acronym in sorted(ACRONYMS, key=len, reverse=True):
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(acronym) + r"(?![A-Za-z0-9])", re.I)
        if not pattern.search(result):
            continue
        token = take_token()
        if token is None:
            break
        mapping[token] = acronym  # 약어는 원문 그대로 되돌린다
        result = pattern.sub(f" {token} ", result)

    def gen_repl(match):
        token = take_token()
        if token is None:
            return match.group(0)
        mapping[token] = f"제{match.group(1)}세대"
        return f" {token} "

    result = GEN_PATTERN.sub(gen_repl, result)

    def year_repl(match):
        token = take_token()
        if token is None:
            return match.group(0)
        mapping[token] = f"{match.group(1)}년"
        return f" {token} "

    result = YEAR_PATTERN.sub(year_repl, result)

    def unit_repl(match):
        token = take_token()
        if token is None:
            return match.group(0)
        mapping[token] = f"{match.group(1)}{_UNIT_KO[match.group(2)]}"
        return f" {token} "

    result = UNIT_PATTERN.sub(unit_repl, result)

    # 어느 용어집에도 없는 한자 덩어리는 거의 전부 고유명사(회사 브랜드명)다.
    # 실측: 康源→"Congenital", 深南→"딥 사우스", 芯联→"CURRENTIZED"처럼
    # 번역기가 회사명을 일반 단어로 지어낸다(지시문 4번이 금지하는 결과).
    # 그래서 이 구간만은 번역기에 넘기지 않고, 기존 A안과 똑같이 로마자
    # 표기(pypinyin)로 되돌린다 — 뜻을 지어내지 않는다.
    # 보호하지 않고 넘기는 행정 낱말(项目/设备 등)까지 로마자로 바꿔버리면
    # 오히려 가독성이 나빠지므로, 그 낱말들을 먼저 걷어낸 잔여 구간만 본다.
    def proper_noun_repl(match):
        run = match.group(0)
        pieces = [run]
        for known in _KNOWN_GENERIC:
            pieces = [p for chunk in pieces for p in chunk.split(known)]
        unknown = [p for p in pieces if _PROPER_NOUN_MIN_LEN <= len(p) <= _PROPER_NOUN_MAX_LEN]
        replaced = run
        for piece in unknown:
            token = take_token()
            if token is None:
                break
            mapping[token] = zh_translate._romanize_run(piece)
            replaced = replaced.replace(piece, f" {token} ")
        return replaced

    result = _CJK_RUN_RE.sub(proper_noun_repl, result)
    return re.sub(r"\s{2,}", " ", result).strip(), mapping


def _restore(text, mapping):
    for token, value in mapping.items():
        # 글자 중복(TERMAX→TERMAAX)과 대소문자 흔들림을 허용해 복원한다.
        loose = "".join(f"{ch}+" for ch in token)
        text = re.sub(loose, value, text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()


def _token_issues(raw, mapping):
    """보호 토큰 누락/변형/중복을 센다(지시문 6번)."""
    issues = {"missing": 0, "mangled": 0, "duplicated": 0}
    for token in mapping:
        loose = "".join(f"{ch}+" for ch in token)
        exact = len(re.findall(re.escape(token), raw, re.I))
        loose_count = len(re.findall(loose, raw, re.I))
        if loose_count == 0:
            issues["missing"] += 1
        elif exact == 0:
            issues["mangled"] += 1
        elif exact > 1:
            issues["duplicated"] += 1
    return issues


# ---------------------------------------------------------------------------
# 후처리 — Argos 결과를 업계에서 쓰는 표현으로 다듬는다(지시문 10번).
# 실제 EBNEW 공고에서 관측된 표현만 대상으로 하고, 문맥 조건을 함께 건다.
# ---------------------------------------------------------------------------
_POST_RULES = [
    (r"생산\s*선(?=\s|$)", "생산라인"),
    (r"검사\s*기계", "검사기"),
    (r"검출\s*기계", "검사기"),
    (r"평가\s*결과", "심사결과"),
    (r"공개\s*발표", "공시"),
    (r"공개\s*공지", "공시"),
    (r"성공적인\s*후보(?:자)?", "낙찰 후보자"),
    (r"조달\s*프로젝트", "구매 프로젝트"),
    (r"정정\s*또는\s*변경", "정정·변경"),
    (r"(?<=반도체\s)감지기", "검출기"),
    (r"(?<=반도체\s)장치(?=\s|$)", "소자"),
    (r"기술\s*변형", "기술 개조"),
    (r"기술\s*개혁", "기술 개조"),
    (r"장비\s+장비", "장비"),          # "습식 식각 장비 장비" 중복 제거
    (r"(?<=\S)을위한", "을 위한"),
    (r"(?<=\S)를위한", "를 위한"),
    (r"조달\s*(?=프로젝트|공고|$)", "구매 "),
    # 기계번역이 문장 끝에 덧붙이는 상투구 — 원문에 대응하는 말이 없다.
    (r"\s*의\s*(?:특징|장점|세부\s*사항)\s*$", ""),
    (r"\s*에\s*대한\s*(?:자세한\s*)?정보\s*$", ""),
    (r"\s*(?:를|을)\s*통해\s*$", ""),
]

# 영어를 경유하는 구조라, en→ko 모델이 옮기지 못하고 영어 그대로 남기는
# 낱말이 있다(실측: 公告→"Bulletin", 澄清→"Clarification", 招标→"Tendering").
# 전부 이 도메인에서 뜻이 하나로 굳어 있는 행정 용어라 그대로 대응시킨다.
_ENGLISH_LEFTOVER_RULES = [
    (r"\bRe-?bidding\b", "재입찰"),
    (r"\bClarifications?\b", "정정"),
    (r"\bBulletins?\b", "공고"),
    (r"\bAnnouncements?\b", "공고"),
    (r"\bNotices?\b", "공고"),
    (r"\bTendering\b", "입찰"),
    (r"\bTenders?\b", "입찰"),
    (r"\bBiddings?\b", "입찰"),
    (r"\bProjects?\b", "프로젝트"),
    (r"\bInternational\b", "국제"),
    (r"\bEquipments?\b", "장비"),
    (r"\bProcurement\b", "구매"),
]

_POST_RULES += [
    # 용어집 치환은 앞뒤에 공백을 넣기 때문에 전각 괄호 주변이 벌어진다.
    (r"（", "("), (r"）", ")"),
    (r"\(\s+", "("), (r"\s+\)", ")"),
    (r"\)\s*-\s*(?=[^\s-])", ") - "),
    (r"장비\s*취득", "장비 구매"),
    (r"취득\s*프로젝트", "구매 프로젝트"),
    (r"취득을\s*위한", "구매"),
    (r"\s{2,}", " "),
    (r"\s+([,.)])", r"\1"),
    (r"\s{2,}", " "),
]


def _fix_english_leftovers(text):
    """번역기 출력에 남은 영어 낱말을 우리 표기로 바꾼다. 보호 표현을 복원하기
    **전에** 돌려야 한다 — 복원한 값 안의 영문 병기("세정 장비(Cleaning
    Equipment)")까지 건드리면 보호한 표기가 깨진다(실측)."""
    result = text
    for pattern, replacement in _ENGLISH_LEFTOVER_RULES:
        result = re.sub(pattern, replacement, result)
    return result


def _postprocess(text):
    result = text
    for pattern, replacement in _POST_RULES:
        result = re.sub(pattern, replacement, result)
    return result.strip()


# ---------------------------------------------------------------------------
# 4) 검증 — 하나라도 실패하면 번역 결과를 쓰지 않는다(지시문 6~9, 11번)
# ---------------------------------------------------------------------------

def _numbers(text):
    return sorted(re.findall(r"\d+(?:\.\d+)?", text or ""))


def _acronyms(text):
    return {w.upper() for w in re.findall(r"(?<![A-Za-z0-9])[A-Z]{2,}[0-9]*(?![a-z])", text or "")}


def _latin_words(text):
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]{1,}", text or "")}


def _hangul_ratio(text):
    if not text:
        return 0.0
    return len(re.findall(r"[가-힣]", text)) / max(len(text), 1)


def validate(reference, candidate, mapping, raw):
    """(통과 여부, 실패 사유). reference는 "보호 대상을 우리가 정한 한국어로
    바꾸고 나머지 한자는 그대로 둔" 기준 문장이다 — 원문과 직접 비교하면
    一期→"1단계"처럼 우리가 의도적으로 넣은 숫자가 불일치로 잡힌다."""
    if not candidate or not candidate.strip():
        return False, "번역 결과가 비어 있음"
    if not re.search(r"[가-힣]", candidate):
        return False, "번역 결과에 한국어가 없음"
    # 우리가 복원해 넣은 표기 자체에 한자가 들어 있는 경우가 있다
    # (기존 용어집의 "산시성(陕西)"처럼 동음 구분용 병기). 그건 의도한
    # 것이므로 빼고 나서 한자가 남았는지 본다.
    residue = candidate
    for value in mapping.values():
        residue = residue.replace(value, " ")
    if _CJK_RE.search(residue):
        return False, "번역 결과에 한자가 남음"
    if re.search(r"TERM[A-Z]", candidate, re.I):
        return False, "보호 토큰이 복원되지 않음"

    issues = _token_issues(raw, mapping)
    if sum(issues.values()):
        return False, ("보호 토큰 실패(누락 %d/변형 %d/중복 %d)"
                       % (issues["missing"], issues["mangled"], issues["duplicated"]))

    lost = [v for v in mapping.values() if v not in candidate]
    if lost:
        return False, f"보호 표현 복원 실패({', '.join(lost[:3])})"

    if _numbers(reference) != _numbers(candidate):
        return False, f"숫자 불일치({_numbers(reference)} → {_numbers(candidate)})"

    missing_acronyms = sorted(a for a in _acronyms(reference) if a not in _acronyms(candidate))
    if missing_acronyms:
        return False, f"약어 소실({', '.join(missing_acronyms[:3])})"

    # 원문에 없던 영문 단어가 새로 생기면 번역기가 지어낸 것이다
    # (실측: 康源→"Congenital", 芯联→"CURRENTIZED", 重新招标→"rebidding").
    invented = sorted(w for w in _latin_words(candidate)
                      if w not in _latin_words(reference) and w not in _LATIN_ALLOWLIST)
    if invented:
        return False, f"원문에 없는 영문 생성({', '.join(invented[:3])})"

    if len(candidate) < max(6, len(reference) * 0.45):
        return False, "번역이 원문 대비 과도하게 짧음"
    return True, None


# ---------------------------------------------------------------------------
# 5) 공개 함수
# ---------------------------------------------------------------------------

def translate_title(text):
    """중국어 제목 → (한국어 제목, 번역 완료 여부, 진단정보 dict).

    모든 검증을 통과했을 때만 새 번역을 쓰고, 그렇지 않으면 기존 zh_translate
    결과(A안)를 그대로 돌려준다(잘못된 한국어를 억지로 보여주지 않는다)."""
    baseline, baseline_ok = zh_translate.translate(text)
    info = {"engine": "glossary", "reason": None, "candidate": None,
            "protected": 0, "tokenIssues": None}

    if not text:
        info["reason"] = "원문 없음"
        return baseline, baseline_ok, info

    # 같은 원문에 대해 이미 안전검증을 통과한 번역이 있으면 그걸 그대로 쓴다.
    # Argos는 같은 입력에도 실행마다 다른 결과를 낸다(JETRO에서 실측: 멀쩡하던
    # 제목이 다음 실행에 완전 오역으로 바뀌었다). 새 번역이 검증된 제목을
    # 덮어쓰지 못하게 막는다. 다시 번역하려면 기억 파일에서 항목을 지우면 된다.
    remembered = translation_memory.lookup("zh_ko", text)
    if remembered:
        info["engine"] = "memory"
        info["reason"] = "이전에 검증된 번역 재사용"
        info["candidate"] = remembered
        return remembered, True, info

    # 기존 A안이 용어집만으로 완전히 처리됐다면(로마자 표기 폴백을 쓰지 않았다면)
    # 고칠 가독성 문제가 없다 — 굳이 기계번역으로 바꾸지 않는다(지시문 16번).
    if baseline_ok:
        info["reason"] = "기존 번역이 이미 완전함(로마자 표기 폴백 없음)"
        return baseline, baseline_ok, info

    try:
        body, serial = _split_serial_suffix(text)
        body, notice = _split_notice_suffix(body)
        if not body.strip():
            info["reason"] = "공고 유형 문구만 있고 본문이 없음"
            return baseline, baseline_ok, info
        protected, mapping = _protect(body)
        reference = _restore(protected, mapping)
        if len(_CJK_RE.findall(protected)) <= _MT_MIN_HANZI:
            # 용어집만으로 사실상 다 처리됐다. 이 상태로 번역기를 부르면
            # 입력이 거의 전부 자리표시자라 끝부분을 잘라먹거나 같은 단어를
            # 수십 번 반복한다(실측). 번역기를 부르지 않는 편이 정확하다.
            # 모델이 없어도 이 경로는 그대로 동작한다.
            raw = protected
            candidate = _postprocess(zh_translate._apply_glossary(reference))
            engine = "glossary-protected"
        elif not _load_argos():
            info["reason"] = _argos_reason or "Argos 사용 불가"
            return baseline, baseline_ok, info
        else:
            raw = _argos_translate.translate(
                _argos_translate.translate(protected, "zh", "en"), "en", "ko")
            candidate = _postprocess(_restore(_fix_english_leftovers(raw), mapping))
            # 발주기관 표기와 맞춘다: 번역기는 "科技有限公司"를 "기술 유한공사"로
            # 옮기지만 발주기관 쪽 용어집은 "과학기술 유한공사"로 낸다. 자리표시자로
            # 보호하면 토큰이 늘어 번역이 불안정해져서(실측: 채택 21→20건)
            # 원문에 그 표현이 있을 때만 결과에서 좁게 맞춘다.
            if "科技有限公司" in body and "과학기술" not in candidate:
                candidate = re.sub(r"(?<!과학)기술\s*유한공사", "과학기술 유한공사", candidate)
            engine = "argos+glossary"
    except Exception as exc:  # noqa: BLE001
        info["reason"] = f"번역 중 오류: {type(exc).__name__}"
        return baseline, baseline_ok, info

    full = " ".join(p for p in (candidate, notice, serial) if p)
    info["protected"] = len(mapping)
    info["tokenIssues"] = _token_issues(raw, mapping)
    info["candidate"] = full

    ok, reason = validate(reference, candidate, mapping, raw)
    if not ok:
        info["reason"] = reason
        return baseline, baseline_ok, info

    # 가독성이 실제로 나아졌을 때만 채택한다(지시문 16번).
    if _hangul_ratio(full) < _hangul_ratio(baseline):
        info["reason"] = "한글 비중이 기존 번역보다 낮음"
        return baseline, baseline_ok, info

    info["engine"] = engine
    # 번역기를 실제로 부른 경로만 기억해 둔다. 용어집 경로는 원래 결정적이라
    # 기억할 필요가 없고, 용어집을 고쳤을 때 곧바로 반영돼야 한다.
    if engine == "argos+glossary":
        translation_memory.remember("zh_ko", text, full)
    return full, True, info


# 발주기관(org) 표기에 쓰는 사전. 제목과 **같은** 회사명 사전을 쓴다 —
# 같은 회사가 제목과 발주기관에서 다르게 보이면 안 되기 때문이다.
# 회사 고유명 → 지역 → 업종/법인격 순으로 긴 표현부터 치환한다.
_ORG_GROUPS = (ORG_NAME_TERMS, COMPANY_TERMS, REGION_TERMS, ADMIN_TERMS, TECH_TERMS)


def translate_org(text):
    """중국어 발주기관명 → (한국어 표기, 완전 번역 여부).

    회사명 사전으로 먼저 덮고, 남은 부분은 기존 zh_translate에 그대로 맡긴다
    (용어집 → 로마자 표기 폴백). 즉 기존 안전장치를 대체하지 않고 앞단에만
    회사명 사전을 얹는 구조다.

    반환값이 (None, False)이면 "발주기관을 확정할 수 없다"는 뜻이다 —
    호출부가 기존대로 "확인 필요"를 표시한다."""
    if not text:
        return text, True

    stripped = text.strip()
    # EBNEW 상세 페이지에서 "招标机构：" 값이 한 글자만 잘려 들어오는 경우가
    # 실제로 있다(예: "招"). 이런 조각을 로마자로 읽어 "Zhao"라고 보여주면
    # 없는 회사를 만들어내는 셈이라, 뜻을 지어내지 않고 확인 필요로 남긴다.
    if len(stripped) <= 1 and _CJK_RE.search(stripped):
        return None, False

    result = stripped
    for group in _ORG_GROUPS:
        for term, korean in sorted(group.items(), key=lambda kv: len(kv[0]), reverse=True):
            # 치환값 안에 한자를 품은 항목(기존 사전의 동음 구분 병기)은
            # 여기서 손대지 않는다 — 뒤에서 zh_translate가 한 번 더 처리하며
            # "산시성(산시성(...))"처럼 이중 치환되기 때문이다.
            if _CJK_RE.search(korean):
                continue
            if term in result:
                result = result.replace(term, f" {korean} ")
    result = re.sub(r"\s{2,}", " ", result).strip()

    # 남은 한자는 기존 방식(용어집 → 로마자 표기)으로 처리한다.
    return zh_translate.translate(result)
