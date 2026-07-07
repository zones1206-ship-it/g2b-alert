"""
중국어 공고 제목/요약을 한국어로 표시하기 위한 용어집 기반 변환기.

중요: 이건 진짜 기계번역(NMT)이 아니다. 이 환경에는 번역 API(Papago/Google/DeepL 등)가
연결돼 있지 않아, 회사명·기술용어·행정용어 용어집으로 알려진 단어만 치환하는
"최선 노력형" 변환이다. 원문에 없는 뜻을 추측해서 문장을 새로 만들지 않는다.

- 회사명은 완전히 한글로 바꾸지 않고 "영문명(원문한자)" 형식을 유지한다
  (예: 京东方 -> BOE(京东方)).
- 기술용어는 한국어와 원어 약어를 함께 표기한다(예: 自动光学检测 -> 자동광학검사(AOI)).
- 용어집에 없는 한자가 결과에 너무 많이 남으면(용어집 커버리지가 낮으면) "번역 실패"로
  보고 원문을 그대로 표시한다(임의로 지어내지 않는다 — 공고 자체를 삭제하지도 않는다).
"""

import re

# 회사명: 완전 치환이 아니라 "영문명(원문)" 형식으로 병기
COMPANY_TERMS = {
    "京东方": "BOE(京东方)",
    "华星光电": "TCL CSOT(华星光电)",
    "长鑫存储": "CXMT(长鑫存储)",
    "维信诺": "Visionox(维信诺)",
    "天马微电子": "Tianma(天马微电子)",
    "天马": "Tianma(天马)",
}

# 기술/공정 용어: 한국어 + 원어 약어 병기
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
    "显示面板": "디스플레이 패널",
    "显示设备": "디스플레이 장비",
    "有机发光二极管": "유기발광다이오드(OLED)",
    "液晶显示": "액정디스플레이(LCD)",
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
}

# 공고/행정 상용어(직역이 아니라 관용적으로 자주 쓰이는 대응어를 붙인다)
GENERIC_TERMS = {
    "招标公告": "입찰공고",
    "招标": "입찰",
    "中标结果公告": "낙찰 결과 공고",
    "中标结果": "낙찰 결과",
    "评标结果公示": "심사결과 공시",
    "评标结果": "심사결과",
    "资格预审公告": "입찰참가자격 사전심사 공고",
    "资格预审": "참가자격 사전심사",
    "采购项目": "구매 프로젝트",
    "采购公告": "구매 공고",
    "采购": "구매",
    "项目": "프로젝트",
    "设备": "장비",
    "系统": "시스템",
    "生产线": "생산라인",
    "扩产": "증설",
    "工厂": "공장",
    "国际招标": "국제입찰",
    "国内招标": "국내입찰",
    "供应商": "공급사",
    "谈判采购": "협상 구매",
    "单一来源": "단독 소싱",
    "询价": "견적 문의",
    "成交公告": "낙찰 공고",
    "股份有限公司": "주식회사",
    "有限公司": "유한공사",
    "集团": "그룹",
    "国际": "국제",
    "键合机": "본더(Bonder)",
    "生长炉": "성장로(Growth Furnace)",
    "单晶": "단결정(Single Crystal)",
    "刻蚀机": "식각기(Etcher)",
    "光学仪器": "광학기기",
}

# 자주 나오는 지역명(성/직할시) — 화면의 "지역" 표시용
REGION_TERMS = {
    "北京": "베이징", "上海": "상하이", "深圳": "선전", "广东": "광둥성",
    "江苏": "장쑤성", "浙江": "저장성", "湖南": "후난성", "湖北": "후베이성",
    "四川": "쓰촨성", "重庆": "충칭", "山东": "산둥성", "河南": "허난성",
    "福建": "푸젠성", "安徽": "안후이성", "陕西": "산시성(陕西)",
    "天津": "톈진", "辽宁": "랴오닝성", "江西": "장시성", "河北": "허베이성",
}

# 이 목록 순서대로 치환한다(긴 구문을 먼저 치환해야 짧은 구문이 그 안의 일부를
# 잘못 치환하는 것을 막을 수 있다).
_ORDERED_DICTS = [COMPANY_TERMS, TECH_TERMS, GENERIC_TERMS]


def _apply_glossary(text: str):
    result = text
    for d in _ORDERED_DICTS:
        for zh, ko in sorted(d.items(), key=lambda kv: -len(kv[0])):
            result = result.replace(zh, f" {ko} ")
    return re.sub(r"\s+", " ", result).strip()


def _cjk_ratio(text: str):
    if not text:
        return 0.0
    cjk = len(re.findall(r"[一-鿿]", text))
    return cjk / max(len(text), 1)


def translate(text: str):
    """용어집 치환을 적용한 뒤, 남은 한자 비율이 너무 높으면(용어집 커버리지가
    낮으면) 번역 실패로 보고 원문을 그대로 반환한다(지어내지 않는다).
    반환값: (번역된 텍스트 또는 원문, 번역 성공 여부)"""
    if not text:
        return text, False
    converted = _apply_glossary(text)
    ratio = _cjk_ratio(converted)
    # 절반 넘게 한자가 그대로 남아있으면 신뢰할 만한 번역이 아니라고 본다.
    success = ratio < 0.5
    return (converted if success else text), success


def translate_region(text: str):
    if not text:
        return text
    for zh, ko in REGION_TERMS.items():
        # "省"/"市" 접미사가 붙은 형태(예: 福建省)를 먼저 치환해 중복
        # 접미사가 남지 않게 한다(福建省 -> 푸젠성, 福建 -> 푸젠성).
        if zh + "省" in text:
            return text.replace(zh + "省", ko)
        if zh + "市" in text:
            return text.replace(zh + "市", ko)
        if zh in text:
            return text.replace(zh, ko)
    return text
