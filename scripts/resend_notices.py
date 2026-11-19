"""
지정한 공고의 알림을 다시 보낸다(수동 전용).

왜 필요한가 — 신규 공고 알림은 한 번에 20건까지만 나간다. 수집이 오래
멈췄다가 재개되면 그보다 많은 신규 공고가 한꺼번에 잡히는데, 넘친 공고는
데이터에는 들어가도 알림 없이 지나가고 다음 실행에서는 더 이상 신규가
아니다. 2026-11-19에 37건 중 17건이 이렇게 빠졌다.

데이터를 바꾸지 않고 메시지만 보낸다. 보낼 공고는 id로 정확히 지정한다.

사용법:
  NOTICE_IDS="id1,id2" python scripts/resend_notices.py [--dry-run]
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notify_telegram import format_message, send_telegram, REQUEST_DELAY_SECONDS

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "data", "announcements.json")


def parse_ids(raw):
    """쉼표로 나눈 id 목록. 빈 값과 중복은 버리고 순서는 지킨다."""
    seen, out = set(), []
    for part in (raw or "").split(","):
        value = part.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def select_items(items, ids):
    """(보낼 공고 목록, 데이터에 없는 id 목록). 요청한 순서를 지킨다."""
    by_id = {i.get("id"): i for i in items}
    found = [by_id[i] for i in ids if i in by_id]
    missing = [i for i in ids if i not in by_id]
    return found, missing


def main():
    ids = parse_ids(os.environ.get("NOTICE_IDS", ""))
    if not ids:
        print("NOTICE_IDS가 비어 있어 보낼 것이 없습니다.")
        return

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        items = json.load(f).get("items", [])
    found, missing = select_items(items, ids)
    if missing:
        print(f"데이터에 없는 id {len(missing)}건은 건너뜁니다: {missing}")

    if "--dry-run" in sys.argv:
        for item in found:
            print(f"--- [dry-run] {item.get('id')} ---")
            print(format_message(item))
        return

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 없어 보내지 못했습니다.")
        raise SystemExit(1)

    sent = failed = 0
    for item in found:
        if send_telegram(bot_token, chat_id, format_message(item)):
            sent += 1
        else:
            failed += 1
            print(f"발송 실패: {item.get('id')}")
        time.sleep(REQUEST_DELAY_SECONDS)
    print(f"재발송 완료: 성공 {sent}건, 실패 {failed}건 (요청 {len(ids)}건)")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
