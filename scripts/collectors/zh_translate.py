"""
중국어 공고 제목/발주처/요약을 한국어 화면에 표시하기 위한 변환기.

중요: 이건 진짜 문장 단위 기계번역(NMT)이 아니다. 이 환경에는 번역 API
(Papago/Google/DeepL 등)가 연결돼 있지 않다. 대신 2단계로 처리한다:

  1) 용어집(회사명/기술용어/행정용어) + 숫자 패턴(제N대, 연산 N만개 등)
     치환 — 뜻을 아는 만큼만 정확하게 바꾼다.
  2) 그래도 남은 한자(용어집에 없는 고유명사 등)는 pypinyin으로
     로마자 표기(발음 표기)한다 — 뜻을 지어내지 않고 "읽는 법"만 알려주는
     것이라 사실 왜곡이 아니다. 이 단계를 쓰면 카드 화면에는 한자가
     하나도 남지 않는다.

원문(중국어 그대로)은 항상 별도 필드(originalTitle/originalOrg 등)에
보존하고, 상세보기에서만 노출한다 — 카드 목록 화면 기본 표시에는 절대
넣지 않는다.

translate()의 반환값 두 번째 요소(ok)는 "용어집만으로 완전히 번역됐는가"
(True) 대 "일부라도 로마자 표기(pinyin) 폴백을 썼는가"(False, 즉
translationIncomplete 대상)를 뜻한다. pinyin 폴백을 썼어도 결과 문자열
자체에는 한자가 남지 않는다 — ok=False는 "화면에 한자가 보인다"는 뜻이
아니라 "품질이 검토 필요 수준"이라는 내부 표시다.
"""

import re

try:
    from pypinyin import lazy_pinyin
    _HAS_PINYIN = True
except ImportError:  # 의존성이 설치 안 된 환경(예: 로컬에서 pip install 전)에서도
    _HAS_PINYIN = False  # 죽지 않고 원문을 그대로 남기는 폴백으로 동작한다.

# 회사명: 완전 치환이 아니라 "영문명(한국식 발음 표기)" 형식으로 병기.
# 괄호 안은 원문 한자가 아니라 한국어 화면에서 바로 읽을 수 있는 표기다
# (카드 목록에 한자가 남으면 안 되므로) — 원문 한자는 originalTitle 등
# 별도 필드에서만 보존한다.
COMPANY_TERMS = {
    "京东方科技集团": "BOE(징둥팡)",
    "京东方": "BOE(징둥팡)",
    "TCL华星光电": "TCL CSOT(화싱광전)",
    "华星光电": "화싱광전",
    "TCL华星": "TCL CSOT(화싱광전)",
    "华星": "화싱",
    "长鑫存储": "CXMT(창신메모리)",
    "维信诺": "Visionox(웨이신눠)",
    "天马微电子": "Tianma(톈마)",
    "天马": "Tianma(톈마)",
    "国显科技": "궈셴과기",
    "中芯国际": "SMIC(중신궈지)",
    "长江存储": "YMTC(창장춘추)",
    "华虹半导体": "화훙반도체",
    "隆基绿能": "룽지그린에너지",
    "通威股份": "퉁웨이",
}

# 기술/공정 용어: 한국어 + 원어 약어 병기(용어 자체는 유지 가능한 항목).
TECH_TERMS = {
    "自动光学检测": "자동광학검사(AOI)",
    "原子层刻蚀": "원자층 식각(ALE)",
    "玻璃基板": "유리기판(Glass Substrate)",
    "玻璃通孔": "TGV(Through Glass Via)",
    "玻璃芯基板": "유리 코어 기판(Glass Core Substrate)",
    "玻璃中介层": "유리 인터포저(Glass Interposer)",
    "玻璃封装基板": "유리 패키징 기판(Glass Packaging Substrate)",
    "先进封装": "첨단 패키징(Advanced Packaging)",
    "面板级封装": "패널레벨패키징(PLP)",
    "晶圆级封装": "웨이퍼레벨패키징(WLP)",
    "铜填充": "구리 충진(Cu Filling)",
    "化学镀铜": "무전해동도금(Electroless Copper Plating)",
    "电镀铜": "전해동도금(Copper Electroplating)",
    "激光钻孔": "레이저 드릴링(Laser Drilling)",
    "湿法刻蚀": "습식 식각(Wet Etching)",
    "玻璃刻蚀": "유리 식각(Glass Etching)",
    "通孔加工": "관통홀 가공(Via Formation)",
    "清洗设备": "세정 장비(Cleaning Equipment)",
    "检测设备": "검사 장비(Inspection Equipment)",
    "中介层": "인터포저(Interposer)",
    "高带宽存储器": "고대역폭메모리(HBM)",
    "硅通孔": "실리콘관통전극(TSV)",
    "新型显示技术": "신형 디스플레이 기술",
    "新型显示器": "신형 디스플레이",
    "显示技术": "디스플레이 기술",
    "显示面板": "디스플레이 패널",
    "显示器件": "디스플레이 소자",
    "显示设备": "디스플레이 장비",
    "有机发光二极管": "유기발광다이오드(OLED)",
    "液晶显示器件": "액정디스플레이(LCD) 소자",
    "液晶显示": "액정디스플레이(LCD)",
    "薄膜晶体管": "박막트랜지스터(TFT)",
    "微型发光二极管": "마이크로 LED(Micro LED)",
    "半导体设备": "반도체 장비",
    "半导体": "반도체",
    "晶圆": "웨이퍼",
    "封装": "패키징",
    "刻蚀": "식각",
    "沉积": "증착",
    "薄膜": "박막",
    "光刻": "포토리소그래피",
    "镀膜": "코팅",
    "键合机": "본더(Bonder)",
    "生长炉": "성장로(Growth Furnace)",
    "单晶": "단결정(Single Crystal)",
    "刻蚀机": "식각기(Etcher)",
    "光学仪器": "광학기기",
}

# 공고/행정/기업 상용어(직역이 아니라 관용적으로 자주 쓰이는 대응어).
GENERIC_TERMS = {
    "招标公告": "입찰공고",
    "招标": "입찰",
    "中标结果公告": "낙찰 결과 공고",
    "中标结果": "낙찰 결과",
    "评标结果公示公告": "심사결과 공시 공고",
    "评标结果公示": "심사결과 공시",
    "评标结果": "심사결과",
    "重新招标澄清或变更公告": "재입찰 정정·변경 공고",
    "澄清或变更公告": "정정·변경 공고",
    "资格预审公告": "입찰참가자격 사전심사 공고",
    "资格预审": "참가자격 사전심사",
    "采购项目": "구매 프로젝트",
    "采购公告": "구매 공고",
    "采购": "구매",
    "项目": "프로젝트",
    "设备": "장비",
    "系统": "시스템",
    "生产线": "생산라인",
    "生产项目": "생산 프로젝트",
    "生产基地": "생산기지",
    "产业化基地": "산업화기지",
    "扩产": "증설",
    "工厂": "공장",
    "厂房": "공장동",
    "国际招标": "국제입찰",
    "国内招标": "국내입찰",
    "供应商": "공급사",
    "谈判采购": "협상 구매",
    "单一来源": "단독 소싱",
    "询价": "견적 문의",
    "成交公告": "낙찰 공고",
    "股份有限公司": "주식회사",
    "有限公司": "유한공사",
    "创新科技": "혁신과학기술",
    "创新中心": "혁신센터",
    "科技集团": "과기그룹",
    "科技": "과학기술",
    "集团": "그룹",
    "国际": "국제",
    "开发": "개발",
    "年产": "연간생산",
    "产品": "제품",
    "模组": "모듈",
    "升级": "업그레이드",
    "改造": "개조",
    "及": "및",
    "万件": "만개",
    "万片": "만장",
    "万台": "만대",
    "万平米": "만㎡",
    "结果": "결과",
    "公示": "공시",
    "送达": "송달",
    "通知": "통지",
    "变更": "변경",
    "取消": "취소",
    "延期": "연기",
    "补充": "보충",
}

# 자주 나오는 지역명(성/직할시/주요 도시) — 화면의 "지역" 표시용이자,
# 회사명/제목 안에 섞여 나오는 지명도 함께 치환한다(예: "苏州市 TCL..."
# 처럼 제목 앞에 지명이 붙는 경우가 실제로 있다).
REGION_TERMS = {
    "北京": "베이징", "上海": "상하이", "深圳": "선전", "广东": "광둥성",
    "江苏": "장쑤성", "浙江": "저장성", "湖南": "후난성", "湖北": "후베이성",
    "四川": "쓰촨성", "重庆": "충칭", "山东": "산둥성", "河南": "허난성",
    "福建": "푸젠성", "安徽": "안후이성", "陕西": "산시성(陕西)",
    "天津": "톈진", "辽宁": "랴오닝성", "江西": "장시성", "河北": "허베이성",
    "苏州": "쑤저우", "武汉": "우한", "广州": "광저우", "佛山": "포산",
    "厦门": "샤먼", "合肥": "허페이", "郑州": "정저우", "长沙": "창사",
    "昆山": "쿤산", "南京": "난징", "无锡": "우시", "东莞": "둥관",
    "惠州": "후이저우", "成都": "청두", "西安": "시안", "杭州": "항저우",
    "宁波": "닝보", "青岛": "칭다오", "大连": "다롄", "沈阳": "선양",
}

# 숫자/단위가 섞인 구조는 사전 치환이 안 통해서 정규식으로 처리한다.
_NUMERIC_PATTERNS = [
    (re.compile(r"第(\d+(?:\.\d+)?)代"), r"제\1세대"),
    (re.compile(r"年产(\d+)万(件|片|台|平米)"), lambda m: f"연산{m.group(1)}만{ {'件':'개','片':'장','台':'대','平米':'㎡'}[m.group(2)] }"),
    (re.compile(r"(\d+)万(件|片|台|平米)"), lambda m: f"{m.group(1)}만{ {'件':'개','片':'장','台':'대','平米':'㎡'}[m.group(2)] }"),
]

# 지명에 "省"/"市" 접미사가 붙은 형태(苏州市, 福建省 등)가 본문 중간에
# 섞여 나올 때, 접미사 글자만 pinyin으로 로마자 표기되어 남는 것을 막기
# 위해 접미사 붙은 조합도 같은 값으로 미리 등록해둔다.
_REGION_WITH_SUFFIX = {}
for _zh, _ko in REGION_TERMS.items():
    _REGION_WITH_SUFFIX[_zh + "市"] = _ko
    _REGION_WITH_SUFFIX[_zh + "省"] = _ko

# 이 목록 순서대로 치환한다(긴 구문을 먼저 치환해야 짧은 구문이 그 안의 일부를
# 잘못 치환하는 것을 막을 수 있다).
_ORDERED_DICTS = [COMPANY_TERMS, _REGION_WITH_SUFFIX, REGION_TERMS, TECH_TERMS, GENERIC_TERMS]

_CJK_RE = re.compile(r"[一-鿿]")
_CJK_RUN_RE = re.compile(r"[一-鿿]+")


def _apply_numeric_patterns(text: str) -> str:
    for pattern, repl in _NUMERIC_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def _apply_glossary(text: str) -> str:
    result = _apply_numeric_patterns(text)
    for d in _ORDERED_DICTS:
        for zh, ko in sorted(d.items(), key=lambda kv: -len(kv[0])):
            result = result.replace(zh, f" {ko} ")
    return re.sub(r"\s+", " ", result).strip()


def _romanize_run(run: str) -> str:
    """용어집에 없는 한자 구간을 pypinyin으로 로마자 표기한다. 2글자씩
    끊어 표기해야(중국어는 대개 2음절 단어 단위라) 너무 길게 붙어버리는
    것을 막고 그나마 읽기 쉽다. 뜻을 지어내지 않고 "발음 표기"만 하는
    것이므로 사실 왜곡이 아니다."""
    if not _HAS_PINYIN:
        return run  # pypinyin 미설치 환경에서는 원문 그대로(한자) 반환 — 폴백의 폴백
    chunks = [run[i:i + 2] for i in range(0, len(run), 2)]
    words = []
    for chunk in chunks:
        syllables = lazy_pinyin(chunk)
        word = "".join(s.capitalize() for s in syllables)
        words.append(word)
    return " ".join(words)


def _romanize_remaining_cjk(text: str) -> str:
    return _CJK_RUN_RE.sub(lambda m: _romanize_run(m.group(0)), text)


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = len(_CJK_RE.findall(text))
    return cjk / max(len(text), 1)


def translate(text: str):
    """1) 용어집+숫자패턴 치환 → 2) 남은 한자는 pypinyin으로 로마자 표기.
    반환값: (한자가 남지 않는 최종 텍스트, ok)
    ok=True  : 용어집만으로 완전히 처리됨(고품질)
    ok=False : 일부 구간을 pinyin 로마자 표기로 폴백함
               (= 화면표시상 한자는 없지만 번역 품질 검토 필요,
               상위 코드에서 classificationStatus/translationIncomplete로 사용)"""
    if not text:
        return text, True
    converted = _apply_glossary(text)
    if not _CJK_RE.search(converted):
        return converted, True
    romanized = _romanize_remaining_cjk(converted)
    return romanized, False


def translate_region(text: str):
    if not text:
        return text
    result = text
    for zh, ko in REGION_TERMS.items():
        # "省"/"市" 접미사가 붙은 형태(예: 福建省)를 먼저 치환해 중복
        # 접미사가 남지 않게 한다(福建省 -> 푸젠성, 福建 -> 푸젠성).
        if zh + "省" in result:
            result = result.replace(zh + "省", ko)
            break
        if zh + "市" in result:
            result = result.replace(zh + "市", ko)
            break
        if zh in result:
            result = result.replace(zh, ko)
            break
    # 지역명 추출 단계에서 원치 않는 문단까지 같이 잡히는 등, 매칭된 지명
    # 이외의 한자가 남아 있을 수 있다 — 화면에 한자가 새지 않도록 나머지도
    # 전부 로마자 표기로 폴백한다(위 for 루프가 지명 하나만 치환하고 바로
    # break하기 때문에 이 안전망이 없으면 뒤에 붙은 한자가 그대로 노출될
    # 수 있었다 — 실제로 이런 사례가 있었다).
    if _CJK_RE.search(result):
        result = _romanize_remaining_cjk(result)
    return result
