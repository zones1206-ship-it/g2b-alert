"""
검증을 통과한 번역 결과를 원문 기준으로 기억해 두는 저장소.

왜 필요한가 (2026-09-03 운영에서 실측):
  Argos(오프라인 번역기)는 같은 원문을 넣어도 실행마다 다른 결과를 낸다.
  실제로 JETRO의 "Dry Etching System 2 sets"가 커밋 이력에서
  "건식 식각 장비 2식" ↔ "팝업레이어 알림 2식"(완전 오역) 사이를 오갔다.
  검증 규칙(숫자·약어·길이)은 둘 다 통과하기 때문에 검증만으로는 못 막는다.

그래서 원문 문자열을 고정 식별값으로 삼아, 한 번 검증을 통과한 한국어
제목을 여기에 적어두고 다음 실행부터는 그걸 그대로 쓴다. 새 번역 결과가
이미 검증된 제목을 임의로 덮어쓰지 못한다.

저장 위치: data/translation_memory.json (저장소에 커밋한다 — 실행 간
상태를 남길 곳이 이 저장소밖에 없다). 모델 파일과 달리 수 KB짜리
텍스트라 커밋해도 부담이 없다.

번역을 새로 하고 싶으면(용어집을 고쳤을 때 등) 해당 항목을 이 파일에서
지우면 다음 실행에 다시 번역한다.
"""

import json
import os

_MEMORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "translation_memory.json",
)

_memory = None      # {"en_ko": {원문: 한국어}, ...}
_dirty = False


def _load():
    global _memory
    if _memory is not None:
        return _memory
    try:
        with open(_MEMORY_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        _memory = loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        # 파일이 없거나 깨졌으면 빈 상태로 시작한다 — 번역 자체는 계속 된다.
        _memory = {}
    return _memory


def lookup(namespace, original):
    """검증을 통과한 적이 있는 번역이면 그 한국어 제목을, 없으면 None."""
    if not original:
        return None
    value = _load().get(namespace, {}).get(original)
    return value or None


def remember(namespace, original, korean):
    """검증을 통과한 번역만 넣는다. 이미 있으면 덮어쓰지 않는다."""
    global _dirty
    if not original or not korean:
        return
    bucket = _load().setdefault(namespace, {})
    if bucket.get(original) == korean:
        return
    if original in bucket:
        return  # 기존 검증 제목을 새 번역이 덮어쓰지 못하게 한다
    bucket[original] = korean
    _dirty = True


def save():
    """바뀐 내용이 있을 때만 파일에 쓴다. 실패해도 수집을 죽이지 않는다."""
    global _dirty
    if not _dirty or _memory is None:
        return False
    try:
        os.makedirs(os.path.dirname(_MEMORY_PATH), exist_ok=True)
        with open(_MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(_memory, f, ensure_ascii=False, indent=2, sort_keys=True)
        _dirty = False
        return True
    except OSError as exc:  # noqa: BLE001
        print(f"번역 기억 파일을 저장하지 못했습니다(무시하고 계속): {exc}")
        return False


def stats():
    mem = _load()
    return {ns: len(items) for ns, items in mem.items() if isinstance(items, dict)}
