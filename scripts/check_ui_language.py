"""사용자 화면에 남은 외국어를 찾아 보고한다.

지시문 No.015 14번. 화면을 한국어로 통일한 뒤, 나중에 다시 외국어가 새어
나오는 것을 잡기 위한 도구다.

검사 대상은 **사용자에게 보이는 것**뿐이다:
  - data/announcements.json 의 사용자 표시 필드(title/org/description …)
  - app.js / index.html 의 화면 출력 문구

원문 보존 필드(originalTitle/originalOrg/originalSummary/originalUrl)는
외국어인 것이 정상이라 검사하지 않는다. CSS class명·변수명·주석도 화면에
나오지 않으므로 대상이 아니다.

판정 기준은 두 단계다.

  치명(exit 1) — 한자·가나가 사용자 필드에 남은 경우.
      번역 경로가 무조건 로마자로라도 바꾸게 되어 있으므로, 여기 걸리면
      파이프라인이 깨진 것이다.
      금지된 영어 UI 문구("China Site", "D-DAY" 같은)가 소스에 되살아난 경우도
      여기 포함한다.

  경고(exit 0) — 로마자 폴백(pinyin)이나 허용 목록 밖 영단어.
      공고 원문에 원래 영어 모델명이 들어 있는 경우가 많아 이것만으로
      수집을 막지는 않는다. 늘어나면 사람이 보고 판단한다.

사용법:
    python scripts/check_ui_language.py            # 보고만
    python scripts/check_ui_language.py --strict   # 경고도 실패로 처리
"""

import io
import json
import os
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 화면에 그대로 나가는 필드. originalXxx 는 일부러 뺐다(원문 보존용).
USER_FIELDS = ("title", "org", "description", "translatedSummary",
               "equipmentName", "process", "industry", "country", "region",
               "source", "noticeType", "contractMethod", "status",
               "deliveryCondition", "paymentCondition", "eligibility")

CJK_RE = re.compile(r"[一-鿿]")
KANA_RE = re.compile(r"[぀-ヿ]")
# 용어집에 없어 pypinyin으로 떨어진 흔적(붙여 쓴 CamelCase).
PINYIN_RE = re.compile(r"(?<![A-Za-z])[A-Z][a-z]+(?:[A-Z][a-z]+)+(?![A-Za-z])")
WORD_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9.\-]*(?![A-Za-z0-9])")

# 한국어와 함께 쓰는 것이 표준인 약어·고유명은 허용한다. "영문자가 하나라도
# 있으면 실패" 같은 검사는 쓸모가 없다(지시문 No.015 14번).
ALLOWED_WORDS = {
    # 공정·장비 표준 약어
    "AOI", "ALD", "CVD", "PVD", "PECVD", "MOCVD", "CMP", "TGV", "RTP", "ECD",
    "RIE", "DRIE", "LED", "OLED", "AMOLED", "TFT", "TFT-LCD", "LCD", "MINI",
    "COB", "SOI", "CMOS", "MRAM", "TEG", "ESC", "GaN", "PLP", "WLP", "SEM",
    "TEM", "UPS", "AHU", "HVAC", "X-ray", "D-Poly", "D-POLY", "POLY", "SET",
    # 수집원·기관 공식 약어
    "KOTRA", "JETRO", "ITRI", "DGIST", "KAIST", "KANC", "NNFC", "KRISS",
    "EBNEW", "MOFCOM", "RIKEN", "AIST", "JAEA", "NIMS", "QST", "JAXA",
    "NEDO", "NICT", "BOE", "TCL", "CSOT", "EIC", "IC",
    # 단위·형식
    "nm", "mm", "cm", "um", "kW", "MHz", "GHz", "inch", "set", "sets",
    "pdf", "hwp", "hwpx", "xlsx", "docx", "zip",
}

# 소스에서 되살아나면 안 되는 영어 UI 문구.
#
# **화면에 출력되는 위치만** 잡는다. 데이터 값 비교(item.sourceType ===
# "China Site")나 코드 주석은 사용자에게 보이지 않으므로 대상이 아니다.
# 그래서 따옴표만 보지 않고 출력 문맥(태그 사이, 배지 안, 삼항식 값)까지
# 포함한 형태로 적는다.
FORBIDDEN_UI_STRINGS = [
    ">China Site<", "🌐 China Site",       # 화면에 찍히는 텍스트 노드
    '? "D-DAY"',                            # D-day 배지 문구
    'new-badge">NEW<',                      # 신규 배지
]


def _load_items():
    path = os.path.join(ROOT, "data", "announcements.json")
    data = json.loads(io.open(path, encoding="utf-8").read())
    return data.get("items") or []


def check_data():
    """(치명 목록, 경고 목록)"""
    fatal, warn = [], []
    for item in _load_items():
        for field in USER_FIELDS:
            value = item.get(field)
            if not isinstance(value, str) or not value:
                continue
            where = f"{item.get('id')}.{field}"
            if CJK_RE.search(value):
                fatal.append((where, "한자", CJK_RE.findall(value)[:8], value[:90]))
            if KANA_RE.search(value):
                fatal.append((where, "가나", KANA_RE.findall(value)[:8], value[:90]))
            pinyin = [t for t in PINYIN_RE.findall(value) if t not in ALLOWED_WORDS]
            if pinyin:
                warn.append((where, "로마자 표기", pinyin, value[:90]))
            words = [w for w in WORD_RE.findall(value)
                     if w not in ALLOWED_WORDS and w.upper() not in ALLOWED_WORDS
                     and not PINYIN_RE.fullmatch(w)]
            if words:
                warn.append((where, "영단어", words[:8], value[:90]))
    return fatal, warn


def check_sources():
    """app.js / index.html 에 금지된 영어 UI 문구가 있는지."""
    fatal = []
    for name in ("app.js", "index.html"):
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        text = io.open(path, encoding="utf-8").read()
        for needle in FORBIDDEN_UI_STRINGS:
            if needle in text:
                fatal.append((name, "금지된 UI 문구", [needle], needle))
    return fatal


def main(strict=False):
    fatal, warn = check_data()
    fatal += check_sources()

    print(f"[UI] 치명 {len(fatal)}건 / 경고 {len(warn)}건")
    for where, kind, tokens, sample in fatal:
        print(f"  [치명] {where} — {kind} {tokens}")
        print(f"         {sample}")
    shown = 0
    for where, kind, tokens, sample in warn:
        if shown >= 25:
            print(f"  ... 경고 {len(warn) - shown}건 더 있음")
            break
        print(f"  [경고] {where} — {kind} {tokens}")
        shown += 1

    if fatal:
        print("\n[UI] 사용자 화면에 한자·가나가 남았거나 금지된 영어 UI 문구가 "
              "되살아났습니다.")
        return 1
    if strict and warn:
        return 1
    print("[UI] 사용자 화면에 치명적인 외국어 잔여 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(strict="--strict" in sys.argv))
