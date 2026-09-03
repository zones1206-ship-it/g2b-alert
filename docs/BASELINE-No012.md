# Baseline 백업 — 지시문 No.012 작업 직전 상태

- 기준 commit SHA: `99f82ad5a1a56ef510b9480b8dd0001d4b24dd7c`
- 백업 파일: `data/backup/announcements-baseline-No012.json` (전 필드 원본 그대로, 가공 없음)
- 백업 시점 `updatedAt`: 2026-09-03T14:44:02+00:00
- 총 공고: **67건**

## 장비 판정 분포
- 장비: 45건
- 제외: 21건
- 검토 필요: 1건

## 출처별 건수
- JETRO: 23건
- EBNEW: 20건
- KANC: 9건
- MOFCOM: 8건
- NNFC: 3건
- KRISS: 2건
- KAIST: 1건
- KOTRA: 1건

## 수집원 상태(sourceHealth)

| 출처 | ok | 연속 실패 | 장애알림 발송됨 |
|---|---|---|---|
| KANC | True | 0 | False |
| NNFC | True | 0 | False |
| KOTRA | False | 2 | False |
| EBNEW | True | 0 | False |
| MOFCOM | True | 0 | False |
| KRISS | True | 0 | False |
| JETRO | True | 0 | False |
| DGIST | True | 0 | False |
| ITRI | True | 0 | False |
| KAIST | True | 0 | False |

## 백업된 필드 (전 필드)

`attachments`, `budget`, `classificationStatus`, `contractMethod`, `country`, `countryCode`, `currency`, `deliveryCondition`, `description`, `detectedLanguage`, `dueDate`, `eligibility`, `equipmentName`, `equipmentReason`, `equipmentStatus`, `eventPeriod`, `firstSeenAt`, `g2bBidNo`, `id`, `industry`, `keywords`, `noticeType`, `org`, `originalOrg`, `originalSummary`, `originalTitle`, `originalUrl`, `paymentCondition`, `postedDate`, `process`, `projectNo`, `quantity`, `region`, `source`, `sourceCode`, `sourceCountry`, `sourceSiteUrl`, `sourceType`, `status`, `title`, `translatedSummary`, `translatedTitle`, `translationIncomplete`, `url`

총 44개 필드. 원본 JSON을 그대로 보존했으므로 필드 누락은 없다.

## 복원 방법

```bash
cp data/backup/announcements-baseline-No012.json data/announcements.json
```

또는 `git show 99f82ad5a1a56ef510b9480b8dd0001d4b24dd7c:data/announcements.json > data/announcements.json`

## No.012 변경 후 불변식 검증 결과

- 총계 67건 유지 / 장비 45 · 검토 필요 1 · 제외 21 유지
- `firstSeenAt` 변경 0건
- 공고 signature 추가 0건 · 소멸 0건 → Telegram 재발송 0건
- `sourceHealth` 변경 없음
- 변경된 필드는 `url` 20건, `originalUrl` 20건뿐이며 전부 EBNEW `http://` → `https://` 스킴 정규화
