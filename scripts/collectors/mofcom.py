"""
중국국제초표망(中国国际招标网, chinabidding.mofcom.gov.cn) 입찰 공고 수집기.
중국 상무부(商务部)가 운영하는 기전제품(机电产品) 국제입찰 행정감독/공공서비스
플랫폼이다.

사이트 구조 (2026-07 기준, 실제로 확인함):
- 주의: 도메인은 "www." 없이 https://chinabidding.mofcom.gov.cn 이다.
  (www.chinabidding.mofcom.gov.cn 은 DNS 자체가 해석되지 않아 접속 불가 —
  실제로 확인함. 반드시 www 없는 도메인을 써야 한다.)
- 검색 결과는 홈페이지의 <form action="/channel/business/bulletinList.shtml">
  GET 폼처럼 보이지만, 실제 목록은 그 뒤에 JS가 비동기로 그리는 것이다.
  실제 데이터를 주는 엔드포인트는 페이지 소스의 $.ajax 호출에서 찾았다:
    POST /zbwcms/front/bidding/bulletinInfoList
    파라미터: pageNumber, keyWord, timeType, rangeCode, typeCode,
              capitalSourceCode, industryCode, provinceCode
    응답: JSON {maxPageNum, pageNumber, pageSize, total,
                rows: [{name, digest, filePath, publishTime, createTime,
                        industryName, areaName, capitalSourceName, fdid}]}
  이걸 실제 키워드(OLED 등)로 호출해 진짜 결과가 나오는 것까지 확인했다
  (예: "第六代柔性有源矩阵有机发光显示器件（AMOLED）生产线升级项目").
  "半导体"/"晶圆"/"面板" 등 일부 한자 키워드는 현재 0건이었고, 로마자
  키워드("OLED")로는 결과가 있었다 — 이 사이트 검색이 한자 키워드 매칭에
  약한 것으로 보이나(원인 불명, 임의로 추정하지 않는다), 실제로 결과가
  나오는 키워드 위주로 SEARCH_KEYWORDS를 구성했다.
- 상세 페이지: https://chinabidding.mofcom.gov.cn/bidDetail{filePath}
  (filePath는 검색 결과 JSON의 "filePath" 필드, 이미 "/bidding/bulletin/..."
  형태— 앞에 "/bidDetail"을 붙여야 실제 200이 나온다. filePath를 그대로
  경로로 쓰면 404다 — 실제로 확인함.)
  본문에 "招标人:"/"项目实施地点:"/"投标截止时间（开标时间）:"/
  "招标项目编号:" 같은 라벨:값 형식으로 정보가 있다.

번역/관련성 판정: EBNEW 수집기(ebnew.py)와 동일한 방식을 그대로 재사용한다
(용어집 기반 최선노력 번역은 zh_translate, 배관/건설/EPC 등 부대공사 하드
제외 + 반도체/디스플레이/TGV 산업 신호 판정은 ebnew.is_relevant를 그대로
가져다 쓴다 — 두 사이트 모두 전 산업을 다루는 사이트라 같은 오탐 패턴이
나타날 수 있어서다).
"""

import json
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta

from .common import normalize_text
from . import zh_translate
from .ebnew import is_relevant_list_stage, is_equipment_purchase, match_categories

SOURCE_NAME = "중국국제초표망(MOFCOM)"
SOURCE_CODE = "MOFCOM"
SOURCE_SITE_URL = "https://chinabidding.mofcom.gov.cn/"
SOURCE_COUNTRY = "중국"
SOURCE_COUNTRY_CODE = "CN"
SOURCE_TYPE = "China Site"

SEARCH_URL = "https://chinabidding.mofcom.gov.cn/zbwcms/front/bidding/bulletinInfoList"
DETAIL_URL_TMPL = "https://chinabidding.mofcom.gov.cn/bidDetail{file_path}"

# 실제로 결과가 나오는 것을 확인한 키워드 위주(반도체/디스플레이/TGV 관련).
# "半导体"/"晶圆"/"面板"/"集成电路"/"刻蚀机"/"光刻机" 등 한자 키워드는
# 이 사이트 검색에서 0건이었다(실제로 테스트함, 임의 판단 아님) — 이유는
# 불명이나(색인 갱신 지연 등으로 추정되나 확인 불가), 로마자/영문 키워드는
# 결과가 있어 이것 위주로 구성한다. 향후 재조사 시 한자 키워드도 다시
# 테스트해볼 것.
SEARCH_KEYWORDS = [
    "OLED", "AMOLED", "TFT-LCD", "TGV",
]

LOOKBACK_DAYS = 30
MAX_PAGES_PER_KEYWORD = 3
REQUEST_TIMEOUT = 20
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 4
REQUEST_DELAY_SECONDS = 1.2


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
                print(f"[MOFCOM] 요청 실패({exc}), {RETRY_DELAY_SECONDS}초 후 재시도 {attempt}/{MAX_RETRY_ATTEMPTS - 1}")
                time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"MOFCOM 요청이 {MAX_RETRY_ATTEMPTS}회 실패했습니다: {last_error}")


def strip_tags(raw_html: str) -> str:
    import html as html_lib
    text = re.sub(r"<!--.*?-->", " ", raw_html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_field(detail_text: str, label: str, max_len: int = 80):
    m = re.search(
        re.escape(label) + r"[：:]\s*(.{1,%d}?)(?=\s*[一-鿿]{2,10}[：:]|$)" % max_len,
        detail_text,
    )
    if not m:
        return None
    value = m.group(1).strip()
    return value or None


def extract_deadline(detail_text: str):
    m = re.search(r"投标截止时间（开标时间）[：:]\s*(\d{4}-\d{2}-\d{2})", detail_text)
    return m.group(1) if m else None


def build_item(row: dict):
    original_title = row["name"]
    translated_title, title_ok = zh_translate.translate(original_title)

    file_path = row["filePath"]
    detail_url = DETAIL_URL_TMPL.format(file_path=file_path)

    try:
        detail_html = fetch(detail_url)
    except RuntimeError as exc:
        print(f"[MOFCOM] 상세 페이지 요청 실패(건너뜀): {exc}")
        return None

    detail_text = strip_tags(detail_html)

    deadline = extract_deadline(detail_text)
    org = extract_field(detail_text, "招标人") or row.get("industryName")
    region = extract_field(detail_text, "项目实施地点") or row.get("areaName")
    project_no = extract_field(detail_text, "招标项目编号")

    digest = row.get("digest") or ""
    translated_summary, summary_ok = zh_translate.translate(digest) if digest else (None, False)
    translated_org, _ = zh_translate.translate(org) if org else (None, False)
    translated_region = zh_translate.translate_region(region) if region else None

    # 3차(실제 장비구매 성격) 판정은 목록 단계 제목/요약이 아니라 상세
    # 페이지 본문("招标产品列表(主要设备)" 등)까지 포함해서 봐야 한다 —
    # 목록 단계 digest만으로는 이 사이트 특성상 대부분 걸러져버린다
    # (실제로 title+digest만으로 테스트했더니 85건 중 0건만 남는 것을 확인).
    combined_relevance_text = " ".join(filter(None, [original_title, digest, detail_text]))
    if not is_equipment_purchase(combined_relevance_text):
        return None

    categories = match_categories(combined_relevance_text)

    return {
        "id": f"mofcom{row['fdid']}",
        "title": translated_title,
        "translatedTitle": translated_title,
        "originalTitle": original_title,
        "translatedSummary": translated_summary,
        "originalSummary": digest or None,
        "org": translated_org or org or "확인 필요",
        "country": SOURCE_COUNTRY,
        "countryCode": SOURCE_COUNTRY_CODE,
        "region": translated_region,
        "status": "진행중",
        "dueDate": deadline,
        "postedDate": row.get("publishTime") or row.get("createTime"),
        "keywords": categories,
        "classificationStatus": "확정" if categories else "미분류/검토 필요",
        "budget": None,
        "currency": None,
        "contractMethod": None,
        "deliveryCondition": None,
        "paymentCondition": None,
        "eligibility": None,
        "description": translated_summary or (translated_title if title_ok else original_title),
        "attachments": [],
        "url": detail_url,
        "originalUrl": detail_url,
        "source": SOURCE_NAME,
        "sourceCode": SOURCE_CODE,
        "sourceSiteUrl": SOURCE_SITE_URL,
        "sourceCountry": SOURCE_COUNTRY_CODE,
        "sourceType": SOURCE_TYPE,
        "detectedLanguage": "zh-CN",
        "noticeType": "정식입찰",
        "projectNo": project_no,
    }


def collect():
    """MOFCOM(중국국제초표망) 검색 결과에서 반도체/디스플레이/TGV 관련
    공고만 수집한다."""
    cutoff = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date().isoformat()

    items = []
    seen_ids = set()
    seen_title_date = set()
    stats = {"raw": 0, "not_relevant": 0, "duplicate": 0, "included": 0, "translate_failed": 0, "excluded_after_detail": 0}

    for keyword in SEARCH_KEYWORDS:
        for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
            body = urllib.parse.urlencode({
                "pageNumber": page,
                "keyWord": keyword,
                "timeType": "",
                "rangeCode": "",
                "typeCode": "",
                "capitalSourceCode": "",
                "industryCode": "",
                "provinceCode": "",
            })
            print(f"[MOFCOM] '{keyword}' 페이지 {page}/{MAX_PAGES_PER_KEYWORD} 검색 중...")
            try:
                raw = fetch(SEARCH_URL, data=body.encode("utf-8"))
                payload = json.loads(raw)
            except (RuntimeError, json.JSONDecodeError) as exc:
                print(f"[MOFCOM] '{keyword}' 검색 실패, 다음 키워드로 넘어감: {exc}")
                break

            rows = payload.get("rows") or []
            if not rows:
                break

            stop_keyword = False
            for row in rows:
                posted = row.get("publishTime") or row.get("createTime") or ""
                posted_date = posted[:10] if posted else None
                if posted_date and posted_date < cutoff:
                    stop_keyword = True
                    break

                fdid = row.get("fdid")
                if not fdid or fdid in seen_ids:
                    continue

                title = row.get("name") or ""
                dedup_key = (normalize_text(title), posted_date)
                if dedup_key in seen_title_date:
                    seen_ids.add(fdid)
                    stats["duplicate"] += 1
                    continue

                stats["raw"] += 1
                combined = f"{title} {row.get('digest') or ''}"
                if not is_relevant_list_stage(combined):
                    stats["not_relevant"] += 1
                    continue

                seen_ids.add(fdid)
                seen_title_date.add(dedup_key)
                row["publishTime"] = posted_date
                item = build_item(row)
                if item is None:
                    stats["excluded_after_detail"] += 1
                    continue
                if item["translatedTitle"] == item["originalTitle"]:
                    stats["translate_failed"] += 1
                items.append(item)
                stats["included"] += 1
                time.sleep(REQUEST_DELAY_SECONDS)

            if stop_keyword:
                break
            if page >= payload.get("maxPageNum", 0):
                break
            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"[MOFCOM] 조회 대상(raw): {stats['raw']}건")
    print(f"[MOFCOM] 같은 공고 재색인으로 중복 제거: {stats['duplicate']}건")
    print(f"[MOFCOM] 관련성 낮아 제외(1차/2차, 제목 기준): {stats['not_relevant']}건")
    print(f"[MOFCOM] 상세 확인 후 제외(3차 장비구매 성격 미확인/요청실패): {stats['excluded_after_detail']}건")
    print(f"[MOFCOM] 최종 포함: {stats['included']}건 (번역 실패/원문 유지 {stats['translate_failed']}건)")

    return items


if __name__ == "__main__":
    result = collect()
    print(f"\n=== 테스트 결과: 총 {len(result)}건 수집 ===")
    for item in result[:8]:
        print(f"- [{item['noticeType']}] {item['title']} | 원문: {item['originalTitle']} | 마감:{item['dueDate']} | {item['keywords']}")
