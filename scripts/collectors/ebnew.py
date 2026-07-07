"""
중국 비롄왕(必联网/EBNEW) 입찰/구매 공고 수집기.

공식 API/RSS 없음(사전 조사 결과). 로그인 없이 공개 접근 가능한
검색 결과만 사용하며, 어떤 우회 기법도 쓰지 않는다.

사이트 구조 (2026-07 기준, 실제로 확인함):
- 검색: POST https://ss.ebnew.com/tradingSearch/index.htm
  폼 필드 key(검색어), sortMethod=timeDesc(최신순), currentPage(페이지)
  - 처음엔 GET 파라미터로 추정해 시도했으나 실제 폼은 POST이고 필드명이
    다르다는 것을 실제 폼(id="searchBidProjForm")을 읽어서 확인했다.
    실제 키워드로 검색해 오늘 날짜(2026-07-07) 공고가 정상적으로
    나오는 것까지 확인했다 — 로그인 불필요.
- 상세: https://www.ebnew.com/businessShow/{id}.html (GET, 로그인 불필요)
  프로젝트번호/공고유형/입찰방식/마감일/발주기관/지역/품목 등을 본문에서
  정규식으로 추출한다. 예산 정보는 이 사이트 특성상 대부분 공개되지
  않아(임의 추정 금지) 없으면 None으로 둔다.

번역: 이 환경에는 번역 API가 연결돼 있지 않아 collectors/zh_translate.py의
용어집 기반 치환으로 "최선 노력" 번역을 한다. 원문(originalTitle 등)은
항상 그대로 보존하며, 치환 후에도 한자가 과반 남으면 번역 실패로 보고
원문을 그대로 표시한다(임의로 지어내지 않는다).

분류: 이 사이트는 전 산업을 다루므로 관련성 판단이 중요하다. 검색 자체를
반도체/디스플레이/TGV 관련 키워드로만 하고, 결과 제목에 관련성 낮은
신호(논문/뉴스/일반 소비자가전/IT운영/건축공사/사무용품/소프트웨어/광고/
교육 등)만 있고 강한 산업 신호가 없으면 제외한다.
"""

import re
import time
import html as html_lib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta

from .common import normalize_text
from . import zh_translate

SOURCE_NAME = "중국 비롄왕(EBNEW)"
SOURCE_CODE = "EBNEW"
SOURCE_SITE_URL = "https://www.ebnew.com/"
SOURCE_COUNTRY = "중국"
SOURCE_COUNTRY_CODE = "CN"
SOURCE_TYPE = "China Site"

SEARCH_URL = "https://ss.ebnew.com/tradingSearch/index.htm"
DETAIL_URL_TMPL = "https://www.ebnew.com/businessShow/{id}.html"

# 검색에 사용할 중국어 키워드(반도체/디스플레이/TGV 관련). 사이트 자체 검색이
# 실제로 서버단에서 필터링되는 것을 확인했으므로(나라장터 때와 달리 진짜
# 동작함), 이 키워드들로 각각 검색해 후보를 모은다.
SEARCH_KEYWORDS = [
    "半导体设备", "显示面板设备", "OLED", "玻璃基板", "玻璃通孔",
    "先进封装", "面板级封装", "自动光学检测", "激光钻孔", "湿法刻蚀",
    "电镀铜", "液晶显示设备", "检测设备半导体", "清洗设备半导体",
]

LOOKBACK_DAYS = 14  # 검색 결과가 매우 많아(키워드당 수만 건) 최근 것만 본다
MAX_PAGES_PER_KEYWORD = 2
REQUEST_TIMEOUT = 20
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 4
REQUEST_DELAY_SECONDS = 1.2

# 관련성 낮음(이 신호만 있고 아래 강한 신호가 없으면 제외)
LOW_RELEVANCE_TERMS = [
    "论文", "新闻", "消费电子", "运维", "工程建设", "办公用品", "软件开发",
    "广告", "培训", "教育", "装修", "维修保养", "会议服务", "餐饮",
]

# 하드 제외: 배관/공조/전기/토목/건축/EPC 등 "설비 부대공사"류. 반도체/
# 디스플레이 키워드가 title에 같이 있어도(예: "半导体设备独立基础项目" =
# 반도체 장비동 "기초 공사") 이 신호가 있으면 장비 구매가 아니라 부대
# 공사이므로 무조건 제외한다(강한 산업 신호보다 우선한다).
HARD_EXCLUDE_TERMS = [
    # 배관/유틸리티
    "二次配管", "配管", "管道", "特气", "气体管道", "动力配管", "给排水",
    "暖通", "hvac", "消防",
    # 전기/기계/클린룸 시공
    "机电安装", "电气安装", "洁净室施工", "厂房建设", "土建", "基础施工",
    "独立基础", "钢结构", "装修工程", "安装工程", "工程施工",
    # 총도급/EPC
    "epc", "总承包",
]

# 반도체/디스플레이/TGV 산업 신호(하나는 있어야 포함된다). HARD_EXCLUDE_TERMS가
# 먼저 걸러지므로, 여기 있는 단어가 있으면 배관/건설류가 아닌 이상 장비/생산
# 관련 공고로 본다.
STRONG_RELEVANCE_TERMS = [
    "半导体", "晶圆", "wafer", "刻蚀", "etch", "镀膜", "沉积", "光刻",
    "封装", "packaging", "显示面板", "显示设备", "oled", "lcd", "面板",
    "微型发光二极管", "micro led", "玻璃基板", "玻璃通孔", "tgv",
    "glass substrate", "through glass via", "中介层", "interposer",
    "检测设备", "清洗设备", "自动光学检测", "aoi", "键合机", "刻蚀机",
    "成长炉", "生长炉", "扩产", "产业化基地", "fab",
]

CATEGORY_HINTS = {
    "디스플레이 장비": ["显示", "oled", "lcd", "面板", "micro led", "液晶"],
    "TGV 장비": ["玻璃基板", "玻璃通孔", "tgv", "glass substrate", "through glass via", "中介层", "interposer", "玻璃刻蚀", "电镀铜", "化学镀铜"],
}

TAG_TYPE_MAP = {
    "预告": "사전규격",
    "公告": "정식입찰",
    "变更": "정식입찰",
    "公示": "낙찰·수주결과",
    "结果": "낙찰·수주결과",
}


def fetch(url: str, data: bytes = None) -> str:
    req = urllib.request.Request(
        url, data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; g2b-alert-bot/1.0)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST" if data is not None else "GET",
    )
    last_error = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as res:
                return res.read().decode("utf-8", "ignore")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < MAX_RETRY_ATTEMPTS:
                print(f"[EBNEW] 요청 실패({exc}), {RETRY_DELAY_SECONDS}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"EBNEW 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def strip_tags(raw_html: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", raw_html, flags=re.S)  # HTML 주석(내부에 '>' 있어도 통째로 제거)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


FIELD_PATTERN = re.compile(
    r'<span class="item-name">(?P<label>[^<]+)：</span>\s*'
    r'<span class="item-value"[^>]*>(?P<value>[^<]*)</span>',
)


def parse_search_results(raw_html: str):
    """검색 결과 HTML을 abstract-box 블록 단위로 나눠 각 블록에서
    태그/제목/URL/필드(항목명:값)를 추출한다."""
    blocks = raw_html.split('class="abstract-box')[1:]
    rows = []
    for block in blocks:
        tag_m = re.search(r'<i class="fl tag-\w+[^"]*">([^<]*)</i>', block)
        link_m = re.search(r'<a class="[^"]*abstract-title[^"]*"[^>]*href="([^"]+)"\s+title="([^"]*)"', block)
        date_m = re.search(r"发布日期[:：]\s*(\d{4}-\d{2}-\d{2})", block)
        if not link_m:
            continue
        fields = {m.group("label").strip(): m.group("value").strip() for m in FIELD_PATTERN.finditer(block)}
        rows.append({
            "tag": tag_m.group(1).strip() if tag_m else None,
            "url": link_m.group(1),
            "title": html_lib.unescape(link_m.group(2)),
            "date": date_m.group(1) if date_m else None,
            "fields": fields,
        })
    return rows


def is_relevant(text: str):
    """2단계 판정: ① 배관/공조/전기/토목/EPC 등 부대공사 신호가 있으면
    반도체/디스플레이 단어가 같이 있어도 무조건 제외한다(예:
    "半导体设备独立基础项目" = 반도체 장비동 "기초 공사"이지 장비 구매가
    아님 — 실제로 이런 오탐이 있었다). ② 산업 신호(STRONG_RELEVANCE_TERMS)
    가 있어야 포함한다.

    처음에는 "장비 구매 문맥(EQUIPMENT_CONTEXT_TERMS)까지 같이 있어야
    포함"하는 더 엄격한 AND 조건도 시도했으나, "OLED 생산라인", "면板
    자동광학검사 및 관련 설비 업그레이드"처럼 명시적으로 "设备采购"라고
    쓰지 않는 정당한 장비/생산라인 공고까지 대거 제외되는 것을 테스트로
    확인해 되돌렸다. 배관/건설 신호는 하드 제외로 충분히 걸러진다."""
    t = normalize_text(text)

    if any(normalize_text(term) in t for term in HARD_EXCLUDE_TERMS):
        return False

    has_strong = any(normalize_text(term) in t for term in STRONG_RELEVANCE_TERMS)
    if not has_strong:
        return False

    has_low = any(normalize_text(term) in t for term in LOW_RELEVANCE_TERMS)
    return not has_low


def match_categories(text: str):
    t = normalize_text(text)
    matched = [cat for cat, terms in CATEGORY_HINTS.items() if any(normalize_text(term) in t for term in terms)]
    return matched or ["반도체 장비"]


def notice_type(tag: str):
    if not tag:
        return "정식입찰"
    return TAG_TYPE_MAP.get(tag.strip(), "정식입찰")


def extract_budget(detail_text: str):
    m = re.search(r"(?:采购预算|项目预算|预算金额)[：:]\s*([\d,.]+)\s*(万元|元|美元|USD)?", detail_text)
    if not m:
        return None, None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None, None
    if amount <= 0:
        return None, None
    unit = m.group(2) or "元"
    currency = "CNY" if unit in ("万元", "元") else "USD"
    if unit == "万元":
        amount *= 10000
    return f"{amount:,.0f}{unit}" if currency == "CNY" else f"${amount:,.0f}", currency


def extract_field(detail_text: str, label: str, max_len: int = 60):
    """"라벨：값" 형태에서 값을 뽑는다. 이 사이트 상세페이지는 항목 사이에
    구분자(세미콜론 등)가 없어서, 값이 끝나고 다음 "한글아님 2~10자 라벨："
    패턴이 시작되기 직전까지만(lookahead) 잘라내 다음 항목이 섞여
    들어오는 것을 막는다."""
    m = re.search(
        re.escape(label) + r"[：:]\s*(.{1,%d}?)(?=\s*[一-鿿]{2,10}[：:]|$)" % max_len,
        detail_text,
    )
    if not m:
        return None
    value = m.group(1).strip()
    return value or None


def build_item(row: dict):
    original_title = row["title"]
    translated_title, title_ok = zh_translate.translate(original_title)

    try:
        detail_html = fetch(row["url"])
    except RuntimeError as exc:
        print(f"[EBNEW] 상세 페이지 요청 실패(건너뜀): {exc}")
        return None

    detail_text = strip_tags(detail_html)

    deadline_m = re.search(r"截止时间[：:]\s*(\d{4}-\d{2}-\d{2})", detail_text)
    deadline = deadline_m.group(1) if deadline_m else None

    org = extract_field(detail_text, "招标人") or extract_field(detail_text, "招标机构") or row["fields"].get("发布企业")
    region = extract_field(detail_text, "招标地区") or row["fields"].get("项目地区") or row["fields"].get("招标地区")
    product = extract_field(detail_text, "招标产品") or row["fields"].get("招标产品")
    project_no = extract_field(detail_text, "项目编号")

    budget, currency = extract_budget(detail_text)

    summary_source = product or original_title
    translated_summary, summary_ok = zh_translate.translate(summary_source) if summary_source else (None, False)
    translated_org, _ = zh_translate.translate(org) if org else (None, False)
    translated_region = zh_translate.translate_region(region) if region else None

    combined_relevance_text = " ".join(filter(None, [original_title, product]))

    return {
        "id": f"ebnew{re.search(r'(\d+)', row['url']).group(1)}",
        "title": translated_title,
        "translatedTitle": translated_title,
        "originalTitle": original_title,
        "translatedSummary": translated_summary,
        "originalSummary": summary_source,
        "org": translated_org or org or "확인 필요",
        "country": SOURCE_COUNTRY,
        "countryCode": SOURCE_COUNTRY_CODE,
        "region": translated_region,
        "status": "진행중",
        "dueDate": deadline,
        "postedDate": row["date"],
        "keywords": match_categories(combined_relevance_text),
        "budget": budget,
        "currency": currency,
        "contractMethod": None,
        "deliveryCondition": None,
        "paymentCondition": None,
        "eligibility": None,
        "description": translated_summary or (translated_title if title_ok else original_title),
        "attachments": [],
        "url": row["url"],
        "originalUrl": row["url"],
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "sourceSiteUrl": SOURCE_SITE_URL,
        "sourceCountry": SOURCE_COUNTRY_CODE,
        "sourceType": SOURCE_TYPE,
        "detectedLanguage": "zh-CN",
        "noticeType": notice_type(row.get("tag")),
        "projectNo": project_no,
    }


def collect():
    """EBNEW 검색 결과에서 반도체/디스플레이/TGV 관련 공고만 수집한다."""
    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date().isoformat()

    items = []
    seen_ids = set()
    seen_title_date = set()  # 같은 공고가 검색어마다 다른 내부 ID로 잡히는 경우의 중복 제거용
    stats = {"raw": 0, "not_relevant": 0, "duplicate": 0, "included": 0, "translate_failed": 0}

    for keyword in SEARCH_KEYWORDS:
        for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
            body = f"key={urllib.parse.quote(keyword)}&sortMethod=timeDesc&currentPage={page}"
            print(f"[EBNEW] '{keyword}' 페이지 {page}/{MAX_PAGES_PER_KEYWORD} 검색 중...")
            try:
                html = fetch(SEARCH_URL, data=body.encode("utf-8"))
            except RuntimeError as exc:
                print(f"[EBNEW] '{keyword}' 검색 실패, 다음 키워드로 넘어감: {exc}")
                break

            rows = parse_search_results(html)
            if not rows:
                break

            stop_keyword = False
            for row in rows:
                if row["date"] and row["date"] < cutoff:
                    stop_keyword = True
                    break

                item_id_m = re.search(r"(\d+)", row["url"])
                if not item_id_m:
                    continue
                raw_id = item_id_m.group(1)
                if raw_id in seen_ids:
                    continue

                # 제목+발행일이 같으면 사이트 내부적으로 재색인된 동일 공고로 보고
                # 건너뛴다(검색어별로 같은 공고가 다른 ID로 잡히는 경우가 실제로 있었음).
                dedup_key = (normalize_text(row["title"]), row["date"])
                if dedup_key in seen_title_date:
                    seen_ids.add(raw_id)
                    stats["duplicate"] += 1
                    continue

                stats["raw"] += 1
                if not is_relevant(row["title"]):
                    stats["not_relevant"] += 1
                    continue

                seen_ids.add(raw_id)
                seen_title_date.add(dedup_key)
                item = build_item(row)
                if item is None:
                    continue
                if item["translatedTitle"] == item["originalTitle"]:
                    stats["translate_failed"] += 1
                items.append(item)
                stats["included"] += 1
                time.sleep(REQUEST_DELAY_SECONDS)

            if stop_keyword:
                break
            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"[EBNEW] 조회 대상(raw): {stats['raw']}건")
    print(f"[EBNEW] 같은 공고 재색인으로 중복 제거: {stats['duplicate']}건")
    print(f"[EBNEW] 관련성 낮아 제외: {stats['not_relevant']}건")
    print(f"[EBNEW] 최종 포함: {stats['included']}건 (번역 실패/원문 유지 {stats['translate_failed']}건)")

    return items


if __name__ == "__main__":
    result = collect()
    print(f"\n=== 테스트 결과: 총 {len(result)}건 수집 ===")
    for item in result[:8]:
        print(f"- [{item['noticeType']}] {item['title']} | 원문: {item['originalTitle']} | 마감:{item['dueDate']} | {item['keywords']}")
