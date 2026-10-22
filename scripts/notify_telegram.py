"""
data/announcements.json이 갱신될 때, 이전 스냅샷과 비교해 새로 추가된
공고만 텔레그램으로 알린다.

중요: 이 스크립트는 검색/필터/UI(app.js, index.html, style.css) 로직과
완전히 분리돼 있다 — scripts/fetch_announcements.py가 데이터 수집을
마치고 data/announcements.json을 다 쓴 뒤, GitHub Actions 워크플로에서
별도 스텝으로 한 번 실행된다. app.js는 이 스크립트의 존재를 모르고,
이 스크립트도 app.js의 필터 로직을 전혀 참조하지 않는다.

"신규"의 기준은 공고의 id(기존 스키마에 이미 있는 소스별 고유 id)가
이전 스냅샷에 없던 경우다 — 마감/제목 변경 등으로 내용이 바뀐 기존
공고는 신규로 취급하지 않는다.

사용법:
  python scripts/notify_telegram.py <이전 스냅샷 json 경로> <최신 json 경로>

환경변수(Repository Secret, GitHub Actions에서만 주입):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
둘 중 하나라도 없으면 아무것도 보내지 않고 조용히 종료한다(로컬 테스트나
텔레그램 연동이 아직 없는 환경에서 이 스크립트 때문에 파이프라인이
실패하지 않게 하기 위함).
"""

import json
import os
from datetime import date, datetime
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

MAX_MESSAGES_PER_RUN = 20  # 한 번에 너무 많이 보내는 것 방지(연동 첫날 등 예외 상황 대비)
REQUEST_DELAY_SECONDS = 0.5


def load_items(path):
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("items", [])
    except (json.JSONDecodeError, OSError):
        return []


def send_telegram(token, chat_id, text):
    """성공하면 True, 실패하면 False를 반환한다. 실패 시에도 토큰/전체 응답은
    출력하지 않고 HTTP 상태코드와 Telegram description만 출력한다."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.load(res)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", "ignore"))
            description = body.get("description", "(설명 없음)")
        except Exception:
            description = "(응답 본문을 읽을 수 없음)"
        print(f"[sendMessage] 실패 — HTTP {exc.code} — {description}")
        return False
    except urllib.error.URLError:
        print("[sendMessage] 실패 — 네트워크 오류(Telegram API에 접속할 수 없음)")
        return False

    if not data.get("ok"):
        print("[sendMessage] Telegram이 실패 응답을 반환했습니다.")
        return False
    return True


SITE_URL = "https://zones1206-ship-it.github.io/g2b-alert/"


def notice_link(item):
    """그 공고를 펼친 채로 레이더를 여는 주소. id가 없으면 첫 화면으로."""
    notice_id = item.get("id")
    if not notice_id:
        return SITE_URL
    return SITE_URL + "#n=" + urllib.parse.quote(str(notice_id), safe="")


def _days_until(due):
    """오늘부터 마감까지 남은 날. 날짜 형식이 이상하면 None(app.js daysUntil)."""
    if not due:
        return None
    try:
        return (datetime.strptime(due, "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return None


def _dday_label(due):
    """화면의 D-day 배지와 같은 문구(app.js ddayBadge)."""
    left = _days_until(due)
    if left is None:
        return "마감일 확인 필요"
    if left < 0:
        return "마감"
    return "오늘 마감" if left == 0 else f"D-{left}"


def _display_status(item):
    """마감일이 지났으면 '마감'으로 본다(app.js displayStatus).

    원문에서 가져온 status는 수집 시점 값이라 마감일이 지나도 '진행중'으로
    남아 있다.
    """
    left = _days_until(item.get("dueDate"))
    if left is not None and left < 0:
        return "마감"
    return item.get("status")


def _rows(pairs):
    """값이 있는 줄만 남긴다(app.js detailRow)."""
    return [f"· {label}: {value}" for label, value in pairs if value]


def _section(title, pairs):
    """한 구획. 담을 줄이 없으면 제목도 넣지 않는다."""
    body = _rows(pairs)
    return ["", title] + body if body else []


def format_message(item):
    """공고 하나를 상세 화면과 같은 항목·순서·라벨로 적는다.

    화면에서 보던 것과 다른 내용이 알림으로 오면 같은 공고인지 헷갈린다.
    그래서 app.js의 renderCard가 그리는 구획을 그대로 따라간다 —
    기본 정보 / 일정 정보 / 공고 정보 / 핵심 요약.
    """
    lines = ["📢 신규 공고", ""]
    lines.append(item.get("title") or "(제목 없음)")
    lines.append("")

    if item.get("org"):
        lines.append("🏛 " + item["org"])
    due = item.get("dueDate")
    lines.append(f"📅 마감일 {due or '확인 필요'}  ·  {_dday_label(due)}")

    blocks = [
        _section("▬ 기본 정보", [
            ("산업", item.get("industry")),
            ("공정", item.get("process")),
            ("장비명", item.get("equipmentName")),
            ("국가", item.get("country")),
            ("지역", item.get("region")),
            ("출처", item.get("source")),
            ("발주기관", item.get("org")),
            ("분야", ", ".join(item.get("keywords") or [])),
            ("정보 유형", item.get("noticeType")),
        ]),
        _section("▬ 일정 정보", [
            ("등록일", item.get("postedDate") or "확인 필요"),
            ("마감일", due or "마감일 확인 필요"),
            ("이행기한 / 납기", item.get("deliveryCondition")),
            ("행사 기간", item.get("eventPeriod")),
            ("상태", _display_status(item)),
        ]),
        _section("▬ 공고 정보", [
            ("공고번호", item.get("projectNo") or item.get("g2bBidNo")),
            ("수량", item.get("quantity")),
            ("예산", item.get("budget") or "예산 정보 없음"),
            ("계약방식", item.get("contractMethod")),
            ("지급조건", item.get("paymentCondition")),
            ("자격조건", item.get("eligibility")),
        ]),
    ]

    summary = (item.get("description") or "").strip() or "상세 설명이 제공되지 않았습니다."
    if len(summary) > 400:
        summary = summary[:400].rstrip() + "…"
    blocks.append(["", "▬ 핵심 요약", summary])

    for block in blocks:
        lines.extend(block)

    lines.append("")
    lines.append("🔗 레이더에서 보기")
    lines.append(notice_link(item))
    return "\n".join(lines)


def announcement_signature(item):
    """같은 공고인지 판단하는 지문(scripts/fetch_announcements.py와 같은 기준)."""
    return (
        item.get("sourceCode"),
        re.sub(r"\s+", " ", (item.get("originalTitle") or item.get("title") or "")).strip(),
        re.sub(r"\s+", " ", (item.get("originalOrg") or item.get("org") or "")).strip(),
        item.get("postedDate"),
        item.get("dueDate"),
        item.get("noticeType"),
    )


def project_key(item):
    """출처 + 공고번호(scripts/fetch_announcements.py와 같은 기준).

    signature가 같아도 공고번호가 다르면 별개 공고다. 실측에서 MOFCOM
    4197-264BOECDCZ02 로트 /02 두 건이 새로 올라왔는데, 같은 프로젝트
    로트 /03 과 제목·기관·게시일·마감일이 모두 같아 "재색인"으로 오판돼
    **신규 공고 알림이 나가지 않았다**.
    """
    project_no = item.get("projectNo") or item.get("g2bBidNo")
    if not project_no:
        return None
    return (item.get("sourceCode"),
            re.sub(r"\s+", "", str(project_no)).strip().lower())


def main():
    if len(sys.argv) != 3:
        print("사용법: python scripts/notify_telegram.py <이전 json> <최신 json>")
        raise SystemExit(1)

    before_path, after_path = sys.argv[1], sys.argv[2]

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 설정돼 있지 않아 알림을 건너뜁니다.")
        return

    before_items = load_items(before_path)
    before_ids = {item.get("id") for item in before_items if item.get("id")}
    # 사이트가 같은 공고에 새 내부 id를 부여해 재색인하는 경우가 있다
    # (MOFCOM에서 중복 알림 3건이 실제로 발생). id뿐 아니라 "같은 공고 지문"
    # 으로도 확인해 재색인만으로 다시 발송하지 않는다. 마감일·공고유형이
    # 바뀌면 지문이 달라지므로 실제 정정·재공고는 그대로 알린다.
    before_signatures = {announcement_signature(item) for item in before_items}
    before_projects = {p for p in (project_key(item) for item in before_items) if p}
    after_items = load_items(after_path)

    new_items = []
    reindexed = 0
    not_equipment = 0
    for item in after_items:
        if not item.get("id") or item["id"] in before_ids:
            continue
        key = project_key(item)
        if not (key and key not in before_projects):
            # 공고번호가 이전에 없던 것이면 별개 공고이므로 지문 검사를
            # 건너뛴다. 그 외에만 재색인 여부를 지문으로 판단한다.
            if announcement_signature(item) in before_signatures:
                reindexed += 1
                continue
        # 재료·부품·용역·공사처럼 장비가 아닌 공고는 알리지 않는다.
        if item.get("equipmentStatus") not in (None, "장비"):
            not_equipment += 1
            continue
        new_items.append(item)

    if reindexed:
        print(f"사이트 재색인으로 id만 바뀐 공고 {reindexed}건은 알리지 않습니다.")
    if not_equipment:
        print(f"장비 공고가 아니어서 제외한 신규 공고 {not_equipment}건"
              f"(재료/부품/용역/공사/검토 필요).")

    if not new_items:
        print("신규 공고 없음 — 알림을 보내지 않습니다.")
        return

    if len(new_items) > MAX_MESSAGES_PER_RUN:
        print(f"신규 공고 {len(new_items)}건 중 상위 {MAX_MESSAGES_PER_RUN}건만 전송합니다"
              f"(1회 발송량 제한).")
        new_items = new_items[:MAX_MESSAGES_PER_RUN]

    sent = 0
    failed = 0
    for item in new_items:
        if send_telegram(bot_token, chat_id, format_message(item)):
            sent += 1
        else:
            failed += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"신규 공고 알림 전송 완료: 성공 {sent}건, 실패 {failed}건")


if __name__ == "__main__":
    main()
