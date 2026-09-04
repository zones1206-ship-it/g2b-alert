"""
매일 아침 정기 실행의 **맨 마지막**에 사이트 주소를 한 번 보낸다.

왜 별도 스크립트인가 — 공고 알림 메시지마다 링크를 붙이면 공고가 열 건일
때 링크도 열 번 나간다. 사용자가 원한 것은 "아침에 사이트로 바로 들어갈
수 있는 링크 하나"이므로, 신규 공고 수와 무관하게 실행당 1건만 보낸다.

언제 보내는가:
  - 07:00 KST 정기 실행에서만 보낸다(워크플로의 if 조건이 판단한다).
  - 신규 공고가 0건이어도 보낸다. 장애/복구 알림이 없어도 보낸다.
  - 손으로 돌린 검증 실행에서는 보내지 않는다.

발송 정책은 기존 알림과 같다 — 토큰이 없으면 조용히 넘어가고, 발송에
실패해도 0으로 끝난다. 링크 한 통 때문에 그날 수집 결과를 잃으면 안 된다.

사용법:
  python scripts/notify_site_link.py [--dry-run]

환경변수(기존 Repository Secret을 그대로 쓴다. 새 Secret은 없다):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from notify_telegram import send_telegram  # 발송 로직은 기존 것을 그대로 재사용

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SITE_URL = "https://zones1206-ship-it.github.io/g2b-alert/"

# 설명이나 공고 요약은 넣지 않는다 — 링크로 바로 들어가라는 메시지다.
MESSAGE = "\n".join([
    "장비 프로젝트 레이더",
    "전체 공고 확인",
    SITE_URL,
])


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("--- [dry-run] 사이트 링크 ---")
        print(MESSAGE)
        return

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 없어 사이트 링크를 건너뜁니다.")
        return

    if send_telegram(bot_token, chat_id, MESSAGE):
        print("사이트 링크 알림 발송 완료(1건).")
    else:
        # 링크 한 통을 못 보냈다고 워크플로를 실패시키지 않는다. 그날 수집
        # 결과는 이미 만들어졌고, 다음 스텝이 그것을 저장해야 한다.
        print("사이트 링크 알림 발송 실패 — 수집 결과에는 영향이 없습니다.")


if __name__ == "__main__":
    main()
