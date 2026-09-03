"""
KOTRA 수집 장애를 계층별로 진단한다 (로컬과 GitHub Actions에서 같은 코드를 돌려
비교하기 위한 도구). 운영 파이프라인과 무관하며 데이터를 건드리지 않는다.

계층:
  A. DNS        — 도메인이 해석되는가
  B. TCP/TLS    — 443 연결과 TLS 핸드셰이크가 되는가
  C. HTTP       — 상태코드/리다이렉트/응답 크기
  D. 애플리케이션 — 목록 AJAX, 공개 HTML, 상세 페이지

우회 기법은 쓰지 않는다. 공개 URL에 일반적인 브라우저 요청을 보낼 뿐이다.
"""

import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# 조사 대상 — 전부 KOTRA 공식 도메인의 공개 경로다.
HOSTS = ["www.kotra.or.kr", "dream.kotra.or.kr", "kotra.or.kr", "news.kotra.or.kr"]

HTTP_TARGETS = [
    ("현재 사용 중인 목록 AJAX(POST)", "POST",
     "https://www.kotra.or.kr/module/subhome/bizAply/selectBmBizRcritYListNewAjax.do",
     "sch_appl_yn=N&sch_nation_cd=Y&pageNo=1&pageNo2=1&pageNoA=1&startCount=0&listCount=20"),
    ("사업신청 공개 HTML", "GET",
     "https://www.kotra.or.kr/subList/20000020753/subhome/bizAply/bizAplyList.do", None),
    ("KOTRA 메인", "GET", "https://www.kotra.or.kr/index.do", None),
    ("KOTRA 루트", "GET", "https://www.kotra.or.kr/", None),
    ("해외시장뉴스(dream) 메인", "GET", "https://dream.kotra.or.kr/kotranews/index.do", None),
    ("해외시장뉴스 공고/알림", "GET",
     "https://dream.kotra.or.kr/kotranews/cms/news/actionKotraBoardList.do?MENU_ID=520", None),
]


def check_dns():
    print("\n=== A. DNS ===")
    for host in HOSTS:
        t0 = time.time()
        try:
            infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
            ips = sorted({i[4][0] for i in infos})
            print(f"  [OK]   {host:<22} {', '.join(ips)}  ({time.time()-t0:.2f}s)")
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {host:<22} {type(exc).__name__}: {exc}")


def check_tcp_tls():
    print("\n=== B. TCP 443 / TLS ===")
    for host in HOSTS:
        t0 = time.time()
        try:
            with socket.create_connection((host, 443), timeout=10) as sock:
                tcp = time.time() - t0
                ctx = ssl.create_default_context()
                try:
                    with ctx.wrap_socket(sock, server_hostname=host) as tls:
                        print(f"  [OK]   {host:<22} TCP {tcp:.2f}s / TLS {time.time()-t0-tcp:.2f}s "
                              f"/ {tls.version()}")
                except Exception as exc:  # noqa: BLE001
                    print(f"  [TLS FAIL] {host:<22} TCP {tcp:.2f}s → {type(exc).__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [TCP FAIL] {host:<22} {type(exc).__name__}: {exc}  ({time.time()-t0:.2f}s)")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"REDIRECT → {newurl}", headers, fp)


def check_http():
    print("\n=== C/D. HTTP + 애플리케이션 ===")
    opener = urllib.request.build_opener(NoRedirect)
    for label, method, url, body in HTTP_TARGETS:
        headers = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
        data = None
        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            headers["X-Requested-With"] = "XMLHttpRequest"
            headers["Referer"] = "https://www.kotra.or.kr/"
            data = body.encode()
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with opener.open(req, timeout=20) as res:
                raw = res.read()
                print(f"  [OK]   {label:<28} HTTP {res.status} / {len(raw):,}B / "
                      f"{time.time()-t0:.2f}s / {res.headers.get('Content-Type','?')}")
        except urllib.error.HTTPError as exc:
            print(f"  [HTTP] {label:<28} HTTP {exc.code} {exc.reason} ({time.time()-t0:.2f}s)")
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {label:<28} {type(exc).__name__}: {exc} ({time.time()-t0:.2f}s)")


def check_repeat():
    """항상 실패인지 간헐 성공인지 확인한다(과도한 요청은 하지 않는다: 3회)."""
    print("\n=== 반복 호출 (간헐 여부 확인, 3회 / 10초 간격) ===")
    url = "https://www.kotra.or.kr/"
    for i in range(1, 4):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as res:
                print(f"  {i}회차 [OK] HTTP {res.status} / {len(res.read()):,}B / {time.time()-t0:.2f}s")
        except Exception as exc:  # noqa: BLE001
            print(f"  {i}회차 [FAIL] {type(exc).__name__}: {exc} ({time.time()-t0:.2f}s)")
        if i < 3:
            time.sleep(10)


def main():
    where = "GitHub Actions" if "--actions" in sys.argv else "로컬"
    print(f"KOTRA 계층별 진단 — 실행 위치: {where}")
    check_dns()
    check_tcp_tls()
    check_http()
    check_repeat()
    print("\n진단 종료")


if __name__ == "__main__":
    main()
