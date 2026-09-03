"""
JETRO 제목 번역에 쓰는 en→ko Argos 모델을 준비한다 (Actions 전용 보조 스크립트).

캐시가 살아 있으면 이미 설치돼 있으므로 아무것도 하지 않고 끝난다.
모델이 없을 때만 내려받아 설치한다.

중요: 이 스크립트가 실패해도 수집 파이프라인을 죽이지 않는다(항상 0으로 종료).
모델이 없으면 수집기가 기존 용어집 방식으로 자동 폴백하도록 만들어 두었기
때문에, 번역 때문에 그날 공고 수집 전체를 잃는 일은 없어야 한다.
"""

import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

FROM_CODE, TO_CODE = "en", "ko"


def main():
    try:
        import argostranslate.package as pkg
        import argostranslate.translate as tr
    except ImportError as exc:
        print(f"argostranslate를 불러오지 못했습니다(용어집 방식으로 폴백): {exc}")
        return

    # 이미 설치돼 있는지(=캐시 적중) 먼저 확인한다.
    try:
        probe = tr.translate("semiconductor equipment", FROM_CODE, TO_CODE)
        if probe and any("가" <= ch <= "힣" for ch in probe):
            print(f"en→ko 모델이 이미 설치돼 있습니다(캐시 적중). 확인 결과: {probe}")
            return
    except Exception:
        pass  # 미설치 상태 — 아래에서 설치한다

    try:
        print("en→ko 모델이 없어 새로 내려받습니다...")
        pkg.update_package_index()
        available = pkg.get_available_packages()
        target = next((p for p in available
                       if p.from_code == FROM_CODE and p.to_code == TO_CODE), None)
        if target is None:
            print("en→ko 패키지를 패키지 인덱스에서 찾지 못했습니다(용어집 방식으로 폴백).")
            return
        path = target.download()
        pkg.install_from_path(path)
        print("en→ko 모델 설치 완료")
    except Exception as exc:  # noqa: BLE001
        print(f"모델 설치 실패(용어집 방식으로 폴백): {type(exc).__name__}: {str(exc)[:150]}")


if __name__ == "__main__":
    main()
    # 어떤 경우에도 워크플로를 실패시키지 않는다.
    sys.exit(0)
