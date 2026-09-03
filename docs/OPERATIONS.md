# 운영 매뉴얼 — 장비 프로젝트 레이더

이 문서는 "무엇이 어떻게 도는지"와 "문제가 생겼을 때 무엇부터 보는지"만
적는다. 기능 설명은 `README.md`를 본다.

---

## 1. 전체 구조

정적 사이트 + GitHub Actions 배치다. 서버도 DB도 없다.

```
GitHub Actions (매일 07:00 KST)
  └ scripts/fetch_announcements.py
      └ scripts/collectors/*.py  (10개 수집원)
      └ scripts/collectors/equipment_filter.py  (장비 판정)
  └ scripts/check_data_drift.py   (이상 변동 검사 — 여기서 막히면 알림·커밋 없음)
  └ scripts/notify_telegram.py    (신규 공고 알림)
  └ scripts/notify_source_health.py (수집원 장애·복구 알림)
  └ data/announcements.json 커밋
        ↓
GitHub Pages → index.html / app.js / style.css 가 이 JSON을 읽어 화면을 그린다
```

`data/announcements.json` 하나가 모든 상태다: 공고 목록(`items`),
수집원 상태(`sourceHealth`), 갱신 시각(`updatedAt`).

## 2. 수집원 10곳

| 코드 | 기관 | 국가 | 성격 | 비고 |
|---|---|---|---|---|
| KANC | 한국나노기술원 | KR | 게시판 | 반도체 나노팹 |
| NNFC | 나노종합기술원 | KR | 게시판 | 반도체 나노팹 |
| KRISS | 한국표준과학연구원 | KR | 게시판 | |
| KAIST | KAIST | KR | 게시판 | |
| DGIST | DGIST | KR | 게시판 | |
| KOTRA | KOTRA 해외사업 | KR | 검색형 | **IP 의존 장애 있음 — 5절** |
| EBNEW | 中国招标投标公共服务平台 | CN | 검색형 | 번역 필요 |
| MOFCOM | 中国商务部 | CN | 검색형(JSON) | TLS 특이 — 6절 |
| JETRO | 일본무역진흥기구 | JP | API(JSON) | 번역 필요 |
| ITRI | 대만 공업기술연구원 | TW | 게시판 | 번체 중국어, 인증서 특이 — 6절 |

검색형 3곳(KOTRA·EBNEW·MOFCOM)은 정상 0건이어도 기존 데이터를 지우지 않는다
(`KEEP_EXPIRED_SOURCES`). 검색 결과가 하루 비었다고 과거 공고까지 사라지면
안 되기 때문이다.

## 3. 매일 무엇이 도는가

`.github/workflows/fetch-announcements.yml`, `cron: 0 22 * * *` (= 07:00 KST).
수동 실행은 Actions 탭의 **Run workflow** 또는:

```bash
gh workflow run "Fetch Project Radar Announcements"
```

스텝 순서와 각각의 의미:

1. **핵심 규칙 회귀테스트** — `python -m unittest discover -s tests`.
   네트워크·번역 모델을 쓰지 않아 1초 안에 끝난다. **여기서 실패하면
   수집을 하지 않는다.** 잘못 분류된 데이터를 커밋하는 것보다 그날 갱신을
   건너뛰는 편이 낫다.
2. **Snapshot previous data** — 신규 공고를 가리기 위해 직전 상태를 복사한다.
3. **Fetch announcements** — 10개 수집원을 순회하고 장비 판정을 붙인다.
4. **데이터 이상 변동 검사** — `check_data_drift.py`. 4절 참조.
   **여기서 실패하면 알림도 커밋도 하지 않는다.**
5. **신규 공고 Telegram 알림** — 장비로 판정된 신규 공고만 보낸다.
6. **수집원 장애 Telegram 알림** — 연속 3회 실패 시 1회만, 복구 시 1회.
7. **Commit updated data** — `data/announcements.json` 커밋 → Pages 갱신.

## 4. 안전장치 두 가지

운영 사고는 대부분 "잘못된 데이터가 조용히 통과하는 것"이라 두 겹으로 막는다.

**회귀테스트 (`tests/test_regression.py`, 55건)** — 수집 전에 돈다.
네트워크 재시도 정책, 정상 0건 vs 장애 판정, 장비 포함·제외 목록,
Telegram 중복 방지, EBNEW URL 정규화, 데이터 이상 변동 검사를 고정한다.
로컬에서도 같은 명령으로 돌린다:

```bash
python -m unittest discover -s tests -v
```

**이상 변동 검사 (`scripts/check_data_drift.py`)** — 수집 후 알림 전에 돈다.
다음 중 하나라도 걸리면 워크플로를 실패시킨다.

- 결과 파일이 비었거나 JSON으로 읽히지 않는다
- 전체 건수가 절반 미만으로 줄었다
- 장비 판정 건수가 절반 미만으로 줄었다
- 모든 수집원이 동시에 실패했다
- 기존 공고의 `firstSeenAt`이 사라졌다 (신규로 오인돼 재발송된다)

공고 몇 건의 증감이나 한 수집원의 일시적 장애는 정상 변동이라 통과시킨다.

## 5. KOTRA — 알려진 IP 의존 장애

**증상**: Actions에서만 `RemoteDisconnected` 또는 TCP 연결 거부가 난다.
로컬에서는 정상이다.

**원인**: KOTRA 쪽에서 일부 Azure(GitHub Actions) 러너 IP 대역을 막고 있다.
러너 IP에 따라 결과가 갈린다 — 측정값:

| 러너 IP | 목록 요청 성공률 |
|---|---|
| 13.83.107.129 | 83% |
| 134.33.70.62 | 50% |
| 20.59.242.3 | 0% (TCP 연결 자체 거부) |

**대응**: `kotra.py`의 `can_reach_kotra()`가 수집 시작 전에 TCP 443을 8초
타임아웃 2회로 찔러본다. 막힌 러너면 재시도로 시간을 쓰지 않고 바로
"장애"로 기록하고 넘어간다. 기존 KOTRA 데이터는 유지된다.

**하지 않는 것**: 프록시, User-Agent 돌려막기, 비공식 미러, 인증서 검증 해제.
전부 지시문에서 금지됐고 근본 해결도 아니다. 실행 환경(self-hosted runner
등) 변경은 사용자 승인 사항이다.

**연속 실패가 이어질 때**: 수동 진단을 돌린다(운영 데이터는 건드리지 않는다).

```bash
python scripts/diagnose_kotra.py        # DNS → TCP/TLS → HTTP → 애플리케이션 계층별
python scripts/diagnose_kotra_rate.py   # 재시도 없이 요청당 실패율 측정
```

Actions에서 같은 진단을 돌리려면 **Diagnose KOTRA connectivity** 워크플로를
수동 실행한다(`workflow_dispatch` 전용, 자동 실행 없음).

## 6. TLS 관련 특이사항 — 건드리지 말 것

두 사이트는 표준 설정으로는 접속되지 않아 최소한의 조정을 해 뒀다.
**둘 다 인증서 검증과 호스트명 확인은 그대로 켜져 있다.**

- **MOFCOM**: `ctx.set_ciphers("DEFAULT@SECLEVEL=1")` — 서버가 낮은 보안수준의
  cipher만 제시한다. cipher 허용 범위만 넓힌 것이다.
- **ITRI**: `ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT` — 서버 인증서에
  Subject Key Identifier 확장이 빠져 있어 Python 3.13+의 RFC 5280 엄격 검증에
  걸린다. 엄격 플래그만 껐다.

`CERT_NONE`, `check_hostname = False`, 검증 비활성화는 어떤 이유로도 넣지 않는다.

## 7. 문제가 생겼을 때

**Actions가 빨간불이다** → 어느 스텝에서 멈췄는지부터 본다.

```bash
gh run list --workflow="Fetch Project Radar Announcements" --limit 5
gh run view <run-id>            # 스텝 목록
gh run view --job=<job-id> --log-failed
```

- *회귀테스트*에서 멈춤 → 코드 변경이 규칙을 깬 것이다. 데이터는 그대로이니
  급하지 않다. 실패한 테스트 이름이 어느 규칙인지 그대로 알려준다.
- *이상 변동 검사*에서 멈춤 → 로그의 `[DRIFT]` 줄이 무엇이 무너졌는지 적는다.
  수집원 대량 장애인지, 파서가 깨진 것인지 확인한다. **알림은 나가지 않았다.**
- *Fetch announcements*에서 멈춤 → 특정 수집원의 예외다. 로그에서 `[출처코드]`
  태그를 찾는다.

**특정 사이트만 계속 0건이다** → 정상 0건인지 장애인지는 화면의 수집원 상태와
`sourceHealth`로 구분된다. `ok: true`인데 0건이면 목록을 정상적으로 읽었는데
조건에 맞는 공고가 없는 것이다(ITRI가 대표적이다 — 詢價案 대부분이 생의료·
시설·소모품이라 정상적으로 0건인 날이 많다).

**Telegram이 조용하다** → 신규 장비 공고가 없으면 보내지 않는 것이 정상이다.
장애 알림은 연속 3회 실패에 1회만 보내고, 그 뒤로는 복구할 때까지 다시 보내지
않는다(중복 방지 상태는 `sourceHealth.failureAlertSent`에 저장된다).

**같은 공고가 또 왔다** → 공고 동일성은 URL·ID가 아니라
`announcement_signature()`(출처, 원문 제목, 원문 기관, 게시일, 마감일, 공고유형)로
판단한다. 사이트가 재색인해 ID가 바뀌어도 재발송되지 않는다. 그래도 재발송이
일어났다면 원문 제목이나 기관명 표기가 실제로 바뀐 것이다.

## 8. 데이터를 되돌려야 할 때

`data/announcements.json`은 매 실행마다 커밋되므로 git 이력이 곧 백업이다.

```bash
git log --oneline -- data/announcements.json
git show <sha>:data/announcements.json > data/announcements.json
```

지시문 No.012 작업 직전 상태는 별도로 보관돼 있다 —
`data/backup/announcements-baseline-No012.json`, 설명은
`docs/BASELINE-No012.md`.

되돌린 뒤에는 반드시 확인한다: 총 건수, 장비 판정 분포, `firstSeenAt` 유실
여부. 마지막 것이 중요하다 — `firstSeenAt`이 비면 그 공고들이 다음 실행에서
신규로 오인돼 한꺼번에 재발송된다(4절의 검사가 이 경우를 막는다).

## 9. 번역

Argos Translate 오프라인 모델(en→ko, zh→en)을 Actions에서 캐시해 쓴다.
같은 문장이라도 기계마다 출력이 미세하게 달라서, 사람이 확인한 번역은
`data/translation_memory.json`에 원문 기준으로 고정해 둔다. 제목이 이유 없이
바뀌는 것을 막기 위한 장치이므로 이 파일은 커밋 대상이다.

번역 엔진 교체는 지시문에서 금지돼 있다.

## 10. 손대기 전에 알아둘 것

- 수집원을 새로 추가하거나 나라를 늘리는 것은 사용자 승인 사항이다.
- 장비 판정 규칙(`equipment_filter.py`)은 "산업 신호 **and** 장비 신호" 두
  조건이다. 기관·부서명만으로 장비를 인정하지 않는다. 규칙을 바꾸기 전에
  `tests/test_regression.py`의 포함·제외 목록을 먼저 본다 — 과거에 잘못
  판정했던 실제 공고들이 거기 고정돼 있다.
- 수집기에서 `except Exception:`을 쓰지 않는다. 파싱 오류나 코드 버그가
  네트워크 재시도로 숨는다. 네트워크 예외는 `common.py`의
  `NETWORK_EXCEPTIONS`를 쓴다.
- 재시도는 최대 3~4회다. 403·404처럼 서버가 명확히 답한 오류는 재시도하지
  않고, 429·5xx만 재시도하며 `Retry-After`를 존중하되 30초로 자른다.

---

## 부록 A. `diagnose-kotra.yml`을 남겨 두는 이유

지시문 No.012 28번의 정리 대상 판단 결과 — **유지한다.**

- 운영에 관여하지 않는다. `workflow_dispatch` 전용이라 스케줄로 도는 일이 없고,
  수집 파이프라인이나 `data/`를 건드리지 않는다. 남겨 둬도 비용이 0이다.
- KOTRA 장애가 **아직 해결되지 않았다.** 러너 IP에 따라 결과가 갈리는 상태라
  같은 증상이 다시 나면 계층별 진단을 또 돌려야 한다. 그때 이 워크플로가
  없으면 처음부터 다시 만들어야 한다.
- 로컬에서는 KOTRA가 항상 정상이라 **Actions에서 돌려야만 의미가 있다.**
  로컬 스크립트(`scripts/diagnose_kotra*.py`)만으로는 대체되지 않는다.

KOTRA 문제가 근본적으로 해결되면(사이트 정책 변경 또는 실행 환경 변경 승인)
이 워크플로와 `scripts/diagnose_kotra*.py`를 함께 지운다.
