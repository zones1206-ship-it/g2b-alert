"""
정기 실행 자체가 실패했을 때 Telegram으로 알린다.

왜 필요한가 — 2026-11-04부터 16일 동안 정기 실행이 매일 회귀테스트
단계에서 실패했는데 아무도 몰랐다. 기존 장애 알림(notify_source_health)은
수집원별 실패만 다루고 워크플로의 뒤쪽 단계에서 돈다. 실행이 그 앞에서
멈추면 알림 단계까지 가지 못하므로, 가장 크게 고장 난 날에 가장 조용했다.

언제 보내는가(워크플로의 if 조건이 판단한다):
  - 정기 실행에서 어느 단계든 실패했을 때만 보낸다.
  - 손으로 돌린 검증 실행의 실패는 보내지 않는다(돌린 사람이 바로 본다).

실패가 이어지면 매일 한 통씩 간다. 중복을 막을 상태를 저장하지 않는 것은
의도다 — 실패한 실행은 커밋을 못 하므로 상태를 남길 곳이 없고, 하루 한
통은 "아직 안 고쳐졌다"는 신호로 적당하다.

사용법:
  python scripts/notify_workflow_failure.py [--dry-run]

환경변수:
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  (기존 Repository Secret)
  GITHUB_SERVER_URL / GITHUB_REPOSITORY / GITHUB_RUN_ID  (Actions가 넣어 준다)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notify_telegram import send_telegram  # 발송 로직은 기존 것을 그대로 재사용

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def run_url():
    """이번 실행의 로그 주소. 정보가 모자라면 빈 문자열."""
    server = os.environ.get("GITHUB_SERVER_URL", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    if not (server and repo and run_id):
        return ""
    return f"{server}/{repo}/actions/runs/{run_id}"


def build_message():
    lines = [
        "[장비 프로젝트 레이더 실행 실패]",
        "오늘 정기 실행이 중간에 멈췄습니다.",
        "신규 공고 수집과 알림이 이루어지지 않았습니다.",
        "화면에는 이전 수집 데이터가 그대로 표시됩니다.",
    ]
    url = run_url()
    if url:
        lines.append(url)
    return "\n".join(lines)


def main():
    message = build_message()
    if "--dry-run" in sys.argv:
        print("--- [dry-run] 실행 실패 알림 ---")
        print(message)
        return

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 없어 실행 실패 알림을 건너뜁니다.")
        return

    if send_telegram(bot_token, chat_id, message):
        print("실행 실패 알림 발송 완료(1건).")
    else:
        print("실행 실패 알림 발송 실패.")


if __name__ == "__main__":
    main()
