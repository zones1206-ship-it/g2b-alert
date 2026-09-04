# dueDate 누락 33건 전수 기록 — 지시문 No.018

조사 시점: No.017 완료 상태(`14e89bc`), 전체 70건.

## 누락 현황 (Before)

| 출처 | 전체 | 있음 | 없음 | 누락률 |
|---|---|---|---|---|
| JETRO | 23 | 4 | 19 | 82% |
| EBNEW | 21 | 13 | 8 | 38% |
| KANC | 10 | 5 | 5 | 50% |
| KOTRA | 1 | 0 | 1 | 100% |
| MOFCOM | 8 | 8 | 0 | 0% |
| NNFC | 3 | 3 | 0 | 0% |
| KRISS | 2 | 2 | 0 | 0% |
| ITRI | 1 | 1 | 0 | 0% |
| KAIST | 1 | 1 | 0 | 0% |
| **합계** | **70** | **37** | **33** | **47%** |

noticeType별 누락: 정식입찰 28 · 낙찰·수주결과 4 · 수출상담회 1

## JETRO 19건 Before / After

파서 수정 뒤 실제 원문(잘리지 않은 것)을 다시 받아 확인한 결과다.

| # | id | 제목 | Before | 원문 근거 | After | TYPE |
|---|---|---|---|---|---|---|
| 1 | `jetro399917` | 고전압 반도체 소자 파라미터 분석기 1식 | null | Time-limit for Tender : 17 : 00, September 24, 2026 | **2026-09-24** | A |
| 2 | `jetro399065` | CMOS 장치 특성 평가용 반도체 분석기 1식 | null | Time-limit for Tender : 17 : 00, September 15, 2026 | **2026-09-15** | A |
| 3 | `jetro398989` | GE 반도체 검출기 1식 | null | Time-limit for tender : 5 : 00 P.M. September 15, 2026 | **2026-09-15** | A |
| 4 | `jetro402047` | 단일 웨이퍼 스핀 식각 장비 1식 | null | Time-limit of tender : 3 : 00 PM, 26, October, 2026 | **2026-10-26** | A |
| 5 | `jetro402048` | 단일 웨이퍼 스핀 식각 장비 1식 | null | Time-limit of tender : 3 : 00 PM, 26, October, 2026 | **2026-10-26** | A |
| 6 | `jetro401480` | 8inch 웨이퍼 검사를 위한 레이저 공초점 현미경 1식 | null | Time-limit for Tender : 17 : 00, October 20, 2026 | **2026-10-20** | A |
| 7 | `jetro400024` | CMOS 실리콘 간단한 TEG 및 고속 MRAM 시험 칩 제작 | null | Deadline for submission of documents : 17 : 00 1 September, 20 | **2026-09-01** | A |
| 8 | `jetro399203` | 동위원소 농축 12 인치 SOI 웨이퍼 1식 | null | Time-limit for Tender : 17 : 00, September 17, 2026 | **2026-09-17** | A |
| 9 | `jetro398529` | 65nm CMOS 공정 전체 마스크 및 웨이퍼 제작 1식 | null | Time limit of the documents : 17 : 00 17 August, 2026 | **2026-08-17** | A |
| 10 | `jetro401190` | 클린룸를 위한 옥외 공조기(AHU)의 제작, B 높은 Q CW | null | Time limit of tender : A 17 : 00 24 September, 2026 B 17 : 00  | **2026-09-24** | A |
| 11 | `jetro397770` | 멀티 챔버 멀티 타깃 코스퍼터링 장비 1식 | null | Time-limit of tender : 3 : 00 PM, 31, August, 2026 | **2026-08-31** | A |
| 12 | `jetro399379` | 건식 식각 장비 2식 | null | Time limit of tender : 17 : 00 24 September, 2026 | **2026-09-24** | A |
| 13 | `jetro399204` | 박막 리튬 Niobate를 위한 건식 식각 장비 1식 | null | Time-limit for Tender : 17 : 00, September 17, 2026 | **2026-09-17** | A |
| 14 | `jetro398518` | Dry 식각 장비 for Metals 1식 | null | Deadline for submission of documents : 17 : 00 28 August, 2026 | **2026-08-28** | A |
| 15 | `jetro397774` | 전자빔 리소그래피 장비 자동 취급 및 PEB 단위 장착 1식 | null | Time-limit of tender : 3 : 00 PM, 31, August, 2026 | **2026-08-31** | A |
| 16 | `jetro401484` | LED 대형 스크린 전시 장비의 일괄 | null | Time limit of tender : By 10 : 00 29 October 2026. | **2026-10-29** | A |
| 17 | `jetro401215` | 총 정보 디스플레이 유닛 유형 TDU-14C의 부속, 등 | null | Time-limit for the submission of tenders ① By electronic biddi | **2026-10-15** | A |
| 18 | `jetro400227` | Manufacture of one ⑴ set of hardwa | null | Time-limit for the submission of tenders ① By electronic biddi | **2026-10-06** | A |
| 19 | `jetro398940` | Advertising 디스플레이 Services for Dig | null | Time-limit for tender : 16 : 00, 15 September, 2026 | **2026-09-15** | A |

**19건 전부 복구.** 원문에 마감일이 없어 못 채운 건은 0건이다.

## 파서 실패 원인

| 원인 | 내용 | 영향 |
|---|---|---|
| 라벨 표기 | 실제는 `Time-limit`(하이픈)인데 정규식은 `time limit`(공백)만 찾았다 | 대부분 |
| 날짜 형식 | `24 September, 2026` / `29 October 2026` 같은 일 우선 표기 미지원 | 일부 |
| 마감 선택 | 한 공고에 자격서류 마감과 입찰 마감이 둘 다 있을 때 앞의 것을 골랐다 | 2건 |

호출 자체는 정상이었다 — `build_item`에서 잘리지 않은 원문으로 부르고 있다.
(저장된 `originalDescription`은 1200자로 잘리지만 파싱에는 쓰이지 않는다.)

## 실제 확인된 날짜 형식

| 형식 | 예 | 건수 |
|---|---|---|
| 월 먼저, 축약 | `Sep. 25, 2026` | 2 |
| 월 먼저, 전체 | `September 15, 2026` | 6 |
| 일 먼저, 쉼표 | `31, August, 2026` | 4 |
| 일 먼저 | `24 September, 2026` | 5 |
| 일 먼저, 쉼표 없음 | `29 October 2026` | 2 |

예상 형식을 넣지 않고 위 다섯 가지만 지원한다.

## 나머지 14건

| 출처 | 건수 | TYPE | 판단 근거 |
|---|---|---|---|
| EBNEW | 4 | **C** | 낙찰·수주결과 — 이미 끝난 결과 공고라 입찰 마감일이 없는 것이 정상 |
| EBNEW | 4 | **B** | 재입찰 정정·변경 공고 — 원문에 `投标截止时间`·`截止时间`·`开标时间` 어느 것도 없다(4건 모두 직접 확인) |
| KANC | 5 | **A** | 원문에 `입찰서 제출시한`/`제출기한`이 있는데 파서에 라벨이 없었다 → 복구 |
| KOTRA | 1 | **B** | 수출상담회, 본문이 `일시/장소 : 연간 / 온오프라인 병행` — 특정 마감일이 없다 |

## 처리 요약

| TYPE | 건수 | 처리 |
|---|---|---|
| A (파서가 못 읽음) | **24** (JETRO 19 + KANC 5) | 파서 수정으로 복구 |
| B (원문에 마감일 없음) | **5** (EBNEW 4 + KOTRA 1) | null 유지 |
| C (마감일이 필요 없는 공고) | **4** (EBNEW 낙찰·수주결과) | null 유지 |

날짜를 만들어 채운 건은 **0건**이다.
