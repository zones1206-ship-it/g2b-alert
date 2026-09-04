# 완료 보고 — 지시문 No.020

No.019 미완료 종결: MOFCOM 신규 누락 수정 검증 / firstSeenAt 복구 /
Manual Health UI 분리 / 정기 복구 알림 준비

작성 2026-09-04

---

## 1. 결과: PARTIAL

한 가지를 빼고 모두 끝냈다. **KAIST 복구 Telegram의 실제 발송 검증만
남았고, 다음 정기 실행(내일 07:00 KST)에서 확인된다.** 복구 알림은 정기
실행에서만 나가도록 만든 것이 이번 설계라, 수동 실행으로는 실증할 수
없다. 대신 synthetic 테스트와 dry-run으로 "무엇이 나갈지"까지 확정했다.

## 2. Baseline (작업 전)

전체 65건 / 장비 47 / 제외 18 / 검토 필요 0.
MOFCOM 11건, dueDate 없음 9건.

| 출처 | ok | 연속 실패 | failureAlertSent | lastRunMode |
|---|---|---|---|---|
| KAIST | true | 0 | **true** | manual-validation |
| KOTRA | true | 0 | false | manual-validation |

## 3. MOFCOM 문제 2건

| | 신규 A | 신규 B |
|---|---|---|
| id | `mofcomff8080819e42905601a03d8e304b2286` | `mofcomff8080819e42905601a06643a3816a91` |
| projectNo | 4197-264BOECDCZ02/**02** | 4197-264BOECDCZ02/**02** |
| url | …/202608/ff8080819e42905601a03d8e304b2286.html | …/202609/ff8080819e42905601a06643a3816a91.html |
| 게시 / 마감 | 2026-08-26 / 2026-09-16 | 2026-09-03 / 2026-09-24 |
| 비교 대상 | `…04c2292` (/03) | `…3806a81` (/03) |

## 4. 실제 별개 로트가 맞다 — 원문 근거

signature 비교로 결론내지 않고 원문 네 건을 모두 열었다.

- `招标项目编号` 이 **/02 와 /03 으로 다르다**
- 입찰문서 가격이 다르다 — **/02 는 ￥1500/$250, /03 은 ￥3000/$500**
- URL이 다르고 네 건 모두 살아 있다

같은 프로젝트의 규모가 다른 별개 로트다.

## 5. firstSeenAt 감사와 복구

git 이력 142개 커밋을 전수 조사해 각 id의 최초 등장 시점을 찾았다.

| id | 실제 최초 등장 | 저장돼 있던 값 | 판정 |
|---|---|---|---|
| …4b2286 (/02) | 2026-09-03T09:33:22+09:00 (커밋 89d01e7) | 2026-09-03T10:27:54Z | **틀림** |
| …816a91 (/02) | 2026-09-04T06:34:38Z (커밋 abbfbcb) | 2026-09-03T10:27:54Z | **틀림** |
| …04c2292 (/03) | 2026-09-03T10:27:54Z | 같음 | 정상 |
| …3806a81 (/03) | 2026-09-03T10:27:54Z | 같음 | 정상 |

둘 다 로트 /03 의 값을 물려받고 있었다. 근거값으로 바로잡았다.

- …4b2286 → **2026-09-03T09:33:22+09:00** (커밋 89d01e7에 이 id로
  실제 저장돼 있던 값 그대로. 날짜를 새로 만들지 않았다)
- …816a91 → **2026-09-04T06:34:38+00:00** (최초 등장한 실행의 updatedAt)

데이터 파일에서 바뀐 줄은 정확히 2줄이고, 대상 외 변경은 0건이다.

한 가지 덧붙일 사실 — **신규 A는 09-03 09:33에 이미 있었다가 43개 커밋
동안 사라졌다가 돌아온 공고**다. "이번에 처음 나타난 것"은 신규 B뿐이다.
사라졌던 구간의 원인은 이번 범위가 아니라 손대지 않았다(9절 참고).

## 6. 소급 발송하지 않았다

누락됐던 Telegram 2건을 지금 다시 보내지 않았다. 데이터에는 정상적으로
들어와 있고 화면에도 보인다. 목표는 앞으로 누락되지 않게 만드는 것이다.

## 7. Manual 실패가 사용자 화면을 오염시켰다 — 고쳤다

No.019에서 Telegram만 분리했는데, 수동 검증 실패가 여전히 `ok: false` 로
남아 **사용자 화면에 장애 배너로 떴다**. 실증했다.

배너 조건에 `lastRunMode !== "manual-validation"` 을 더했다. 이미 있는
필드를 쓰므로 sourceHealth schema는 그대로다.

브라우저에서 두 경우를 직접 확인했다.

| 상태 | 배너 |
|---|---|
| manual-validation 실패 | **표시 안 됨** |
| scheduled 실패 | 표시됨 (⚠ 수집 장애 1곳) |

수동 실행 실패는 sourceHealth와 Actions 로그에 그대로 남는다 — 숨기는
것이 아니라 사용자 화면에만 올리지 않는다.

## 8. KAIST / KOTRA

KAIST는 `failureAlertSent: true` 가 남아 있다. No.018에서 장애 알림이
나갔고, No.019 수동 실행에서 정상 수집됐지만 수동 모드라 복구를 알리지
않았기 때문이다. **JSON을 손으로 지우지 않았다** — 사용자가 이미 장애
알림을 받았으므로 복구 알림이 가는 것이 맞다.

다음 정기 실행에서 나갈 알림을 dry-run으로 확인했다.

```
[장비 프로젝트 레이더 수집 복구]
출처: KAIST (한국)
상태: 정상 수집 복구
이번 수집: 3건
```

**KAIST 복구 1건뿐이다.** KOTRA는 `failureAlertSent: false` 라 알림이 없다.

### KAIST 원인은 아직 확정하지 않는다

확정된 사실만 적는다.

- KAIST 서버는 정상이다 — 로컬에서 TCP 연결 0.04초, 목록 3페이지 각각
  0.4~1.1초
- 타임아웃 값 부족이 아니다 — 설정 12초, 실측 최대 1.06초
- Actions 러너에서만 실패했고, 간격을 둔 다음 실행에서는 성공했다

러너 IP 문제인지 반복 접근 제한인지 일시 네트워크 문제인지는 **이 데이터로
구분할 수 없다.** "반복 실행 때문에 차단됐다"고 단정하지 않는다.

KOTRA는 기존 판정을 유지한다 — "GitHub Actions runner IP에 따른
선택적/부분적 접속 차단". 로컬에서는 24.3초에 1건 정상 수집된다.

## 9. 데이터 무결성

Baseline 대비 변경.

| 필드 | 변경 |
|---|---|
| 건수 (65) | 추가 0 / 사라짐 0 |
| title / org / dueDate | 0건 |
| equipmentStatus / equipmentReason | 0건 |
| industry / process | 0건 |
| **firstSeenAt** | **2건** (의도한 복구) |

판정 재계산 불일치 0건, id 중복 0, dueDate 없음 9건 유지.

## 10. 회귀 (No.018 / No.019 보호)

- dueDate 없음 9건 유지
- JETRO 동일 제목 2건(`jetro402047` / `402048`) 둘 다 유지
- 동일 projectNo 정정·차수 공고 보호 유지
- 일정 탭 9월 33건이 데이터와 **전부 일치**
- 한자·가나 잔여 0, 콘솔 오류 0
- Desktop / Mobile 정상

## 11. 테스트

**187건 전체 PASS** (No.019의 181 → 187).

새로 추가한 6건은 수정 전 코드에서 실제로 실패하는 것을 확인했다.

CASE A~J 매핑.

| CASE | 어디서 | 결과 |
|---|---|---|
| A signature 동일·projectNo 다름 → 별개 | LotIdentityLeakTest | PASS |
| B id만 변경 → reindex | LotIdentityLeakTest | PASS |
| C 신규 로트 → 새 firstSeenAt + 신규 알림 | LotIdentityLeakTest | PASS |
| D JETRO signature 충돌 → 둘 다 유지 | AnnouncementIdentityTest | PASS |
| E 동일 projectNo 정정공고 → 유지 | AnnouncementIdentityTest | PASS |
| F manual 실패 → 카운터 불변 | RunModeHealthTest | PASS |
| G manual 실패 → 배너 없음 | HealthBannerScopeTest | PASS |
| H scheduled 3회 실패 → 장애 1회 | RunModeHealthTest | PASS |
| I scheduled 복구 → 복구 1회 | RecoveryAlertOnceTest | PASS |
| J 복구 후 정상 반복 → 추가 0 | RecoveryAlertOnceTest | PASS |

## 12. Actions 실행

**0회.** 지시대로 synthetic / 로컬 / 브라우저 실증만 했다. No.019 1차
실행 결과를 재분석했을 뿐 새로 돌리지 않았다.

## 13. 남은 문제

1. **KAIST 복구 Telegram 실제 발송 검증** — 내일 07:00 KST 정기 실행에서
   확인. 1건만 나가야 하고, 그 다음 정기 실행에서는 0건이어야 한다.
2. **신규 A가 43개 커밋 동안 사라졌던 원인** — 마감 09-16으로 진행 중인
   공고였는데 데이터에서 빠져 있었다. Active carry-forward가 잡지 못한
   경로가 남아 있을 수 있다.
3. KAIST / KOTRA의 Actions 러너 실패 원인 미확정.

## 14. 다음 우선순위

1. 정기 실행에서 KAIST 복구 알림 1회 확인 (남은 문제 1)
2. 신규 A가 사라졌던 구간 추적 — 진행 중 공고 소실 경로가 더 있는지
3. 러너 실패 통계 축적 (KOTRA IP 로그와 대조)
