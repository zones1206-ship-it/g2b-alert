# 데이터 보호장치 감사 — 지시문 No.013 11~17번

No.012 작업 중 `data/announcements.json`이 빈 파일로 커밋된 사고가 있었다.
그 뒤에 만든 보호장치가 **실제 워크플로 순서상** 알림과 커밋을 확실히 막는지
코드 기준으로 감사한다.

---

## 1. 실제 실행 순서 (`.github/workflows/fetch-announcements.yml`)

| # | 스텝 | 조건 | 실패 시 |
|---|---|---|---|
| 1 | Checkout | — | 중단 |
| 2 | Set up Python | — | 중단 |
| 3 | Install dependencies | — | 중단 |
| 4 | Restore Argos translation model cache | — | 중단 |
| 5 | Ensure Argos translation models | `continue-on-error: true` | 계속 |
| 6 | **핵심 규칙 회귀테스트** | — | **중단 (수집 안 함)** |
| 7 | 러너 외부 IP 기록 | `continue-on-error: true` | 계속 |
| 8 | Snapshot previous data | — | 중단 |
| 9 | Fetch announcements | — | 중단 |
| 10 | **데이터 이상 변동 검사** | — | **중단 (알림·커밋 안 함)** |
| 11 | Notify new announcements via Telegram | — | 중단 |
| 12 | Notify source collection failures via Telegram | — | 중단 |
| 13 | Commit updated data (`git add`/`commit`/`push`) | — | 중단 |

**핵심 확인**: 워크플로 전체에 `if:` 조건이 하나도 없고, 알림·커밋 스텝에는
`continue-on-error`가 붙어 있지 않다. GitHub Actions는 스텝을 순차 실행하며
실패한 스텝에서 잡을 중단하므로, **10번이 실패하면 11·12·13번은 아예
실행되지 않는다.** `if: always()` 같은 우회 경로도 없다.

즉 지시문 12·16·17번이 요구한 두 가지가 구조적으로 보장된다.

- ★ Telegram 이전 차단 — 10번이 11·12번보다 앞이다.
- ★ commit 이전 차단 — 10번이 13번보다 앞이다.

`continue-on-error`가 붙은 두 스텝(5·7번)은 번역 모델 준비와 진단용 IP
기록이라 실패해도 데이터 안전성과 무관하다.

## 2. 실패 조건별 실측 (`scripts/check_data_drift.py`)

운영 데이터(67건)를 원본으로 시나리오를 만들어 **실제 스크립트를 그대로**
돌렸다. exit code 1이면 워크플로가 중단되어 알림·커밋이 일어나지 않는다.

| CASE | 상황 | 결과 | 검출 내용 |
|---|---|---|---|
| A | 빈 파일 | **FAIL** (exit 1) | `caseA.json 가 비어 있습니다` |
| B | JSON 파싱 불가 | **FAIL** (exit 1) | `Expecting value: line 1 column 20` |
| C | 건수 급감 67 → 3 | **FAIL** (exit 1) | 건수 절반 미만 + ID 4%만 생존 + 장비 판정 절반 미만 (3중 검출) |
| D | firstSeenAt 대량 유실 | **FAIL** (exit 1) | `기존 공고 67건의 firstSeenAt이 사라졌습니다` |
| E | ID 대량 유실 (건수는 동일) | **FAIL** (exit 1) | `기존 공고 ID가 67건 중 0건만 남았습니다 (0%)` |
| F | 정상적인 1건 신규/종료 | **PASS** (exit 0) | ID 99% 생존, 이상 없음 |

CASE E는 이번에 추가했다. **건수만 보면 잡히지 않는 유형**이다 — 수집기가
엉뚱한 목록을 읽으면 건수는 비슷한데 ID가 전부 바뀌고, 그러면 기존 공고
전부가 "신규"로 재발송된다.

## 3. 급감 판정 기준 — 현재 건수에 의존하지 않는다

지시문 14번대로 숫자를 박아 두지 않았다. 비율로 보되 표본이 작을 때는
아예 검사하지 않는다.

```python
SMALL_DATASET_FLOOR = 10   # 이보다 적으면 비율 검사를 하지 않는다
ID_SURVIVAL_MIN = 0.30     # 기존 ID 중 최소 이만큼은 남아 있어야 한다
```

- **비율**: 전체 건수 또는 장비 판정이 직전 대비 절반 미만이면 FAIL.
- **절대 하한**: 직전이 10건 미만이면 비율 검사를 건너뛴다. 8건에서 3건이
  되는 것은 마감이 겹친 평범한 날에도 일어난다. 그런 날 수집을 막으면
  보호장치가 아니라 방해물이 된다.
- **정상적인 대량 종료 고려**: 검색형 수집원(KOTRA·EBNEW·MOFCOM)은 검색
  결과가 크게 바뀌는 날이 있어 ID 생존 하한을 30%로 넉넉히 뒀다. 목록을
  통째로 잘못 읽은 경우(대개 0~10% 생존)를 잡는 것이 목적이다.

회귀테스트로 고정했다 — 300건 → 280건은 통과하고 300건 → 20건은 차단된다.
지금이 67건이라는 사실에 기대지 않는다.

## 4. firstSeenAt 보호 (지시문 15번)

두 겹이다.

1. **수집 단계** — `fetch_announcements.py`의 `stamp_first_seen()`이 기존
   공고의 `firstSeenAt`을 그대로 물려준다. 공고 동일성은 URL·ID가 아니라
   `announcement_signature()`(출처·원문 제목·원문 기관·게시일·마감일·
   공고유형)로 판단하므로, 사이트가 재색인해 ID가 바뀌어도 유지된다.
2. **커밋 직전** — drift 검사가 "기존 ID인데 `firstSeenAt`이 비었다"를
   잡아 낸다(CASE D).

회귀테스트: 기존 ID는 `firstSeenAt` 유지, 신규 ID는 새로 생성.

## 5. 감사 결론

지시문 11~17번이 요구한 항목은 모두 충족한다. 순서를 바꿀 필요는 없었다.

- 워크플로 순서: 수집 → **검증** → Telegram → commit/push — 이미 안전하다.
- CASE A~E 전부 차단, CASE F 통과 — 실측으로 확인.
- 급감 기준은 비율 + 절대 하한이며 현재 건수에 하드코딩되지 않았다.
- `firstSeenAt` 보호는 수집 단계와 커밋 직전 두 곳에 있다.
