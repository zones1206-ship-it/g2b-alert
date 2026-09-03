"""
한국과학기술원(KAIST) 입찰/구매 공고 수집기.

실제 페이지 구조 (2026-09 기준, 직접 확인해 작성):
- 목록: https://www.kaist.ac.kr/kr/html/footer/0815.html  (공개, 로그인 없음)
  표 헤더: 번호 | 구분 | 공고명 | 게시일시 | 입찰개시일시 | 입찰마감일시
  구분 값: 공사 / 물품 / 용역
  각 행의 제목/구분 링크가 **나라장터 상세 페이지로 바로 연결**된다:
    https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R26BK01708895&bidPbancOrd=000
  → 별도 상세 페이지가 없으므로 목록에서 모든 필드를 얻고, 원문 링크는
    나라장터 링크를 그대로 쓴다. bidPbancNo는 기존 스키마의 g2bBidNo에 담는다.

접근성 참고: KAIST **홈페이지**(www.kaist.ac.kr/)는 GitHub Actions 러너에서
timeout이 나지만, 이 입찰 게시판 경로는 러너에서 20초 간격 3회 모두 정상
응답(HTTP 200)하는 것을 확인했다. 그래서 홈페이지가 아니라 게시판 URL만
직접 요청한다.

수집 대상은 반도체/디스플레이/TGV 및 관련 공정장비 공고로 한정한다.
KAIST는 종합 연구기관이라 공사/일반 용역/전산장비 공고가 훨씬 많으므로
KANC·DGIST와 같은 보수적 판정(장비 신호가 있어야 포함)을 쓴다.
"""

import re
import time
import html as html_lib
import urllib.error
import urllib.request

from .common import TGV_STRONG_TERMS

SOURCE_NAME = "KAIST (한국)"
SOURCE_CODE = "KAIST"
SOURCE_SITE_URL = "https://www.kaist.ac.kr/kr/html/footer/0815.html"

LIST_URL = SOURCE_SITE_URL

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
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

HARD_EXCLUDE_TERMS = ["취소", "매각", "유찰", "재입찰 안내"]

# 장비 신호(사용자가 지정한 수집 대상). DGIST 수집기와 같은 기준을 쓴다.
EQUIPMENT_INCLUDE_TERMS = [
    "반도체", "웨이퍼", "wafer", "클린룸", "cleanroom", "fab", "팹",
    "패키징", "packaging", "본딩", "bonding", "본더", "bonder",
    "디스플레이", "display", "oled", "마이크로led", "microled", "lcd", "패널", "panel",
    "tgv", "유리기판", "글라스", "glass",
    "증착", "pvd", "cvd", "pecvd", "ald", "스퍼터", "sputter", "sputtering", "evaporation",
    "식각", "etch", "etching", "rie", "icp", "drie", "세정", "cleaning",
    "웨트벤치", "wet bench", "플라즈마", "plasma",
    "도금", "plating", "ecd", "시드층",
    "cmp", "연마", "polishing", "어닐링", "annealing", "열처리로", "furnace", "rtp",
    "노광", "리소그래피", "lithography", "스테퍼", "stepper", "포토레지스트", "photoresist",
    "계측", "metrology", "엘립소미터", "ellipsometer", "타원편광기",
    "프로파일로미터", "profilometer", "박막 두께", "박막두께", "film thickness",
]
EQUIPMENT_INCLUDE_TERMS += [t.lower() for t in TGV_STRONG_TERMS]

METROLOGY_ONLY_TERMS = [
    "계측", "metrology", "검사", "inspection", "sem", "tem", "현미경",
    "엘립소미터", "ellipsometer", "타원편광기", "프로파일로미터", "profilometer",
    "박막 두께", "박막두께", "두께 측정", "film thickness",
]
CONTEXT_TERMS = [
    "반도체", "웨이퍼", "wafer", "디스플레이", "display", "oled", "패널", "panel",
    "유리기판", "glass", "tgv", "클린룸", "cleanroom", "공정",
]

SERVICE_EXCLUDE_TERMS = [
    "공사", "용역", "위탁", "교육", "행사", "홍보", "컨설팅", "운영", "관리",
    "청소", "경비", "차량", "급식", "보험", "임차", "인쇄", "설계",
    "리모델링", "수선", "조경", "네트워크", "소프트웨어", "라이선스",
    "클라우드", "서버", "노트북", "컴퓨터", "프린터", "가구", "도서",
    "gpgpu", "gpu", "충전소", "아파트",
]


def fetch(url):
    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
                return res.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < MAX_RETRY_ATTEMPTS:
                delay = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                print(f"[KAIST] 요청 실패({exc}), {delay}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(delay)
    raise RuntimeError(f"KAIST 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def normalize(text):
    return re.sub(r"\s+", " ", html_lib.unescape(text or "")).strip()


def strip_tags(raw):
    return normalize(re.sub(r"<[^>]+>", " ", raw or ""))


def contains(haystack_low, term):
    if re.search(r"[가-힣]", term):
        return term in haystack_low
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", haystack_low) is not None


def classify(title, kind):
    low = normalize(title).lower()
    for term in HARD_EXCLUDE_TERMS:
        if contains(low, term):
            return False, f"하드 제외({term})"
    if kind == "공사":
        return False, "공사 공고"

    hit = next((t for t in EQUIPMENT_INCLUDE_TERMS if contains(low, t)), None)
    if hit:
        if hit in METROLOGY_ONLY_TERMS and not any(contains(low, c) for c in CONTEXT_TERMS):
            return False, "계측/검사 용어만 있고 반도체·디스플레이 맥락 없음"
        return True, None

    if any(contains(low, t) for t in SERVICE_EXCLUDE_TERMS):
        return False, "서비스성/비대상 공고"
    return False, "장비 신호 없음"


def match_categories(text):
    low = normalize(text).lower()
    cats = []
    if any(contains(low, t) for t in ["디스플레이", "display", "oled", "microled", "마이크로led", "lcd", "패널", "panel"]):
        cats.append("디스플레이 장비")
    if any(contains(low, t) for t in ["tgv", "유리기판", "glass", "글라스"] + [t.lower() for t in TGV_STRONG_TERMS]):
        cats.append("TGV 장비")
    if not cats or any(contains(low, t) for t in ["반도체", "웨이퍼", "wafer", "클린룸", "식각", "etch", "증착", "cvd", "pvd", "ald", "cmp", "노광", "lithography"]):
        if "반도체 장비" not in cats:
            cats.insert(0, "반도체 장비")
    return cats


DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_date(text):
    m = DATE_RE.search(text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def parse_list(html):
    """목록 표에서 각 행을 뽑는다. 상세 링크는 나라장터 URL이며 거기에
    포함된 bidPbancNo를 공고번호로 쓴다."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 6:
            continue
        no = strip_tags(cells[0])
        if not no.isdigit():
            continue
        link = re.search(r'href="(https://www\.g2b\.go\.kr/[^"]+)"', tr)
        bid_no = re.search(r"bidPbancNo=([A-Za-z0-9]+)", tr)
        rows.append({
            "no": no,
            "kind": strip_tags(cells[1]),
            "title": strip_tags(cells[2]),
            "postedDate": parse_date(strip_tags(cells[3])),
            "startDate": parse_date(strip_tags(cells[4])),
            "dueDate": parse_date(strip_tags(cells[5])),
            "url": html_lib.unescape(link.group(1)) if link else LIST_URL,
            "g2bBidNo": bid_no.group(1) if bid_no else None,
        })
    return rows


def build_item(row):
    categories = match_categories(row["title"])
    notice_type = "사전규격" if "사전규격" in row["title"] else "정식입찰"
    return {
        "id": f"kaist{row['g2bBidNo'] or row['no']}",
        "title": row["title"],
        "org": "한국과학기술원(KAIST)",
        "country": "국내",
        "countryCode": "KR",
        "region": "대전",
        "status": None,
        "dueDate": row.get("dueDate"),
        "postedDate": row.get("postedDate"),
        "keywords": categories,
        "classificationStatus": None if categories else "미분류/검토 필요",
        "budget": None,
        "contractMethod": row.get("kind"),
        "deliveryCondition": None,
        "paymentCondition": None,
        "eligibility": None,
        "description": None,
        "attachments": [],
        "url": row["url"],
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "sourceSiteUrl": SOURCE_SITE_URL,
        "noticeType": notice_type,
        "g2bBidNo": row.get("g2bBidNo"),
    }


def collect():
    html = fetch(LIST_URL)
    rows = parse_list(html)
    print(f"[KAIST] 조회 대상(raw): {len(rows)}건")

    included, excluded = [], {}
    for row in rows:
        ok, reason = classify(row["title"], row.get("kind"))
        if ok:
            included.append(row)
        else:
            excluded[reason] = excluded.get(reason, 0) + 1
    for reason, count in sorted(excluded.items(), key=lambda kv: -kv[1]):
        print(f"[KAIST] {reason}: {count}건")

    items = [build_item(r) for r in included]
    print(f"[KAIST] 최종 포함: {len(items)}건")
    return items
