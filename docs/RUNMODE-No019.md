# 실행 유형과 Health 분리 (No.019)

## 1. 지금 있는 trigger

`fetch-announcements.yml` 에 걸린 것은 둘뿐이다.

| trigger | 언제 | 용도 |
|---|---|---|
| `schedule` (`0 22 * * *`) | 매일 07:00 KST | 정기 수집 |
| `workflow_dispatch` | 손으로 실행 | 검증 |

`push` / `repository_dispatch` 는 없다. 다른 워크플로 3개
(`diagnose-kotra`, `telegram-test`, `telegram-personal-chat-discovery`)는
모두 `workflow_dispatch` 전용이고 `data/announcements.json` 을 쓰지 않는다.

## 2. 고치기 전 — 두 trigger가 완전히 같았다

`github.event_name` 을 보는 코드가 워크플로에도 파이썬에도 **없었다**.

| 영향 대상 | schedule | workflow_dispatch |
|---|---|---|
| 실제 수집 | 함 | 함 |
| `sourceHealth` 갱신 | 함 | 함 |
| `consecutiveFailures` 누적 | 함 | **함** |
| 장애 Telegram (3회 임계값) | 보냄 | **보냄** |
| 복구 Telegram | 보냄 | **보냄** |
| 신규 공고 Telegram | 보냄 | 보냄 |
| 데이터 커밋 | 함 | 함 |

### No.018 실행 기록이 그 증거다

| 회차 | trigger | KAIST | 연속 실패 | 결과 |
|---|---|---|---|---|
| 1차 | dispatch | 정상 | 0 | — |
| 2차 | dispatch | timeout | 1 | — |
| 3차 | dispatch | timeout | 2 | — |
| 4차 | dispatch | timeout | **3** | **장애 Telegram 발송** |

같은 시각 로컬에서는 KAIST가 4.6초에 정상 수집됐다. 검증 실행이 만든
가짜 장애가 실제 알림으로 나간 것이다.

## 3. 고른 방식 — A안

> `workflow_dispatch` 는 수집·검증은 그대로 하되 운영 장애 누적과
> 장애/복구 Telegram에는 반영하지 않는다.

B안(`production_mode` 입력)과 C안(짧은 간격 반복만 제외)은 쓰지 않았다.
B안은 운영자가 매번 옳은 값을 골라야 하고, C안은 "짧은 간격"의 경계를
정해야 해서 판단이 애매해진다. A안은 규칙이 한 줄이다.

`RUN_MODE` 환경변수 하나로 갈린다.

```
RUN_MODE: ${{ github.event_name == 'schedule' && 'scheduled' || 'manual-validation' }}
```

`RUN_MODE` 가 없으면 `scheduled` 로 본다 — 로컬 실행의 기존 동작이
그대로 유지된다.

## 4. 고친 뒤

| 영향 대상 | schedule | workflow_dispatch |
|---|---|---|
| 실제 수집 | 함 | 함 |
| `sourceHealth` 갱신 | 함 | 함 (`lastRunMode` 기록) |
| `consecutiveFailures` 누적 | 함 | **안 함** (이전 값 유지) |
| 실패 사실 기록 (`lastStatus`/`lastError`) | 함 | **함** — 숨기지 않는다 |
| 장애 Telegram | 보냄 | **안 보냄** (보낼 뻔한 내용은 로그로) |
| 복구 Telegram | 보냄 | **안 보냄** |
| 신규 공고 Telegram | 보냄 | **보냄** — 정책 그대로 |
| 데이터 커밋 | 함 | 함 |

수동 검증에서 **성공**한 것은 그대로 반영한다(`consecutiveFailures` 0,
`lastSuccessAt` 갱신). 수집을 진짜로 했기 때문이다.

## 5. 신규 공고 알림은 건드리지 않았다

장애 알림과 신규 공고 알림은 별개 기능이다. 검증 실행 중에 발견한 신규
공고도 실제 신규 공고이므로 정책을 바꾸지 않았다. `notify_telegram.py` 에
`RUN_MODE` 를 참조하는 코드가 없다는 것을 회귀테스트로 고정했다.

## 6. Health 상태 구분

`sourceHealth` 만 봐도 다음이 구분된다. UI는 바꾸지 않았다.

| 상태 | 어떻게 알아보나 |
|---|---|
| 정상 | `ok: true`, `collectedThisRun > 0` |
| 정상 0건 | `ok: true`, `collectedThisRun: 0`, `lastStatus: "정상"` |
| 부분 상세 실패 | `ok: true` + 로그의 `상세 실패로 이전 수집분 유지` |
| 출처 전체 실패 | `ok: false`, `lastStatus: "오류"`, `lastError` |
| stale 유지 | `ok: false` + 화면에 이전 수집분이 남아 있음 |
| 수동 검증 실패 | `ok: false` + `lastRunMode: "manual-validation"` |

## 7. UI는 그대로 두기로 했다 — 근거

화면 배너는 `ok === false` 인 출처만 띄우고, 문구는 "해당 출처는 기존
수집 데이터를 표시 중입니다" 이다.

수동 검증에서 실패했더라도 **그 출처가 이번에 갱신되지 않았고 낡은
데이터를 보여주는 중이라는 사실은 참이다.** 배너는 사실을 말하고 있다.

배너는 Telegram과 달리 밀어내는 알림이 아니라 화면에만 있고, 다음 정기
실행이 성공하면 저절로 사라진다. 실제로 문제였던 것은 push 알림이었고
그쪽을 막았다. 모드별로 배너를 나누면 "수동 검증 중 장애" 같은 문구가
생겨 일반 사용자에게 오히려 혼란스럽다.

---

## 8. 검증 중 찾은 별개 결함 — 신규 공고 알림 누락

No.019 1차 실행에서 MOFCOM 2건이 늘었는데 신규 공고 알림이 0건이었다.
확인해 보니 **진짜 신규 공고가 "재색인"으로 오판돼 알림이 나가지 않았다**.

새로 올라온 것은 4197-264BOECDCZ02 프로젝트의 **로트 /02** 두 건이고,
이미 있던 **로트 /03** 과 제목·기관·게시일·마감일·공고종류가 모두 같아
signature가 완전히 일치했다. 별개 공고인데 같은 공고로 본 것이다.

No.018에서 이 문제를 보존 로직에서 고쳤지만, **같은 판단이 두 곳에 더
있었다.**

| 위치 | 증상 |
|---|---|
| `stamp_first_seen` 의 `previous_by_signature` | 새 공고가 남의 `firstSeenAt`(이틀 전)을 물려받아 NEW 배지가 안 뜸 |
| `notify_telegram` 의 `before_signatures` | "재색인"으로 오판 → **신규 공고 Telegram 미발송** |

두 곳 모두 No.018과 같은 규칙을 적용했다.

> 공고번호가 이전에 없던 것이면 별개 공고다. 그 외에만 지문으로 판단한다.

수정 전 코드로 새 테스트를 돌리면 5건이 실패하고, 수정 후 전부 통과한다.
실제 그 실행의 입력으로 다시 판정하면 **신규 2건 / 재색인 0건**이 나온다
(수정 전에는 신규 0건 / 재색인 2건이었다).

이 2건의 알림은 이미 지나갔다. 지금 억지로 다시 보내지 않는다 — 데이터에는
정상적으로 들어와 있고 화면에도 보인다. 다음 정기 실행부터는 같은 상황에서
정상적으로 알림이 나간다.
