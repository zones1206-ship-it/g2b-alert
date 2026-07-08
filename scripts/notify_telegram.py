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
import sys
import time
import urllib.error
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


def format_message(item):
    lines = [f"\U0001F4E2 신규 공고: {item.get('title') or '(제목 없음)'}"]
    if item.get("source"):
        lines.append(f"출처: {item['source']}")
    if item.get("org"):
        lines.append(f"발주기관: {item['org']}")
    if item.get("dueDate"):
        lines.append(f"마감일: {item['dueDate']}")
    keywords = item.get("keywords") or []
    if keywords:
        lines.append(f"분야: {', '.join(keywords)}")
    url = item.get("url")
    if url:
        lines.append(url)
    return "\n".join(lines)


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

    before_ids = {item.get("id") for item in load_items(before_path) if item.get("id")}
    after_items = load_items(after_path)
    new_items = [item for item in after_items if item.get("id") and item["id"] not in before_ids]

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
