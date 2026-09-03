"""
장비 프로젝트 레이더 핵심 규칙 회귀테스트.

지시문 No.001~No.012에서 확정한 규칙들이 나중에 조용히 깨지지 않도록
고정한다. 무거운 것(번역 모델, 실제 네트워크)은 건드리지 않는다 —
전부 표준 unittest + monkeypatch로 몇 초 안에 끝난다.

실행:
    python -m unittest discover -s tests -v
    python tests/test_regression.py          (같은 결과)

여기서 FAIL이 나면 운영 데이터를 커밋하기 전에 반드시 원인을 확인해야 한다.
"""

import http.client
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from collectors import equipment_filter as EF                      # noqa: E402
from collectors import zh_translate as ZT                          # noqa: E402
from collectors import kanc, nnfc, ebnew, mofcom, kriss            # noqa: E402
from collectors import jetro, dgist, itri, kaist, kotra            # noqa: E402
from collectors.common import (FetchState, NETWORK_EXCEPTIONS,     # noqa: E402
                               should_retry, retry_delay,
                               looks_like_empty_board)
import fetch_announcements as FA                                   # noqa: E402
import notify_telegram as NT                                       # noqa: E402
from notify_source_health import decide_actions                    # noqa: E402
import check_data_drift as DRIFT                                   # noqa: E402


# 수집기별 (모듈, fetch 함수명, 최대 시도 횟수)
COLLECTORS = [
    ("KANC", kanc, "fetch_html", 3), ("NNFC", nnfc, "fetch_html", 3),
    ("EBNEW", ebnew, "fetch", 3), ("MOFCOM", mofcom, "fetch", 3),
    ("KRISS", kriss, "fetch_html", 3), ("JETRO", jetro, "fetch", 3),
    ("DGIST", dgist, "fetch", 4), ("ITRI", itri, "fetch", 3),
    ("KAIST", kaist, "fetch", 4), ("KOTRA", kotra, "fetch", 3),
]


class _FakeResponse:
    def __init__(self, body=b"<html>ok</html>"):
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _http_error(code, headers=None):
    return urllib.error.HTTPError(
        "http://example.invalid/x", code, f"HTTP {code}",
        http.client.HTTPMessage() if headers is None else headers, None)


def _with_headers(code, name, value):
    msg = http.client.HTTPMessage()
    msg[name] = value
    return _http_error(code, msg)


class NetworkRetryTest(unittest.TestCase):
    """A. 네트워크 계층 — 어떤 오류를 재시도하고 어떤 것을 즉시 포기하는가."""

    def setUp(self):
        self._urlopen = urllib.request.urlopen
        self._sleep = time.sleep
        time.sleep = lambda _s: None          # 테스트를 빠르게

    def tearDown(self):
        urllib.request.urlopen = self._urlopen
        time.sleep = self._sleep

    def _run(self, mod, attr, script):
        """script를 순서대로 소비하며 fetch를 호출한다. (성공여부, 호출횟수)"""
        calls = {"n": 0}

        def fake(req, timeout=None, context=None):
            i = calls["n"]
            calls["n"] += 1
            outcome = script[min(i, len(script) - 1)]
            if outcome is None:
                return _FakeResponse()
            raise outcome

        urllib.request.urlopen = fake
        fn = getattr(mod, attr)
        try:
            fn("http://example.invalid/x", {}) if attr == "fetch" and mod is jetro \
                else fn("http://example.invalid/x")
            return True, calls["n"]
        except RuntimeError:
            return False, calls["n"]

    def test_remote_disconnected_retries_then_succeeds(self):
        exc = http.client.RemoteDisconnected("Remote end closed connection without response")
        for name, mod, attr, _max in COLLECTORS:
            with self.subTest(source=name):
                ok, calls = self._run(mod, attr, [exc, None])
                self.assertTrue(ok, f"{name}: RemoteDisconnected 후 재시도 성공해야 함")
                self.assertEqual(calls, 2, f"{name}: 정확히 1회 재시도해야 함")

    def test_connection_reset_retries_then_succeeds(self):
        for name, mod, attr, _max in COLLECTORS:
            with self.subTest(source=name):
                ok, calls = self._run(mod, attr, [ConnectionResetError("reset"), None])
                self.assertTrue(ok, f"{name}: ConnectionReset 후 재시도 성공해야 함")
                self.assertEqual(calls, 2)

    def test_timeout_exhausts_retries_and_fails(self):
        for name, mod, attr, max_attempts in COLLECTORS:
            with self.subTest(source=name):
                ok, calls = self._run(mod, attr, [TimeoutError("timed out")] * 8)
                self.assertFalse(ok, f"{name}: 전부 timeout이면 최종 실패해야 함")
                self.assertEqual(calls, max_attempts,
                                 f"{name}: 시도 횟수는 {max_attempts}회로 제한돼야 함(무한 재시도 금지)")

    def test_404_is_not_retried(self):
        for name, mod, attr, _max in COLLECTORS:
            with self.subTest(source=name):
                ok, calls = self._run(mod, attr, [_http_error(404)] * 8)
                self.assertFalse(ok, f"{name}: 404는 최종 실패")
                self.assertEqual(calls, 1, f"{name}: 404는 재시도하지 않아야 함")

    def test_403_is_not_retried(self):
        for name, mod, attr, _max in COLLECTORS:
            with self.subTest(source=name):
                ok, calls = self._run(mod, attr, [_http_error(403)] * 8)
                self.assertFalse(ok)
                self.assertEqual(calls, 1, f"{name}: 403은 기본적으로 재시도하지 않아야 함")

    def test_429_is_retried(self):
        for name, mod, attr, _max in COLLECTORS:
            with self.subTest(source=name):
                ok, calls = self._run(mod, attr, [_http_error(429), None])
                self.assertTrue(ok, f"{name}: 429는 제한 재시도 대상")
                self.assertEqual(calls, 2)

    def test_5xx_is_retried(self):
        for code in (500, 502, 503, 504):
            for name, mod, attr, _max in COLLECTORS:
                with self.subTest(source=name, code=code):
                    ok, calls = self._run(mod, attr, [_http_error(code), None])
                    self.assertTrue(ok, f"{name}: {code}은 제한 재시도 대상")
                    self.assertEqual(calls, 2)

    def test_other_4xx_is_not_retried(self):
        for code in (400, 401, 410, 418):
            for name, mod, attr, _max in COLLECTORS:
                with self.subTest(source=name, code=code):
                    ok, calls = self._run(mod, attr, [_http_error(code)] * 8)
                    self.assertFalse(ok)
                    self.assertEqual(calls, 1, f"{name}: {code}은 재시도 금지")

    def test_parsing_errors_are_not_swallowed_as_network(self):
        """KeyError/TypeError/ValueError는 네트워크 재시도로 숨기면 안 된다."""
        for exc in (KeyError("k"), TypeError("t"), ValueError("v")):
            with self.subTest(exc=type(exc).__name__):
                self.assertNotIsInstance(exc, NETWORK_EXCEPTIONS)

    def test_should_retry_policy_table(self):
        self.assertTrue(should_retry(TimeoutError("t")))
        self.assertTrue(should_retry(ConnectionResetError("r")))
        self.assertTrue(should_retry(http.client.RemoteDisconnected("d")))
        for code in (429, 500, 502, 503, 504):
            self.assertTrue(should_retry(_http_error(code)), code)
        for code in (400, 401, 403, 404, 410):
            self.assertFalse(should_retry(_http_error(code)), code)

    def test_retry_after_is_honoured_and_capped(self):
        base = 3
        # 초 단위 Retry-After는 존중하되 base보다 작으면 base 유지
        self.assertEqual(retry_delay(_with_headers(429, "Retry-After", "10"), base), 10)
        self.assertEqual(retry_delay(_with_headers(429, "Retry-After", "1"), base), base)
        # 과도한 값은 상한으로 자른다(워크플로가 멈추지 않게)
        self.assertEqual(retry_delay(_with_headers(503, "Retry-After", "9999"), base), 30)
        # 헤더가 없거나 해석 불가면 기존 backoff 사용
        self.assertEqual(retry_delay(_http_error(429), base), base)
        self.assertEqual(retry_delay(_with_headers(429, "Retry-After", "not-a-date"), base), base)
        # HTTP 오류가 아니면 그대로
        self.assertEqual(retry_delay(TimeoutError("t"), base), base)


class FetchStateTest(unittest.TestCase):
    """B. FetchState — 정상 0건 / 진짜 빈 게시판 / 장애 구분."""

    def test_normal_with_results(self):
        st = FetchState("T")
        st.mark([{"a": 1}, {"a": 2}])
        self.assertTrue(st.fetched)
        self.assertEqual(st.item_count, 2)

    def test_normal_but_filtered_to_zero(self):
        """목록은 정상, 우리 조건 통과 0건 → 정상."""
        st = FetchState("T")
        st.mark([{"a": 1}])
        st.mark_filtered(0)
        self.assertTrue(st.fetched)
        self.assertEqual(st.filtered_count, 0)

    def test_genuinely_empty_board_is_normal(self):
        """게시판이 진짜 0건(페이지가 그렇게 말함) → 정상."""
        st = FetchState("T")
        st.mark_page("<div>등록된 자료가 없습니다</div>")
        st.mark([], structure_ok=True)
        self.assertTrue(st.fetched)
        self.assertEqual(st.item_count, 0)

    def test_connection_failure_is_outage(self):
        st = FetchState("T")
        self.assertFalse(st.fetched)

    def test_structure_gone_is_parse_outage(self):
        """본문은 받았지만 우리가 아는 구조가 사라짐 → 파싱 장애."""
        st = FetchState("T")
        st.mark_page("<html>완전히 다른 페이지</html>")
        st.mark([], structure_ok=False)
        self.assertTrue(st.network_fetched)
        self.assertFalse(st.parse_succeeded)
        self.assertFalse(st.fetched)

    def test_empty_without_signal_stays_conservative(self):
        st = FetchState("T")
        st.mark([])
        self.assertFalse(st.fetched, "구조 확인 신호가 없으면 정상으로 판정하지 않는다")

    def test_reset_clears_all(self):
        st = FetchState("T")
        st.mark([{"a": 1}])
        st.mark_filtered(5)
        st.reset()
        self.assertFalse(st.fetched)
        self.assertEqual(st.item_count, 0)
        self.assertIsNone(st.filtered_count)

    def test_all_collectors_expose_fetch_state(self):
        for name, mod, _attr, _max in COLLECTORS:
            with self.subTest(source=name):
                self.assertTrue(hasattr(mod, "FETCH_STATE"), f"{name}: FETCH_STATE 필요")
                self.assertEqual(mod.FETCH_STATE.name, name)

    def test_empty_board_markers(self):
        self.assertTrue(looks_like_empty_board("등록된 자료가 없습니다"))
        self.assertTrue(looks_like_empty_board("查無資料"))
        self.assertTrue(looks_like_empty_board("No Data"))
        self.assertFalse(looks_like_empty_board("<table><tr><td>공고</td></tr></table>"))
        self.assertFalse(looks_like_empty_board(""))
        self.assertFalse(looks_like_empty_board(None))


class RunCollectorTest(unittest.TestCase):
    """정상 0건과 장애가 orchestrator까지 올바르게 전달되는지."""

    class _Fake:
        def __init__(self, name, state, mode):
            self.name, self.FETCH_STATE, self.mode = name, state, mode

        def collect(self):
            self.FETCH_STATE.reset()
            if self.mode == "raise":
                raise RuntimeError("연결 실패(모의)")
            if self.mode == "empty_board":
                self.FETCH_STATE.mark_page("등록된 자료가 없습니다")
                self.FETCH_STATE.mark([], structure_ok=True)
                return []
            if self.mode == "broken":
                self.FETCH_STATE.mark_page("<html/>")
                self.FETCH_STATE.mark([], structure_ok=False)
                return []
            self.FETCH_STATE.mark([{"row": 1}])
            if self.mode == "filtered_zero":
                return []
            return [{"id": "X-1", "sourceCode": self.name, "title": "t"}]

    def _run(self, mode, name="KANC"):
        log = {}
        existing = [{"id": f"{name}-old", "sourceCode": name, "title": "old"}]
        fake = self._Fake(name, FetchState(name), mode)
        items = FA.run_collector(name, fake, existing, log)
        health = FA.build_source_health(log, {}, "2026-09-04T00:00:00")
        return log[name], health[name], items

    def test_results_present_is_normal(self):
        log, health, items = self._run("normal")
        self.assertEqual(log["status"], "정상")
        self.assertTrue(health["ok"])
        self.assertEqual(health["consecutiveFailures"], 0)
        self.assertEqual(len(items), 1)

    def test_filtered_zero_is_normal(self):
        log, health, items = self._run("filtered_zero")
        self.assertEqual(log["status"], "정상")
        self.assertTrue(health["ok"])
        self.assertEqual(health["consecutiveFailures"], 0)
        self.assertEqual(items, [])

    def test_genuinely_empty_board_is_normal(self):
        log, health, items = self._run("empty_board")
        self.assertEqual(log["status"], "정상")
        self.assertTrue(health["ok"])
        self.assertEqual(items, [])

    def test_exception_is_outage_and_keeps_old_data(self):
        log, health, items = self._run("raise")
        self.assertEqual(log["status"], "오류")
        self.assertFalse(health["ok"])
        self.assertEqual(health["consecutiveFailures"], 1)
        self.assertEqual(len(items), 1, "장애 시 기존 데이터를 유지해야 함")

    def test_broken_structure_is_outage_and_keeps_old_data(self):
        log, health, items = self._run("broken")
        self.assertFalse(health["ok"])
        self.assertEqual(len(items), 1)

    def test_search_based_sources_keep_old_data_on_normal_zero(self):
        """KOTRA/EBNEW/MOFCOM은 검색 기반이라 정상 0건에도 기존 데이터를 남긴다."""
        for name in ("KOTRA", "EBNEW", "MOFCOM"):
            with self.subTest(source=name):
                log, health, items = self._run("empty_board", name=name)
                self.assertEqual(log["status"], "정상")
                self.assertTrue(health["ok"])
                self.assertEqual(len(items), 1, f"{name}: 과거 공고를 지우지 않아야 함")


class EquipmentClassifierTest(unittest.TestCase):
    """C. 장비 판정 — 반드시 포함 / 반드시 제외."""

    # (규칙 라벨, 제목, 출처) — 제목·출처는 실제 운영 데이터에 나온 형태를 쓴다.
    # 출처가 판정에 영향을 주는 규칙(KANC/NNFC 나노팹 보조 신호)이 있어서
    # 임의의 출처를 넣으면 실제 동작과 달라진다.
    MUST_INCLUDE = [
        ("PVD", "반도체 PVD 스퍼터링 장비 1식 구매", "EBNEW"),
        ("CVD", "[공고 제2026-25호] Large-area Metal-Organic Chemical Vapor Deposition "
                "1SET (대면적 비소/인화물계 유기금속화학기상증착장비 1대) 구매 (외자)", "KANC"),
        ("ALD", "200mm 클러스터 ALD 장비 본체 구매", "NNFC"),
        ("Wet Etching", "단일 웨이퍼 스핀 식각 장비 1식", "JETRO"),
        ("CMP", "반도체 웨이퍼 CMP 장비 1식 구매", "EBNEW"),
        ("Prober", "EIC에서 반도체 검출기의 개발을 위한 반자동 프로버 1식", "JETRO"),
        ("Tester", "[공고 제2026-34호] 입자충격잡음검출시험기 1식 구매 입찰 공고(내자)", "KANC"),
        ("MOCVD", "MOCVD 장비 1식 구매", "KANC"),
        ("Inspection", "난퉁 캉위안 집적회로 패키징 기판 프로젝트 - 자동광학검사(AOI) 장비 2대", "EBNEW"),
        ("Metrology", "반도체 박막 두께 계측기 1식 구매", "KANC"),
        ("Lithography", "반도체 웨이퍼 노광장비 구매_260270", "KAIST"),
        ("Furnace", "(재)(외자)입찰공고(제2026–059호) 200mm 수직형 산질화막 성장로", "NNFC"),
    ]
    MUST_EXCLUDE = [
        ("wafer material", "동위원소 농축 12 인치 SOI 웨이퍼 1식"),
        ("chemical", "반도체 공정용 화학약품 구매"),
        ("bead/slurry", "연마비즈"),
        ("chip", "양자자이로 감지 칩 구매"),
        ("sensor 단품", "첨단 로직 반도체 분석을 위한 X-ray 센서 1식"),
        ("frame/baseplate", "전력증폭기 패키징프레임 및 베이스플레이트"),
        ("utility 공사", "200mm 클러스터 ALD 장비 외 11종 유틸리티 연결 공사"),
        ("LED display 제품", "LED 대형 스크린 전시 장비의 일괄"),
        ("software subscription", "[사전규격공개] 초전도 양자 컴퓨터 회로 설계툴 구독"),
        ("yearbook", "2026 반도체 산업 연감(예약 판매중)"),
    ]

    def _classify(self, title, source="EBNEW"):
        return EF.classify({"sourceCode": source, "title": title,
                            "originalTitle": None, "description": None, "keywords": []})

    def test_must_include(self):
        for label, title, source in self.MUST_INCLUDE:
            with self.subTest(rule=label):
                verdict, reason = self._classify(title, source=source)
                self.assertEqual(verdict, "장비",
                                 f"{label}[{source}]: {title[:50]} → {verdict} ({reason})")

    def test_must_exclude(self):
        for label, title in self.MUST_EXCLUDE:
            with self.subTest(rule=label):
                verdict, reason = self._classify(title)
                self.assertNotEqual(verdict, "장비", f"{label}: {title} → {verdict} ({reason})")

    def test_institution_alone_does_not_qualify(self):
        """KANC/NNFC라는 기관만으로 장비로 인정하지 않는다(No.009)."""
        for source in ("KANC", "NNFC"):
            with self.subTest(source=source):
                verdict, _ = self._classify("일반 시험장비 1식 구매", source=source)
                self.assertNotEqual(verdict, "장비")

    def test_fab_facility_excluded_even_at_fab_institutions(self):
        for title in ("클린룸 항온항습기 및 공조기 1식 구매", "전동 지게차 1대 구매",
                      "무정전전원장치(UPS) 교체 구매", "사무용 복합기 5대 구매",
                      "팹 비상전력 공급용 버스(부스) 덕트 제작 설치"):
            with self.subTest(title=title):
                verdict, reason = self._classify(title, source="KANC")
                self.assertEqual(verdict, "제외", f"{title} → {verdict} ({reason})")

    def test_specific_equipment_survives_component_words(self):
        """구체 장비어가 있으면 부품 단어가 함께 있어도 장비로 본다."""
        verdict, _ = self._classify("반도체 검출기의 개발을 위한 반자동 프로버 1식")
        self.assertEqual(verdict, "장비")


class TelegramTest(unittest.TestCase):
    """D. Telegram — 재발송 금지 / 임계값 / 복구."""

    def _sig(self, **kw):
        base = {"sourceCode": "MOFCOM", "originalTitle": "제목", "originalOrg": "기관",
                "postedDate": "2026-09-01", "dueDate": "2026-09-30",
                "noticeType": "정식입찰"}
        base.update(kw)
        return base

    def test_signature_ignores_url_and_id(self):
        """URL/ID가 바뀌어도 같은 공고면 같은 지문이어야 한다(EBNEW URL 정규화 안전성)."""
        a = self._sig(id="x1", url="http://www.ebnew.com/a.html")
        b = self._sig(id="x2", url="https://www.ebnew.com/a.html")
        self.assertEqual(NT.announcement_signature(a), NT.announcement_signature(b))
        self.assertEqual(FA.announcement_signature(a), FA.announcement_signature(b))

    def test_signature_changes_when_duedate_changes(self):
        """마감일이 바뀌면 새 정보이므로 다른 지문이어야 한다."""
        a = self._sig(dueDate="2026-09-30")
        b = self._sig(dueDate="2026-10-15")
        self.assertNotEqual(NT.announcement_signature(a), NT.announcement_signature(b))

    def test_signature_changes_when_noticetype_changes(self):
        a = self._sig(noticeType="정식입찰")
        b = self._sig(noticeType="낙찰·수주결과")
        self.assertNotEqual(NT.announcement_signature(a), NT.announcement_signature(b))

    def _run_notify(self, before_items, after_items):
        sent = []
        saved_send = NT.send_telegram
        NT.send_telegram = lambda t, c, m: (sent.append(m), True)[1]
        os.environ["TELEGRAM_BOT_TOKEN"] = "x"
        os.environ["TELEGRAM_CHAT_ID"] = "y"
        import tempfile
        d = tempfile.mkdtemp()
        bp, ap = os.path.join(d, "b.json"), os.path.join(d, "a.json")
        json.dump({"items": before_items}, io.open(bp, "w", encoding="utf-8"), ensure_ascii=False)
        json.dump({"items": after_items}, io.open(ap, "w", encoding="utf-8"), ensure_ascii=False)
        saved_argv = sys.argv
        sys.argv = ["notify_telegram.py", bp, ap]
        try:
            NT.main()
        finally:
            sys.argv = saved_argv
            NT.send_telegram = saved_send
        return sent

    def _item(self, **kw):
        base = {"id": "a1", "sourceCode": "JETRO", "source": "JETRO (일본)",
                "title": "건식 식각 장비 1식", "originalTitle": "Dry Etching System 1 set",
                "org": "AIST", "originalOrg": "AIST", "postedDate": "2026-09-01",
                "dueDate": "2026-09-30", "noticeType": "정식입찰",
                "equipmentStatus": "장비", "url": "https://example.invalid/a"}
        base.update(kw)
        return base

    def test_existing_item_is_not_resent(self):
        item = self._item()
        sent = self._run_notify([item], [item])
        self.assertEqual(sent, [])

    def test_reindexed_item_is_not_resent(self):
        """사이트가 같은 공고에 새 id를 부여해도 재발송하지 않는다(MOFCOM)."""
        old = self._item(id="mof-1", sourceCode="MOFCOM")
        new = dict(old, id="mof-999")
        sent = self._run_notify([old], [old, new])
        self.assertEqual(sent, [], "재색인만으로 재발송하면 안 됨")

    def test_genuine_new_equipment_is_sent_once(self):
        old = self._item(id="a1")
        new = self._item(id="a2", title="신규 건식 식각 장비 1식",
                         originalTitle="Brand-new Dry Etching System 1 set")
        sent = self._run_notify([old], [old, new])
        self.assertEqual(len(sent), 1)

    def test_non_equipment_is_not_sent(self):
        old = self._item(id="a1")
        for status in ("제외", "검토 필요"):
            with self.subTest(status=status):
                new = self._item(id="a9", title="SOI 웨이퍼 1식",
                                 originalTitle="SOI wafer 1 set", equipmentStatus=status)
                sent = self._run_notify([old], [old, new])
                self.assertEqual(sent, [], f"{status} 공고는 발송하지 않아야 함")

    def _health(self, failures, alert_sent, ok=False):
        return {"KOTRA": {"ok": ok, "lastStatus": "오류" if not ok else "정상",
                          "lastError": "e", "collectedThisRun": 0,
                          "lastRunAt": "2026-09-04T00:00:00",
                          "lastSuccessAt": "2026-09-03T00:00:00",
                          "consecutiveFailures": failures,
                          "failureAlertSent": alert_sent}}

    def test_failure_alert_threshold(self):
        self.assertEqual(decide_actions(self._health(1, False)), [])
        self.assertEqual(decide_actions(self._health(2, False)), [])
        actions = decide_actions(self._health(3, False))
        self.assertEqual([(a[0], a[1]) for a in actions], [("KOTRA", "failure")])

    def test_no_duplicate_failure_alert(self):
        for failures in (4, 5, 12):
            with self.subTest(failures=failures):
                self.assertEqual(decide_actions(self._health(failures, True)), [])

    def test_recovery_alert_once(self):
        actions = decide_actions(self._health(0, True, ok=True))
        self.assertEqual([(a[0], a[1]) for a in actions], [("KOTRA", "recovery")])
        # 복구 알림을 보낸 뒤에는 플래그가 내려가므로 다시 보내지 않는다
        self.assertEqual(decide_actions(self._health(0, False, ok=True)), [])

    def test_health_flag_survives_rebuild(self):
        """build_source_health가 failureAlertSent를 초기화하면 중복 알림이 난다(No.005)."""
        log = {"KOTRA": {"status": "오류", "detail": "e", "count": 0}}
        prev = {"KOTRA": {"consecutiveFailures": 3, "failureAlertSent": True,
                          "lastSuccessAt": "2026-09-03T00:00:00"}}
        health = FA.build_source_health(log, prev, "2026-09-04T00:00:00")
        self.assertTrue(health["KOTRA"]["failureAlertSent"])
        self.assertEqual(health["KOTRA"]["consecutiveFailures"], 4)


class EbnewUrlTest(unittest.TestCase):
    """EBNEW URL 스킴 고정 (No.012)."""

    def test_http_is_upgraded_for_ebnew_hosts(self):
        self.assertEqual(ebnew.canonical_url("http://www.ebnew.com/businessShow/1.html"),
                         "https://www.ebnew.com/businessShow/1.html")
        self.assertEqual(ebnew.canonical_url("http://ss.ebnew.com/tradingSearch/index.htm?a=1"),
                         "https://ss.ebnew.com/tradingSearch/index.htm?a=1")

    def test_https_is_unchanged(self):
        url = "https://www.ebnew.com/businessShow/1.html"
        self.assertEqual(ebnew.canonical_url(url), url)

    def test_other_domains_untouched(self):
        for url in ("http://www.kotra.or.kr/x", "http://www.ebnew.com.other.invalid/x"):
            with self.subTest(url=url):
                self.assertEqual(ebnew.canonical_url(url), url)

    def test_query_and_path_preserved(self):
        url = "http://www.ebnew.com/a/b/c.html?x=1&y=2#frag"
        self.assertEqual(ebnew.canonical_url(url),
                         "https://www.ebnew.com/a/b/c.html?x=1&y=2#frag")


class DataDriftTest(unittest.TestCase):
    """F. 데이터 이상 변동 — 깨진 결과로 알림·커밋이 나가지 않는지."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, name, data):
        path = os.path.join(self.dir, name)
        with io.open(path, "w", encoding="utf-8") as fp:
            fp.write(data if isinstance(data, str)
                     else json.dumps(data, ensure_ascii=False))
        return path

    def _sample(self, n_items=10, n_equip=6, all_ok=True, keep_seen=True):
        items = [{"id": "x%d" % i,
                  "equipmentStatus": "장비" if i < n_equip else "제외",
                  "firstSeenAt": "2026-09-01T00:00:00" if keep_seen else ""}
                 for i in range(n_items)]
        return {"items": items,
                "sourceHealth": {"KANC": {"ok": all_ok}, "NNFC": {"ok": True}}}

    def _check(self, before, after):
        return DRIFT.main(self._write("b.json", before), self._write("a.json", after))

    def test_normal_change_passes(self):
        """공고가 몇 건 늘고 주는 정상 변동은 통과해야 한다."""
        self.assertEqual(self._check(self._sample(10, 6), self._sample(12, 7)), 0)

    def test_empty_result_is_blocked(self):
        self.assertEqual(self._check(self._sample(), ""), 1)

    def test_malformed_result_is_blocked(self):
        self.assertEqual(self._check(self._sample(), "{not json"), 1)

    def test_count_collapse_is_blocked(self):
        self.assertEqual(self._check(self._sample(40, 20), self._sample(3, 2)), 1)

    def test_equipment_collapse_is_blocked(self):
        """전체 건수는 유지되는데 장비 판정만 무너진 경우도 잡는다."""
        self.assertEqual(self._check(self._sample(20, 18), self._sample(20, 2)), 1)

    def test_all_sources_down_is_blocked(self):
        after = self._sample(10, 6)
        for v in after["sourceHealth"].values():
            v["ok"] = False
        self.assertEqual(self._check(self._sample(10, 6), after), 1)

    def test_one_source_down_still_passes(self):
        """한 수집원 장애는 정상 운영 범위다 — 여기서 막으면 안 된다."""
        self.assertEqual(
            self._check(self._sample(10, 6), self._sample(10, 6, all_ok=False)), 0)

    def test_lost_first_seen_is_blocked(self):
        """firstSeenAt이 사라지면 기존 공고가 신규로 오인돼 재발송된다."""
        self.assertEqual(
            self._check(self._sample(10, 6), self._sample(10, 6, keep_seen=False)), 1)

    def test_id_mass_loss_is_blocked(self):
        """CASE E — 건수는 비슷한데 ID가 전부 갈리면 전부 신규로 재발송된다."""
        before = self._sample(20, 12)
        after = self._sample(20, 12)
        for n, i in enumerate(after["items"]):
            i["id"] = "y%d" % n            # ID 체계가 통째로 바뀐 상황
        self.assertEqual(self._check(before, after), 1)

    def test_partial_id_turnover_still_passes(self):
        """검색형 수집원은 결과가 절반쯤 바뀌는 날이 있다 — 막으면 안 된다."""
        before = self._sample(20, 12)
        after = self._sample(20, 12)
        for i in after["items"][:8]:
            i["id"] = i["id"] + "-new"
        self.assertEqual(self._check(before, after), 0)

    def test_small_dataset_is_not_over_policed(self):
        """표본이 작을 때(10건 미만) 비율 검사로 정상 수집을 막지 않는다."""
        self.assertEqual(self._check(self._sample(6, 4), self._sample(2, 1)), 0)

    def test_ratio_rule_is_not_hardcoded_to_current_size(self):
        """지금이 67건이라는 사실에 기대지 않는다 — 300건이어도 같게 동작한다."""
        self.assertEqual(self._check(self._sample(300, 200), self._sample(280, 190)), 0)
        self.assertEqual(self._check(self._sample(300, 200), self._sample(20, 10)), 1)

    def test_missing_before_still_checks_after(self):
        """최초 실행이라 이전 상태가 없어도 결과 자체는 검사한다."""
        missing = os.path.join(self.dir, "없음.json")
        self.assertEqual(DRIFT.main(missing, self._write("a.json", self._sample())), 0)
        dead = self._sample(all_ok=False)
        dead["sourceHealth"]["NNFC"]["ok"] = False
        self.assertEqual(DRIFT.main(missing, self._write("a2.json", dead)), 1)


class ResearchInstrumentTest(unittest.TestCase):
    """G. 연구기관의 일반 계측장비 — 기관·부서명만으로 포함하지 않는다.

    지시문 No.013 2·4번. "반도체 관련 부서가 산 연구장비"와 "반도체용
    장비"는 다르다. 산업·공정 근거 없이 장비 신호만 있으면 제외한다.
    """

    def _classify(self, title, source="KRISS", description=None):
        return EF.classify({"sourceCode": source, "title": title,
                            "originalTitle": None, "description": description,
                            "keywords": []})

    # 산업·공정 근거 없는 연구·계측 장비 — 전부 제외되어야 한다.
    GENERAL_INSTRUMENTS = [
        ("KRISS 중적외선 레이저", "중적외선 레이저 시스템", "KRISS"),
        ("열분석기", "동시열분석기(TGA/DSC) 1식 구매", "KRISS"),
        ("가스분석기", "FTIR 적외선 가스 분광 분석기 1대", "KRISS"),
        ("항법장치", "초고정밀 관성항법 시스템 구매", "DGIST"),
        ("전원장치", "고전압 직류 전원공급장치 1식", "KAIST"),
    ]

    def test_general_research_instruments_are_excluded(self):
        for label, title, source in self.GENERAL_INSTRUMENTS:
            with self.subTest(rule=label):
                verdict, reason = self._classify(title, source=source)
                self.assertEqual(verdict, "제외",
                                 f"{label}[{source}]: {title} → {verdict} ({reason})")

    def test_kriss_mid_ir_laser_is_excluded(self):
        """실제 운영 공고 그대로 — 검토 필요가 아니라 제외여야 한다."""
        verdict, reason = self._classify("새글 중적외선 레이저 시스템")
        self.assertEqual(verdict, "제외")
        self.assertIn("일반 연구·계측 장비", reason)

    # 같은 연구기관이 사더라도 반도체 공정·계측 근거가 있으면 장비다.
    # 이 규칙 때문에 정상 장비가 빠지면 안 된다.
    SEMICONDUCTOR_INSTRUMENTS = [
        ("웨이퍼 계측", "반도체 웨이퍼 박막 두께 계측기 1식 구매", "KRISS"),
        ("공정 분광", "식각 공정 모니터링용 플라즈마 발광분광 분석기", "KRISS"),
        ("현미경", "8inch 웨이퍼 검사를 위한 레이저 공초점 현미경 1식", "JETRO"),
        ("프로버", "반도체 검출기의 개발을 위한 반자동 프로버 1식", "JETRO"),
        ("증착", "MOCVD 장비 1식 구매", "KANC"),
        ("노광", "반도체 웨이퍼 노광장비 구매_260270", "KAIST"),
    ]

    def test_semiconductor_instruments_still_included(self):
        for label, title, source in self.SEMICONDUCTOR_INSTRUMENTS:
            with self.subTest(rule=label):
                verdict, reason = self._classify(title, source=source)
                self.assertEqual(verdict, "장비",
                                 f"{label}[{source}]: {title} → {verdict} ({reason})")

    def test_monitoring_is_not_mistaken_for_office_monitor(self):
        """한글은 부분 문자열로 맞으므로 "모니터링"이 시설 신호 "모니터"에
        걸리면 안 된다. 그래도 사무용 모니터 구매는 여전히 제외돼야 한다."""
        verdict, _ = self._classify(
            "반도체 식각 공정 실시간 모니터링 장비 1식", source="KANC")
        self.assertEqual(verdict, "장비")
        verdict, _ = self._classify("사무용 27인치 모니터 30대 구매", source="KANC")
        self.assertEqual(verdict, "제외")

    def test_industry_signal_may_come_from_description(self):
        """제목에 없어도 본문에 산업 근거가 있으면 인정한다 — 과잉 제외 방지."""
        verdict, _ = self._classify(
            "레이저 공초점 현미경 1식", source="KRISS",
            description="반도체 웨이퍼 표면 결함 검사에 사용한다.")
        self.assertEqual(verdict, "장비")


class ChineseGlossaryTest(unittest.TestCase):
    """H. 중국어 용어집 — 반복 기술용어가 pinyin으로 남지 않는지.

    지시문 No.013 5·6번. 번역 엔진은 그대로 두고, 실제 운영 제목에서
    로마자로 남던 용어만 용어집으로 처리한다.
    """

    # (원문 조각, 결과에 있어야 할 한국어, 남으면 안 되는 pinyin)
    CASES = [
        ("技术改造", "기술", "JiShu"),
        ("产线", "생산라인", "ChanXian"),
        ("光电", "광전", "GuangDian"),
        ("显示", "디스플레이", "XianShi"),
        ("印刷OLED", "인쇄", "YinShua"),
        ("高清", "고화질", "GaoQing"),
        ("一期", "1단계", "YiQi"),
        ("板级封装", "패널레벨 패키징", "WeiBan"),
    ]

    def test_repeated_terms_are_translated(self):
        for zh, ko, _pinyin in self.CASES:
            with self.subTest(term=zh):
                out = ZT._apply_glossary(zh)
                self.assertIn(ko, out, f"{zh} → {out}")
                self.assertNotIn(zh, out, f"{zh}가 그대로 남음: {out}")

    def test_year_keeps_its_number(self):
        """"2026年" 이 "년" 만 남거나 " 년 "으로 벌어지면 안 된다."""
        self.assertIn("2026년", ZT._apply_glossary("2026年"))

    def test_year_does_not_break_annual_output(self):
        """年产(연간생산) 패턴이 연도 패턴에 먹히면 안 된다."""
        self.assertIn("연산100만장", ZT._apply_glossary("年产100万片"))

    def test_longer_terms_win(self):
        """짧은 용어가 긴 용어 안을 갉아먹으면 안 된다."""
        # 生产线(3자)이 产线(2자)보다 먼저 적용돼야 "生"이 남지 않는다.
        out = ZT._apply_glossary("OLED生产线")
        self.assertIn("생산라인", out)
        self.assertNotIn("生", out)
        # 面板级封装 / 显示技术 같은 기존 조합어도 그대로 유지된다.
        self.assertIn("패널레벨패키징(PLP)", ZT._apply_glossary("面板级封装"))
        self.assertIn("디스플레이 기술", ZT._apply_glossary("显示技术"))

    def test_real_titles(self):
        """실제 운영 공고 원문 — pinyin 잔여가 없어야 한다."""
        cases = [
            ("成都京东方光电2026年第4.5代TFT-LCD产线技术改造项目",
             ["광전", "2026년", "생산라인", "기술", "개조"]),
            ("第8.6代印刷OLED生产线一期项目",
             ["제8.6세대", "인쇄", "생산라인", "1단계"]),
            ("苏州华星光电显示有限公司高清MINI LED COB产品技术改造项目",
             ["화싱광전", "디스플레이", "고화질", "기술"]),
        ]
        for zh, expected in cases:
            with self.subTest(title=zh[:20]):
                out = ZT._apply_glossary(zh)
                for e in expected:
                    self.assertIn(e, out, f"{e} 없음 → {out}")

    def test_numbers_do_not_run_together(self):
        """용어집이 한자를 많이 흡수할수록 번역 모델이 띄어쓰기를 넣어 줄
        기회가 줄어든다. "2026년제4.5세대TFT-LCD"처럼 붙지 않아야 한다."""
        out = ZT._apply_glossary("成都京东方光电2026年第4.5代TFT-LCD产线")
        self.assertIn("2026년 제4.5세대 TFT-LCD", out)

    def test_company_names_are_not_invented(self):
        """근거 없는 고유명사는 한국어로 창작하지 않는다(지시문 No.013 7번).

        奕斯伟는 용어집에 없으므로 뜻을 지어내지 않고 그대로 남는다.
        """
        out = ZT._apply_glossary("奕斯伟板级封装")
        self.assertIn("패널레벨 패키징", out)
        self.assertIn("奕斯伟", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
