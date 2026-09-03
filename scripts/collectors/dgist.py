"""
대구경북과학기술원(DGIST) 입찰정보 게시판 수집기.

KANC/KRISS와 동일한 구조(목록 파싱 → 관련성 판정 → 상세 파싱 → 표준 스키마)
를 따른다. 공개 게시판이며 로그인/CAPTCHA가 없다.

실제 페이지 구조 (2026-09 기준, 직접 확인해 작성):
- 목록: https://www.dgist.ac.kr/prog/bidPbanc/kor/sub06_01_04/list.do?pageIndex={page}
  표 헤더: No. | 구분 | 공고명 | 공고상태 | 입찰개시일 | 입찰마감일 | 첨부파일 | 나라장터 상세보기
  구분 값 예: 내자(물품) / 용역 / 공사 / 기타
- 상세: .../view.do?pbancNo={번호}
  표: 구분 / 진행상태 / 공고명 / 입찰개시일 / 입찰마감일 / 나라장터 상세링크 / 공고내용 / 첨부파일

주의: 이 사이트는 GitHub Actions 러너에서 간헐적으로 연결이 끊긴다
(러너에서 직접 확인: 1회차 Connection reset, 2회차 정상 200). 상시 차단은
아니어서 재시도로 대부분 커버되며, 그래도 실패하면 orchestrator가 이전
수집분을 유지하고 Health Check가 실패를 표시한다.

수집 대상은 반도체/디스플레이/TGV 및 관련 공정장비 공고로 한정한다.
DGIST는 종합 연구기관이라 일반 용역/행사/시설 공고가 훨씬 많으므로,
KANC와 같은 보수적 4단계 판정(장비 신호가 있어야 포함)을 쓴다.
"""

import re
import time
import html as html_lib
import urllib.error
import urllib.request

from .common import TGV_STRONG_TERMS, FetchState, NETWORK_EXCEPTIONS, should_retry, retry_delay, looks_like_empty_board

SOURCE_NAME = "DGIST (한국)"
SOURCE_CODE = "DGIST"
SOURCE_SITE_URL = "https://www.dgist.ac.kr/prog/bidPbanc/kor/sub06_01_04/list.do"

BASE_URL = "https://www.dgist.ac.kr"
LIST_URL_TMPL = BASE_URL + "/prog/bidPbanc/kor/sub06_01_04/list.do?pageIndex={page}"
DETAIL_URL_TMPL = BASE_URL + "/prog/bidPbanc/kor/sub06_01_04/view.do?pbancNo={no}"

MAX_LIST_PAGES = 3
# Actions 러너에서 실측한 결과(2026-09 진단):
#  - 정상 응답은 1~2초. 실패는 timeout까지 기다린 게 아니라 TLS 핸드셰이크
#    단계에서 즉시 끊긴다(curl exit 35, tls=0.000000s, 0.65초만에 실패).
#  - 2초 간격 5회와 15초 간격 3회가 같은 비율로 실패 → 짧은 간격 반복 호출에
#    따른 일시 제한이 아니라 무작위 연결 실패다.
#  - bot UA와 브라우저 UA 결과가 같아 UA 문제도 아니다.
# 그래서 timeout을 길게 두는 건 의미가 없고, 빨리 포기하고 재시도하는 쪽이
# 성공률과 실행시간 모두 유리하다. 최악의 경우에도 4x12 + (2+4+8) = 62초로
# 기존(3x25 + 3+6 = 84초)보다 짧다. 무한 재시도는 하지 않는다.
REQUEST_TIMEOUT = 12
MAX_RETRY_ATTEMPTS = 4
RETRY_DELAY_SECONDS = 2
PAGE_DELAY_SECONDS = 0.6

UA = "Mozilla/5.0 (compatible; g2b-alert-bot/1.0)"

# 공고 자체가 무효이거나 조달과 무관한 안내성 게시물
HARD_EXCLUDE_TERMS = ["취소", "매각", "사기피해", "안내드립니다", "유의사항"]

# 장비 신호(사용자가 지정한 수집 대상). 이 신호가 있어야 포함한다.
EQUIPMENT_INCLUDE_TERMS = [
    # 반도체
    "반도체", "웨이퍼", "wafer", "클린룸", "cleanroom", "fab", "팹",
    "패키징", "packaging", "본딩", "bonding", "본더", "bonder",
    # 디스플레이
    "디스플레이", "display", "oled", "마이크로led", "microled", "lcd", "패널", "panel",
    # TGV / 유리
    "tgv", "유리기판", "글라스", "glass",
    # 증착
    "증착", "pvd", "cvd", "pecvd", "ald", "스퍼터", "sputter", "sputtering", "evaporation",
    # 식각 / 세정
    "식각", "etch", "etching", "rie", "icp", "drie", "세정", "cleaning",
    "웨트벤치", "wet bench", "플라즈마", "plasma",
    # 도금 / 금속
    "도금", "plating", "ecd", "seed layer", "시드층",
    # CMP / 열처리
    "cmp", "연마", "polishing", "어닐링", "annealing", "열처리로", "furnace", "rtp",
    # 노광 / 패터닝
    "노광", "리소그래피", "lithography", "스테퍼", "stepper", "포토레지스트", "photoresist",
    "레이저", "laser",
    # 검사 / 계측 (아래 CONTEXT와 함께 있을 때만 인정)
    "계측", "metrology", "엘립소미터", "ellipsometer", "타원편광기",
    "프로파일로미터", "profilometer", "박막 두께", "박막두께", "film thickness",
]
EQUIPMENT_INCLUDE_TERMS += [t.lower() for t in TGV_STRONG_TERMS]

# 검사/계측 단어만 있는 경우 반도체·디스플레이 맥락이 함께 있어야 포함한다
# (일반 연구용 현미경/분석장비까지 끌어오지 않기 위해).
METROLOGY_ONLY_TERMS = [
    "계측", "metrology", "검사", "inspection", "sem", "tem", "현미경",
    "엘립소미터", "ellipsometer", "타원편광기", "프로파일로미터", "profilometer",
    "박막 두께", "박막두께", "두께 측정", "film thickness",
]
CONTEXT_TERMS = [
    "반도체", "웨이퍼", "wafer", "디스플레이", "display", "oled", "패널", "panel",
    "유리기판", "glass", "tgv", "클린룸", "cleanroom", "공정",
]

# 장비 신호가 없을 때 확실히 제외하는 서비스성 신호
SERVICE_EXCLUDE_TERMS = [
    "용역", "위탁", "교육", "행사", "홍보", "컨설팅", "운영", "관리",
    "청소", "경비", "차량", "급식", "보험", "임차", "인쇄", "설계",
    "리모델링", "수선", "공사", "조경", "네트워크", "소프트웨어", "라이선스",
    "클라우드", "서버", "노트북", "컴퓨터", "프린터", "가구", "도서",
]


def fetch(url):
    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
                return res.read().decode("utf-8", "ignore")
        except NETWORK_EXCEPTIONS as exc:
            last_error = exc
            # 403/404처럼 서버가 명확히 답한 HTTP 오류는 재시도하지 않는다
            # (429·5xx만 재시도 — collectors/common.py의 should_retry 참고).
            if not should_retry(exc):
                print(f"[DGIST] 재시도하지 않는 오류로 즉시 중단: {exc}")
                break
            if attempt < MAX_RETRY_ATTEMPTS:
                delay = retry_delay(exc, RETRY_DELAY_SECONDS * (2 ** (attempt - 1)))
                print(f"[DGIST] 요청 실패({exc}), {delay}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(delay)
    raise RuntimeError(f"DGIST 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def normalize(text):
    return re.sub(r"\s+", " ", html_lib.unescape(text or "")).strip()


def strip_tags(raw):
    return normalize(re.sub(r"<[^>]+>", " ", raw or ""))


def contains(haystack_low, term):
    """한글은 부분 문자열, 영문은 단어 경계로 확인한다(영문 약어가 다른
    단어 안에 우연히 들어가는 오탐 방지)."""
    if re.search(r"[가-힣]", term):
        return term in haystack_low
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", haystack_low) is not None


def classify(title, kind):
    """(포함 여부, 제외 사유)를 반환한다."""
    low = normalize(title).lower()
    for term in HARD_EXCLUDE_TERMS:
        if contains(low, term):
            return False, f"하드 제외({term})"

    equipment_hit = next((t for t in EQUIPMENT_INCLUDE_TERMS if contains(low, t)), None)
    if equipment_hit:
        # 계측/검사 단어 하나만 걸린 경우는 맥락을 한 번 더 본다
        if equipment_hit in METROLOGY_ONLY_TERMS and not any(contains(low, c) for c in CONTEXT_TERMS):
            return False, "계측/검사 용어만 있고 반도체·디스플레이 맥락 없음"
        return True, None

    if any(contains(low, t) for t in SERVICE_EXCLUDE_TERMS):
        return False, "서비스성 공고(장비 신호 없음)"
    return False, "장비 신호 없음"


def match_categories(text):
    low = normalize(text).lower()
    cats = []
    if any(contains(low, t) for t in ["디스플레이", "display", "oled", "microled", "마이크로led", "lcd", "패널", "panel"]):
        cats.append("디스플레이 장비")
    if any(contains(low, t) for t in ["tgv", "유리기판", "glass", "글라스"] + [t.lower() for t in TGV_STRONG_TERMS]):
        cats.append("TGV 장비")
    if not cats or any(contains(low, t) for t in ["반도체", "웨이퍼", "wafer", "클린룸", "cleanroom", "식각", "etch", "증착", "cvd", "pvd", "ald", "cmp", "노광", "lithography"]):
        if "반도체 장비" not in cats:
            cats.insert(0, "반도체 장비")
    return cats


DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_date(text):
    m = DATE_RE.search(text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse_list(html):
    """목록 표에서 (pbancNo, 구분, 제목, 상태, 개시일, 마감일)을 뽑는다."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 6:
            continue
        # 상세는 <a href>가 아니라 버튼의 data-key-no 값으로 열린다
        # (view.do?pbancNo={data-key-no} 형태). href만 찾으면 0건이 된다.
        link = re.search(r'data-key-no="(\d+)"', tr) or re.search(r"pbancNo=(\d+)", tr)
        if not link:
            continue
        rows.append({
            "no": link.group(1),
            "kind": strip_tags(cells[1]),
            "title": strip_tags(cells[2]),
            "status": strip_tags(cells[3]),
            "startDate": parse_date(strip_tags(cells[4])),
            "dueDate": parse_date(strip_tags(cells[5])),
        })
    return rows


def parse_detail(html):
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    cells = [strip_tags(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", t, re.S)]
    cells = [c for c in cells if c]
    fields = {}
    for i in range(len(cells) - 1):
        if cells[i] in ("구분", "진행상태", "공고명", "입찰개시일", "입찰마감일", "공고내용", "나라장터 상세링크"):
            fields[cells[i]] = cells[i + 1]
    attachments = []
    for m in re.finditer(r'href="([^"]*(?:fileDown|download)[^"]*)"[^>]*>(.*?)</a>', html, re.S | re.I):
        name = strip_tags(m.group(2))
        if name:
            url = m.group(1)
            attachments.append({"name": name, "url": url if url.startswith("http") else BASE_URL + url})
    return fields, attachments


def build_item(row, fields, attachments, detail_url):
    title = fields.get("공고명") or row["title"]
    content = fields.get("공고내용") or ""
    categories = match_categories(title + " " + content)
    notice_type = "정식입찰"
    if "사전규격" in title:
        notice_type = "사전규격"
    return {
        "id": f"dgist{row['no']}",
        "title": title,
        "org": "대구경북과학기술원(DGIST)",
        "country": "국내",
        "countryCode": "KR",
        "region": "대구",
        "status": fields.get("진행상태") or row.get("status"),
        "dueDate": parse_date(fields.get("입찰마감일") or "") or row.get("dueDate"),
        "postedDate": parse_date(fields.get("입찰개시일") or "") or row.get("startDate"),
        "keywords": categories,
        "classificationStatus": None if categories else "미분류/검토 필요",
        "budget": None,
        "contractMethod": fields.get("구분") or row.get("kind"),
        "deliveryCondition": None,
        "paymentCondition": None,
        "eligibility": None,
        "description": content[:1200] or None,
        "attachments": attachments,
        "url": detail_url,
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "sourceSiteUrl": SOURCE_SITE_URL,
        "noticeType": notice_type,
    }


# 목록을 실제로 읽고 파싱했는지 기록한다. "정상 수집 + 조건에 맞는
# 공고 0건"을 수집 실패로 오인하지 않기 위한 신호다(common.FetchState).
FETCH_STATE = FetchState("DGIST")


def collect():
    FETCH_STATE.reset()
    raw_rows = []
    for page in range(1, MAX_LIST_PAGES + 1):
        try:
            html = fetch(LIST_URL_TMPL.format(page=page))
        except RuntimeError as exc:
            print(f"[DGIST] 목록 {page}페이지 요청 실패, 여기서 중단: {exc}")
            break
        rows = FETCH_STATE.mark(parse_list(FETCH_STATE.mark_page(html)),
                                structure_ok=looks_like_empty_board(html))
        if not rows:
            break
        raw_rows.extend(rows)
        time.sleep(PAGE_DELAY_SECONDS)

    print(f"[DGIST] 조회 대상(raw): {len(raw_rows)}건")

    included, excluded = [], {}
    for row in raw_rows:
        ok, reason = classify(row["title"], row.get("kind"))
        if ok:
            included.append(row)
        else:
            excluded[reason] = excluded.get(reason, 0) + 1
    for reason, count in excluded.items():
        print(f"[DGIST] {reason}: {count}건")

    items = []
    for row in included:
        detail_url = DETAIL_URL_TMPL.format(no=row["no"])
        try:
            html = fetch(detail_url)
            fields, attachments = parse_detail(html)
        except RuntimeError as exc:
            print(f"[DGIST] 상세 요청 실패(목록 정보만으로 구성): {exc}")
            fields, attachments = {}, []
        items.append(build_item(row, fields, attachments, detail_url))
        time.sleep(PAGE_DELAY_SECONDS)

    print(f"[DGIST] 최종 포함: {len(items)}건")
    return items
