"""
수집원 장애/복구를 Telegram으로 알린다 (신규 공고 알림과는 별개 기능).

왜 필요한가: 수집기 하나가 실패해도 워크플로는 성공으로 끝나고, 화면에는
그 출처의 이전 수집분이 그대로 남는다. Actions 로그와 화면 배너에는
표시되지만 운영자가 매일 들여다보지 않으면 장애를 놓친다.

동작 규칙 (중복 알림 방지가 핵심):
  - 연속 실패가 ALERT_THRESHOLD(3)회 이상이 되면 **최초 1회만** 장애 알림
  - 그 뒤로 4회, 5회 계속 실패해도 다시 보내지 않는다
  - 정상 수집으로 돌아오면 복구 알림을 1회 보내고 상태를 초기화한다
  - 초기화 후 다시 3회 연속 실패하면 새 장애 알림을 보낸다

상태 저장: data/announcements.json 의 sourceHealth[코드].failureAlertSent
(별도 저장소를 두지 않는다 — 이 파일이 실행 간 유일한 상태 저장소다).
이 스크립트가 플래그를 갱신해 파일에 다시 쓰면, 워크플로의 커밋 스텝이
그대로 저장한다.

사용법:
  python scripts/notify_source_health.py data/announcements.json

환경변수(Repository Secret, GitHub Actions에서만 주입):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
둘 중 하나라도 없으면 아무것도 보내지 않고 조용히 종료한다(플래그도
바꾸지 않는다 — 나중에 연동됐을 때 첫 알림을 놓치지 않기 위함).

--dry-run 을 주면 Telegram으로 보내지 않고 보낼 내용만 출력한다(테스트용).
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notify_telegram import send_telegram  # 발송 로직은 기존 것을 그대로 재사용
from collectors.common import SOURCES

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ALERT_THRESHOLD = 3          # 연속 실패 몇 회부터 알릴지
REQUEST_DELAY_SECONDS = 0.5

SOURCE_DISPLAY_NAMES = {s["code"]: s["name"] for s in SOURCES}


def display_name(code):
    """화면·알림에 쓰는 표기(기관명 (국가))를 common.SOURCES에서 가져온다."""
    return SOURCE_DISPLAY_NAMES.get(code, code)


def format_time(iso_text):
    if not iso_text:
        return "기록 없음"
    return iso_text.replace("T", " ")[:16]


def format_failure_message(code, health):
    lines = [
        "[장비 프로젝트 레이더 수집 장애]",
        f"출처: {display_name(code)}",
        f"상태: 연속 {health.get('consecutiveFailures', 0)}회 수집 실패",
        f"마지막 정상 수집: {format_time(health.get('lastSuccessAt'))}",
        "현재 데이터: 기존 수집 데이터 유지 중",
    ]
    if health.get("lastError"):
        lines.append(f"오류: {str(health['lastError'])[:120]}")
    lines.append("확인이 필요합니다.")
    return "\n".join(lines)


def format_recovery_message(code, health):
    return "\n".join([
        "[장비 프로젝트 레이더 수집 복구]",
        f"출처: {display_name(code)}",
        "상태: 정상 수집 복구",
        f"이번 수집: {health.get('collectedThisRun', 0)}건",
        f"복구 시각: {format_time(health.get('lastRunAt'))}",
    ])


def decide_actions(source_health):
    """보낼 알림을 정한다. (코드, 종류, 메시지) 목록을 돌려준다.
    실제 발송·플래그 갱신은 호출한 쪽에서 한다."""
    actions = []
    for code, health in source_health.items():
        if not isinstance(health, dict):
            continue
        already_alerted = bool(health.get("failureAlertSent"))
        failures = health.get("consecutiveFailures", 0) or 0

        if health.get("ok"):
            # 정상 복귀 — 장애 알림을 보냈던 출처만 복구를 알린다
            if already_alerted:
                actions.append((code, "recovery", format_recovery_message(code, health)))
            continue

        if failures >= ALERT_THRESHOLD and not already_alerted:
            actions.append((code, "failure", format_failure_message(code, health)))
    return actions


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/notify_source_health.py <announcements.json 경로> [--dry-run]")
        raise SystemExit(1)

    path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"데이터 파일을 읽지 못해 장애 알림을 건너뜁니다: {exc}")
        return

    source_health = data.get("sourceHealth") or {}
    if not source_health:
        print("sourceHealth가 없어 장애 알림을 건너뜁니다.")
        return

    actions = decide_actions(source_health)
    if not actions:
        print("보낼 장애/복구 알림이 없습니다(임계값 미만이거나 이미 알린 장애).")
        return

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if dry_run:
        for code, kind, message in actions:
            print(f"--- [dry-run] {code} ({kind}) ---")
            print(message)
        return

    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 없어 장애 알림을 건너뜁니다"
              "(플래그는 바꾸지 않아 다음 실행에서 다시 시도합니다).")
        return

    sent = failed = 0
    for code, kind, message in actions:
        if send_telegram(bot_token, chat_id, message):
            sent += 1
            # 발송에 성공했을 때만 상태를 바꾼다 — 실패했는데 보낸 것으로
            # 처리하면 그 장애를 영영 못 알리게 된다.
            source_health[code]["failureAlertSent"] = (kind == "failure")
            print(f"[{code}] {'장애' if kind == 'failure' else '복구'} 알림 발송")
        else:
            failed += 1
            print(f"[{code}] 알림 발송 실패 — 다음 실행에서 다시 시도합니다")
        time.sleep(REQUEST_DELAY_SECONDS)

    if sent:
        data["sourceHealth"] = source_health
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"수집 장애/복구 알림: 성공 {sent}건, 실패 {failed}건")


if __name__ == "__main__":
    main()
