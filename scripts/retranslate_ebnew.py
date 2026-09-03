"""
이미 저장된 EBNEW 공고의 **한국어 표시 필드만** 새 번역 규칙으로 다시 계산한다.

바꾸는 필드는 이 넷뿐이다:
  title / translatedTitle / org / translationIncomplete

id, originalTitle, url, originalUrl, org, originalOrg, 게시일, 마감일,
projectNo 등 나머지는 절대 건드리지 않는다. 신규 공고 판정은 id 기준이라
(scripts/notify_telegram.py 참고) 제목이 바뀌어도 Telegram 재발송은 없다.

사용:
    python scripts/retranslate_ebnew.py            # 무엇이 바뀌는지만 출력
    python scripts/retranslate_ebnew.py --apply    # 실제로 저장
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from collectors import zh_ko_argos, zh_translate  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "announcements.json"
MUTABLE_FIELDS = ("title", "translatedTitle", "org", "translationIncomplete")


def main():
    apply_changes = "--apply" in sys.argv

    ready, reason = zh_ko_argos.argos_status()
    print(f"zh→en→ko 모델: {'사용 가능' if ready else '사용 불가 — ' + reason}")

    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    targets = [i for i in payload["items"] if i.get("sourceCode") == "EBNEW"]
    print(f"EBNEW 저장 공고: {len(targets)}건\n")

    changed = 0
    engines = {}
    reasons = {}
    for item in targets:
        original = item.get("originalTitle")
        if not original:
            continue
        before_title = item.get("title")
        before_org = item.get("org")
        title, title_ok, info = zh_ko_argos.translate_title(original)

        # 발주기관도 수집기와 같은 함수를 쓴다(제목과 표기를 통일하기 위해).
        original_org = item.get("originalOrg")
        if original_org:
            org, org_ok = zh_ko_argos.translate_org(original_org)
        else:
            org, org_ok = None, True
        org = org or "확인 필요"

        # translationIncomplete 판정 방식은 수집기(ebnew.build_item)와 똑같이
        # 맞춘다. 제목만 보고 플래그를 지우면 다음 수집 때 다시 켜져서
        # "번역 미완료" 배지가 매일 깜빡인다.
        _, summary_ok = zh_translate.translate(item.get("originalSummary") or "")
        ok = title_ok and org_ok and summary_ok

        engines[info["engine"]] = engines.get(info["engine"], 0) + 1
        if info["engine"] == "glossary" and info["reason"]:
            reasons[info["reason"]] = reasons.get(info["reason"], 0) + 1

        if (title == before_title and org == before_org
                and item.get("translationIncomplete") == (not ok)):
            continue
        changed += 1
        print(f"- {original}")
        if title != before_title:
            print(f"    제목 이전: {before_title}")
            print(f"    제목 이후: {title}")
        if org != before_org:
            print(f"    기관 이전: {before_org}")
            print(f"    기관 이후: {org}")
        item["title"] = title
        item["translatedTitle"] = title
        item["org"] = org
        item["translationIncomplete"] = not ok

    print(f"\n번역 경로: " + ", ".join(f"{k} {v}건" for k, v in sorted(engines.items())))
    for r, c in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  기존 번역 유지 사유: {r} ({c}건)")
    print(f"표시가 바뀌는 공고: {changed}건 / {len(targets)}건")

    if not apply_changes:
        print("\n(미리보기입니다. 실제로 저장하려면 --apply 를 붙여 다시 실행하세요.)")
        return

    # 기존 파일과 같은 형식(indent=2, 끝에 개행 없음)으로 써야 데이터 전체가
    # 바뀐 것처럼 보이는 diff가 나지 않는다(fetch_announcements.py와 동일).
    DATA_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{DATA_PATH} 에 저장했습니다(한국어 표시 {len(MUTABLE_FIELDS)}개 필드만 변경).")


if __name__ == "__main__":
    main()
