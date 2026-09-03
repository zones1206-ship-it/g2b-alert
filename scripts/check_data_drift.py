"""수집 결과가 이전 상태에서 비정상적으로 벗어났는지 검사한다.

수집 직후 · Telegram 알림 직전에 돌린다. 여기서 실패하면 알림도 커밋도
하지 않는다 — 깨진 데이터로 45건을 "신규 공고"라며 한꺼번에 보내는 것이
그날 갱신을 건너뛰는 것보다 훨씬 나쁘기 때문이다.

정상적인 변동(공고 몇 건 추가/마감, 한 수집원의 일시적 장애)은 통과시키고,
사람이 봐야 하는 수준의 이상만 잡는다:

  1. 파일이 비었거나 JSON으로 읽히지 않는다
  2. 전체 건수가 절반 미만으로 줄었다
  3. 모든 수집원이 동시에 실패했다
  4. 장비 판정 건수가 절반 미만으로 줄었다
  5. firstSeenAt이 사라진 기존 공고가 있다 (신규로 오인되어 재발송된다)

사용법:
    python scripts/check_data_drift.py data/announcements.before.json data/announcements.json
"""

import io
import json
import sys

# Windows 콘솔(cp949)에서 한글·em dash가 깨지지 않게 한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def load(path):
    raw = io.open(path, encoding="utf-8").read()
    if not raw.strip():
        raise ValueError(f"{path} 가 비어 있습니다")
    data = json.loads(raw)
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError(f"{path} 에 items가 없습니다")
    return data


def main(before_path, after_path):
    problems = []

    try:
        after = load(after_path)
    except Exception as exc:                                  # noqa: BLE001
        print(f"[DRIFT] 수집 결과를 읽을 수 없습니다: {exc}")
        return 1

    try:
        before = load(before_path)
    except Exception as exc:                                  # noqa: BLE001
        # 최초 실행 등 이전 상태가 없으면 비교는 건너뛰되 결과 자체는 본다.
        print(f"[DRIFT] 이전 상태 없음({exc}) — 비교 검사는 건너뜁니다")
        before = None

    items = after["items"]
    health = after.get("sourceHealth") or {}

    print(f"[DRIFT] 현재 {len(items)}건 / 수집원 {len(health)}개")

    if health and not any(v.get("ok") for v in health.values()):
        problems.append("모든 수집원이 동시에 실패했습니다 "
                        "(네트워크 또는 실행 환경 문제일 가능성이 높습니다)")

    if before is not None:
        old_items = before["items"]
        print(f"[DRIFT] 이전 {len(old_items)}건 → 현재 {len(items)}건")

        if old_items and len(items) * 2 < len(old_items):
            problems.append(f"전체 건수가 {len(old_items)}건에서 {len(items)}건으로 "
                            f"절반 미만으로 줄었습니다")

        def equip(rows):
            return sum(1 for i in rows if i.get("equipmentStatus") == "장비")

        old_eq, new_eq = equip(old_items), equip(items)
        print(f"[DRIFT] 장비 판정 {old_eq}건 → {new_eq}건")
        if old_eq and new_eq * 2 < old_eq:
            problems.append(f"장비 판정이 {old_eq}건에서 {new_eq}건으로 "
                            f"절반 미만으로 줄었습니다")

        # firstSeenAt이 사라지면 기존 공고가 신규로 오인되어 재발송된다.
        old_seen = {i.get("id"): i.get("firstSeenAt") for i in old_items}
        lost = [i.get("id") for i in items
                if old_seen.get(i.get("id")) and not i.get("firstSeenAt")]
        if lost:
            problems.append(f"기존 공고 {len(lost)}건의 firstSeenAt이 사라졌습니다 "
                            f"(예: {lost[:3]}) — 신규로 오인되어 재발송됩니다")

    if problems:
        print("\n[DRIFT] 비정상 변동을 발견해 알림·커밋을 중단합니다:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("[DRIFT] 이상 없음")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
