"""
영문 공고 제목을 한국어로 옮기는 번역기 (JETRO 전용, PoC의 C′ 방식).

처리 순서:
  원문 영어 → 전문용어·고유명사·숫자단위 보호(자리표시자 치환)
  → Argos Translate(en→ko 직접 모델) → 보호한 표현 복원
  → 자동 검증(숫자/약어/고유명사/토큰 잔존/길이)
  → 통과하면 한국어 제목 채택, 실패하면 기존 용어집 결과로 되돌린다.

왜 이렇게 하나 (PoC에서 실측한 근거):
  - Argos 단독은 읽기는 좋아지지만 고유명사를 8건 중 7건 망가뜨렸다
    (京东方→"동부 광 발전", 广州华星→"중국 스타"). 보호가 필수다.
  - `prober`→"조사관", `Electron Beam`→"광속", `Parameter Analyzer`→
    "모수 해석기" 같은 도메인 오역이 실제로 나왔다. 이 표현들은 아예
    번역 대상에서 빼고 우리가 정한 한국어로 복원한다.
  - 자리표시자에 같은 글자가 연속되면 Argos가 글자를 덧붙이고(ZZAAA→ZZAAAA),
    기호가 섞이면 지워버린다. 그래서 글자가 반복되지 않는 영문 토큰을 쓰고
    복원할 때 글자 중복을 허용하는 정규식으로 되돌린다.

안전장치:
  Argos나 모델이 없으면(로컬 개발 환경, Actions 캐시 실패 등) 예외를 내지 않고
  기존 en_translate 용어집 방식으로 조용히 폴백한다 — 번역 때문에 수집
  전체가 실패하면 안 되기 때문이다.
"""

import re

from . import en_translate

# ---------------------------------------------------------------------------
# 1) 보호 대상 — 번역기에 넘기지 않고 우리가 정한 표기로 되돌릴 표현들
# ---------------------------------------------------------------------------

# (가) 공정·장비 전문용어. 값은 최종 화면에 쓸 한국어 표기.
PROTECTED_TERMS = {
    # PoC에서 실제 오역이 확인된 것들 — 최우선 보호
    "probe station": "프로브 스테이션",
    "prober": "프로버",
    "probers": "프로버",
    "electron beam": "전자빔",
    "e-beam": "전자빔",
    "parameter analyzer": "파라미터 분석기",
    # 증착
    "pecvd": "PECVD", "pvd": "PVD", "cvd": "CVD", "ald": "ALD",
    "sputtering": "스퍼터링", "sputter": "스퍼터", "evaporation": "증착(Evaporation)",
    # 식각·세정
    "drie": "DRIE", "rie": "RIE", "icp": "ICP",
    "wet cleaning": "습식 세정", "wet bench": "웨트벤치",
    "dry etching": "건식 식각", "wet etching": "습식 식각",
    "etching": "식각", "etcher": "식각 장비", "etch": "식각",
    "plasma cleaning": "플라즈마 세정",
    # 도금·평탄화
    "cu plating": "구리 도금", "copper plating": "구리 도금",
    "electroplating": "전해 도금", "ecd": "ECD", "cmp": "CMP",
    "seed layer": "시드층",
    # 본딩·패키징
    "wafer bonding": "웨이퍼 본딩", "hybrid bonding": "하이브리드 본딩",
    "die bonding": "다이 본딩", "bonder": "본더",
    "advanced packaging": "첨단 패키징",
    # 노광·패터닝
    "photolithography": "포토리소그래피", "lithography": "리소그래피",
    "photoresist": "포토레지스트", "stepper": "스테퍼",
    # 반도체·디스플레이·유리
    "semiconductor": "반도체", "wafer": "웨이퍼", "cleanroom": "클린룸",
    "through glass via": "유리관통전극(TGV)", "glass substrate": "유리기판",
    "glass interposer": "글라스 인터포저", "tgv": "TGV",
    "microled": "마이크로 LED", "micro led": "마이크로 LED",
    "oled": "OLED", "amoled": "AMOLED", "tft-lcd": "TFT-LCD", "lcd": "LCD",
    # 계측
    "ellipsometer": "엘립소미터", "profilometer": "표면조도 측정기",
    "film thickness": "박막 두께", "metrology": "계측",
    "microscope": "현미경", "confocal": "공초점",
    # 재료·원소명 — Argos가 국가명 등으로 오역한다(실측: Germanium→"독일").
    "germanium": "게르마늄", "silicon": "실리콘", "gallium": "갈륨",
    "indium": "인듐", "titanium": "티타늄", "tantalum": "탄탈럼",
    "tungsten": "텅스텐", "molybdenum": "몰리브덴", "sapphire": "사파이어",
    "quartz": "석영", "photomask": "포토마스크",
    # 장비를 뜻하는 일반 명사 — 그대로 두면 "체계"로 번역된다.
    "system": "장비", "systems": "장비",
}

# (나) 고유명사 — 번역하지 않고 원문 그대로 되돌린다.
PROTECTED_PROPER_NOUNS = [
    "RIKEN", "AIST", "NIMS", "JAEA", "JAXA", "NEDO", "NICT", "QST", "JEOL",
    "Hitachi", "Tokyo Electron", "Shimadzu", "Canon", "Nikon", "Toshiba",
    "Panasonic", "Sony", "Fujitsu", "Mitsubishi", "Kyocera", "Ulvac",
    "Bruker", "Zeiss", "Oxford Instruments", "Thermo Fisher",
    "CMOS", "EIC", "X-ray", "MEMS", "SiC", "GaN", "InP", "EUV", "DUV",
]

# (다) 숫자+단위 — 값이 바뀌면 안 되는 표현.
UNIT_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mm|nm|μm|um|㎛|cm|inch|kV|kW|MHz|GHz|RF|EA|"
    r"generation|gen)\b|\b\d+\s*(?:set|sets|unit|units|system|systems|piece|pieces)\b",
    re.I,
)

# 자리표시자: 같은 글자가 연속되지 않는 토큰만 쓴다(Argos가 글자를 덧붙이는
# 경향이 실측됐다). 한 제목에서 이 개수를 넘는 보호 대상은 드물다.
_TOKENS = [
    "TERMAX", "TERMBO", "TERMCU", "TERMDI", "TERMEV", "TERMFO", "TERMGI",
    "TERMHU", "TERMIS", "TERMJO", "TERMKA", "TERMLU", "TERMNE", "TERMOP",
    "TERMQI", "TERMRU", "TERMSA", "TERMTE", "TERMVI", "TERMXO",
]

# ---------------------------------------------------------------------------
# 2) Argos 로딩 — 없으면 조용히 폴백
# ---------------------------------------------------------------------------

_argos_translate = None
_argos_ready = None
_argos_reason = ""


def _load_argos():
    """Argos와 en→ko 모델이 실제로 쓸 수 있는지 한 번만 확인한다."""
    global _argos_translate, _argos_ready, _argos_reason
    if _argos_ready is not None:
        return _argos_ready
    try:
        import argostranslate.translate as tr
        # 실제 번역을 한 번 시켜봐야 모델 설치 여부까지 확인된다.
        probe = tr.translate("semiconductor equipment", "en", "ko")
        if not probe or not re.search(r"[가-힣]", probe):
            _argos_ready = False
            _argos_reason = "en→ko 모델이 설치돼 있지 않음(번역 결과에 한국어 없음)"
        else:
            _argos_translate = tr
            _argos_ready = True
    except Exception as exc:  # noqa: BLE001
        _argos_ready = False
        _argos_reason = f"{type(exc).__name__}: {str(exc)[:80]}"
    return _argos_ready


def argos_status():
    """호출부에서 로그로 남길 수 있도록 상태를 알려준다."""
    ready = _load_argos()
    return ready, _argos_reason


# ---------------------------------------------------------------------------
# 3) 보호 → 번역 → 복원
# ---------------------------------------------------------------------------

def _protect(text):
    mapping = {}
    # 하이픈으로 붙은 보호어("Single-Wafer")는 자리표시자가 앞 단어와 한 덩어리로
    # 번역되면서 통째로 사라진다(실측: Single-Wafer → "단일 회로"). 보호 대상
    # 앞뒤의 하이픈만 공백으로 떼어 독립 토큰이 되게 한다.
    result = text
    for term in list(PROTECTED_TERMS) + [n.lower() for n in PROTECTED_PROPER_NOUNS]:
        if "-" in term:
            continue  # TFT-LCD처럼 하이픈이 이름의 일부인 건 건드리지 않는다
        result = re.sub(r"(?<=[A-Za-z0-9])-(" + re.escape(term) + r")(?![A-Za-z0-9])",
                        r" \1", result, flags=re.I)
        result = re.sub(r"(?<![A-Za-z0-9])(" + re.escape(term) + r")-(?=[A-Za-z0-9])",
                        r"\1 ", result, flags=re.I)
    idx = 0

    def take_token():
        nonlocal idx
        if idx >= len(_TOKENS):
            return None
        token = _TOKENS[idx]
        idx += 1
        return token

    # 긴 표현부터 치환해야 "wet etching"이 "etch"로 쪼개지지 않는다.
    ordered = sorted(PROTECTED_TERMS.items(), key=lambda kv: len(kv[0]), reverse=True)
    for term, korean in ordered:
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.I)
        if not pattern.search(result):
            continue
        token = take_token()
        if token is None:
            break
        mapping[token] = korean
        result = pattern.sub(token, result)

    for noun in sorted(PROTECTED_PROPER_NOUNS, key=len, reverse=True):
        pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(noun) + r"(?![A-Za-z0-9])", re.I)
        if not pattern.search(result):
            continue
        token = take_token()
        if token is None:
            break
        mapping[token] = noun  # 고유명사는 원문 그대로 되돌린다
        result = pattern.sub(token, result)

    def unit_repl(match):
        token = take_token()
        if token is None:
            return match.group(0)
        # 숫자는 그대로 두고 수량 단위만 한국어 표기로 맞춘다(기존 화면 표기와
        # 일관되게 "1 set"은 "1식"으로 보여준다 — 값 자체는 바뀌지 않는다).
        raw = match.group(0).strip()
        korean = re.sub(r"(\d+)\s*(sets?)\b", r"\1식", raw, flags=re.I)
        korean = re.sub(r"(\d+)\s*(units?|systems?)\b", r"\1대", korean, flags=re.I)
        korean = re.sub(r"(\d+)\s*(pieces?)\b", r"\1개", korean, flags=re.I)
        mapping[token] = korean
        return token

    result = UNIT_PATTERN.sub(unit_repl, result)
    return result, mapping


def _restore(text, mapping):
    for token, value in mapping.items():
        # 글자 중복(TERMAX→TERMAAX)과 대소문자 흔들림을 허용해 복원한다.
        loose = "".join(f"{ch}+" for ch in token)
        text = re.sub(loose, value, text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()


# ---------------------------------------------------------------------------
# 4) 검증 — 통과하지 못하면 번역 결과를 쓰지 않는다
# ---------------------------------------------------------------------------

def _numbers(text):
    return sorted(re.findall(r"\d+(?:\.\d+)?", text or ""))


def _acronyms(text):
    """대문자 약어만 뽑는다. 'CMOS-Silicon'처럼 약어+일반단어가 하이픈으로
    붙은 경우 예전 정규식은 'CMOS-S'라는 없는 약어를 만들어내 멀쩡한 번역을
    검증 실패로 떨어뜨렸다. 순수 대문자 2자 이상만 약어로 본다."""
    return {w.upper() for w in re.findall(r"(?<![A-Za-z0-9])[A-Z]{2,}[0-9]*(?![a-z])", text or "")}


def validate(original, translated, mapping):
    """(통과 여부, 실패 사유)를 돌려준다."""
    if not translated or not translated.strip():
        return False, "번역 결과가 비어 있음"
    if not re.search(r"[가-힣]", translated):
        return False, "번역 결과에 한국어가 없음"
    if re.search(r"TERM[A-Z]", translated, re.I):
        return False, "보호 토큰이 복원되지 않음"
    if _numbers(original) != _numbers(translated):
        return False, f"숫자 불일치({_numbers(original)} → {_numbers(translated)})"
    missing = [a for a in _acronyms(original) if a not in _acronyms(translated)
               and a.lower() not in translated.lower()]
    if missing:
        return False, f"약어 소실({', '.join(sorted(missing)[:3])})"
    # 원문 대비 지나치게 짧아지면 내용이 통째로 날아간 것으로 본다.
    if len(translated) < max(6, len(original) * 0.35):
        return False, "번역이 원문 대비 과도하게 짧음"
    return True, None


# ---------------------------------------------------------------------------
# 5) 공개 함수
# ---------------------------------------------------------------------------

def translate_title(text):
    """영문 제목 → (한국어 제목, 번역 완료 여부, 진단정보 dict).

    Argos 검증을 통과하면 그 결과를 쓰고, 그렇지 않으면 기존 용어집 결과를
    그대로 쓴다(잘못된 한국어를 억지로 보여주지 않는다)."""
    baseline, baseline_ok = en_translate.translate_title(text)
    info = {"engine": "glossary", "protected": [], "reason": None}

    if not text or not _load_argos():
        info["reason"] = _argos_reason or "원문 없음"
        return baseline, baseline_ok, info

    try:
        protected, mapping = _protect(text)
        raw = _argos_translate.translate(protected, "en", "ko")
        candidate = _restore(raw, mapping)
    except Exception as exc:  # noqa: BLE001
        info["reason"] = f"번역 중 오류: {type(exc).__name__}"
        return baseline, baseline_ok, info

    ok, reason = validate(text, candidate, mapping)
    info["protected"] = sorted(set(mapping.values()))
    if not ok:
        info["reason"] = reason
        return baseline, baseline_ok, info

    info["engine"] = "argos+glossary"
    return candidate, True, info
