# 장비 프로젝트 레이더 (g2b-alert)

반도체·디스플레이·TGV(유리기판) 장비를 실제로 구매·제작·설치하는 전문
기관의 입찰/프로젝트 정보를 모아 보여주는 개인용 알림 대시보드.
순수 정적 HTML/CSS/JS + GitHub Actions로 구성했으며, Netlify 등
외부 호스팅은 사용하지 않는다.

> 저장소 이름은 `g2b-alert`로 시작했지만, 나라장터(G2B) 전체 공고를
> 키워드로 필터링하는 방식은 실제 장비 구매 공고 비율이 낮고(연구용역/
> 교육/위탁 사업이 다수 혼재) 502 오류·과도한 필터링 로직 문제로 제거했다.
> 지금은 실제 장비를 발주하는 전문기관(한국나노기술원 등)의 공개 게시판을
> 직접 수집하는 방식으로 운영한다.

## 수집 출처

현재 `scripts/fetch_announcements.py`의 `COLLECTORS`에 등록돼 실제로 도는 수집원은 10곳이다.

| 출처 | sourceCode | 국가 | 방식 |
|---|---|---|---|
| 한국나노기술원 (KANC) | `KANC` | 국내 | 공개 입찰공고 게시판 HTML 수집 (공식 API/RSS 없음) |
| 나노종합기술원 (NNFC) | `NNFC` | 국내 | 공개 입찰공고 게시판 HTML 수집 (공식 API/RSS 없음) |
| 한국표준과학연구원 (KRISS) | `KRISS` | 국내 | 공개 입찰공고 게시판 HTML 수집. KANC와 같은 4단계 관련성 판정 로직 재사용 |
| 대한무역투자진흥공사 (KOTRA) | `KOTRA` | 해외(프로젝트 대상국 기준) | "사업신청" 목록 중 반도체/디스플레이/TGV 관련 프로젝트만 HTML 수집 |
| 중국 비롄왕(必联网/EBNEW) | `EBNEW` | 중국(China Site) | 로그인 불필요, 실제 검색 API(POST) 확인 후 반도체/디스플레이/TGV 키워드로 수집. 제목은 C″ 번역(용어집 보호 + 필요한 구간만 Argos zh→en→ko, 검증 실패 시 기존 번역 유지), 원문 보존 |
| 중국국제초표망 (MOFCOM) | `MOFCOM` | 중국(China Site) | `chinabidding.mofcom.gov.cn` 검색 API(POST). 관련성 판정은 EBNEW 로직 재사용, 번역은 기존 용어집 방식 유지(PoC 결과 이미 우수) |
| JETRO (일본) | `JETRO` | 일본 | 일본 정부조달 데이터베이스의 공개 JSON 목록 + 상세 HTML. AIST/RIKEN/NIMS/일본 대학 공고가 여기 모인다 |
| DGIST (한국) | `DGIST` | 국내 | 입찰정보 게시판 HTML 수집 (상세는 버튼의 `data-key-no` 값으로 열림) |
| ITRI (대만) | `ITRI` | 대만 | 採購資訊系統 詢價案 공개 목록 HTML. 번체 중국어라 수집기 내부 번체 용어집으로 한국어 표기 |
| KAIST (한국) | `KAIST` | 국내 | 입찰/구매 공고 게시판 HTML. 상세가 나라장터로 바로 연결돼 `g2bBidNo`를 함께 저장 |

> MOFCOM 서버는 OpenSSL 3.x의 기본 보안수준(SECLEVEL=2)이 요구하는 cipher를
> 제공하지 않아 TLS handshake 자체가 실패한다. 이 수집기만 SSL 컨텍스트에서
> cipher 수준을 낮춰(`DEFAULT@SECLEVEL=1`) 연결한다 — 인증서 검증은 그대로
> 유지하며, 로그인/CAPTCHA 등 접근 제한을 우회하는 것이 아니다.

> KOTRA는 로컬에서는 0.4초에 정상 응답하지만 **GitHub Actions 러너에서는
> TCP 443 연결 자체가 차단된다.** 러너에서 직접 진단한 결과: DNS는 정상
> 해석되나 TCP 연결 실패, `curl`은 `http=000`, User-Agent/Accept/Referer/
> XHR/GET 등 5가지 요청 조합이 모두 timeout, 비-AJAX 공개 HTML 페이지도
> 동일하게 실패했다. 애플리케이션 레벨(헤더·요청 방식) 문제가 아니라
> Actions(Azure) IP 대역 차단으로 판단되며, 차단 우회는 하지 않는다.
> 따라서 Actions 실행분에서는 KOTRA가 계속 실패하고, 이전에 수집된
> 데이터를 유지한 채 아래 Health Check로 실패 사실을 노출한다.

### 조사했으나 보류한 신규 후보 (2026-09 조사)

| 후보 | 상태 | 이유 |
|---|---|---|
| GeBIZ (싱가포르) | 보류 | 로그인 없이 목록은 보이지만 JSF(ViewState) 앱이라 검색·페이징이 POST 부분요청으로만 동작하고, 컴포넌트 ID(`j_idt179` 등)가 배포마다 바뀌어 안정적인 수집이 어렵다. 실제로 검색 POST를 시도했으나 키워드가 적용되지 않았다(700건 그대로) |
| MIMOS (말레이시아) | 보류 | 입찰 목록이 AJAX로 로드돼 공개 HTML에 없고, **Actions에서 TLS 인증서 체인 검증 실패**(서버가 중간 인증서를 보내지 않음, certifi로도 실패). 인증서 검증 비활성화는 하지 않는다 |

KIMM/KITECH/KETI/EBIZ4U는 추가 예정 (구조 분석 후 실제 수집 코드가
검증된 것만 `COLLECTORS`에 등록한다 — UI에 이름만 먼저 올리지 않는다).

KDIA(한국디스플레이산업협회)는 중국 디스플레이 비딩정보 출처로 검토했으나,
조사 결과 월간 산업동향 리포트 게시판만 있고 입찰/비딩 게시판이 없어
보류 중이다. cebpubservice.cn(중국 입찰투찰 공공서비스 플랫폼)과
chinabidding.com.cn(중국 구매·입찰망)은 알리바바 클라우드 WAF/CDN이
자동화 요청을 명시적으로 차단하고, CXMT SRM 공급사 포털은 로그인이
필요해 — 로그인/CAPTCHA/접근제한 우회를 하지 않는다는 원칙에 따라
셋 다 보류 중이다.

새 수집원은 `scripts/collectors/`에 모듈 하나만 추가하면 붙일 수 있는
구조로 되어 있다 (아래 "새 수집원 추가 방법" 참고).

## 구성

```
g2b-alert/
├── index.html                          화면 (홈/공고/통계/일정/설정 5탭 + 하단 네비)
├── style.css
├── app.js                               필터링(분야/유형/지역/신규), D-day·국가·출처·유형·번역미완료 뱃지,
│                                        수집 실패 경고 표시, localStorage 저장
├── data/announcements.json              수집된 데이터 + 수집원 상태(sourceHealth). Actions가 매일 갱신
├── requirements.txt                     pypinyin (중국어 로마자 표기 폴백용)
├── copy.md                              화면에 실제로 쓰이는 문구 정리 문서
├── scripts/
│   ├── fetch_announcements.py           수집기를 실행하는 orchestrator + Health Check 기록
│   ├── notify_telegram.py               신규 공고만 Telegram으로 발송 (Actions에서 별도 스텝으로 실행)
│   └── collectors/
│       ├── common.py                    공유 상수(카테고리, 출처 목록, TGV 키워드 등)
│       ├── kanc.py / nnfc.py / kriss.py   국내 기관 입찰공고 게시판 수집기
│       ├── kotra.py                     KOTRA 사업신청 목록 수집기
│       ├── ebnew.py / mofcom.py         중국 사이트 수집기 (China Site)
│       ├── zh_translate.py              용어집 기반 최선노력 중국어 번역(MOFCOM·발주처·요약)
│       └── zh_ko_argos.py               EBNEW 제목 전용 C″ 번역(용어집 보호 → 필요한 구간만
│                                        zh→en→ko → 검증 → 실패 시 zh_translate 결과 유지)
├── security/cloudflare-worker/          접속 게이트(비밀번호) Worker 코드 + 배포 안내
└── .github/workflows/
    ├── fetch-announcements.yml          매일 1회 자동 수집 + Telegram 알림 + 데이터 커밋
    ├── telegram-test.yml                Telegram 개인 알림 수동 테스트 (workflow_dispatch)
    └── telegram-personal-chat-discovery.yml   개인 Chat ID 확인용 (workflow_dispatch)
```

## 데이터 구조

`data/announcements.json`의 최상위는 아래 3개 키다.

```json
{
  "updatedAt": "마지막 수집 실행 시각 (ISO 8601)",
  "sourceHealth": { "KANC": { "...": "수집원별 상태, 아래 Health Check 참고" } },
  "items": [ { "...": "공고 1건" } ]
}
```

각 공고 아이템의 필드다. **원문에서 확인되지 않는 값은 전부 `null`이며,
화면은 이를 "확인 필요"/"정보 없음"으로 표시할 뿐 임의로 값을 만들어내지 않는다.**
출처에 따라 채워지지 않는 필드가 있고(예: 중국 사이트만 번역 관련 필드를 가짐),
프론트엔드는 없는 필드를 만나면 표시를 생략한다.

```json
{
  "id": "출처 내 고유 ID (sourceCode 접두사 포함, 예: kriss123)",
  "title": "공고명/프로젝트명 (중국 출처는 번역된 제목)",
  "org": "발주기관/수요기업",
  "country": "국내 | 중국 | ...",
  "countryCode": "KR | CN | ...",
  "region": "지역 또는 null",
  "status": "진행중 등 원문에서 확인 가능한 경우만 (화면은 마감일이 지났으면 '마감'으로 표시)",
  "dueDate": "YYYY-MM-DD 또는 null (없으면 화면에 '마감일 확인 필요')",
  "postedDate": "YYYY-MM-DD 또는 null",
  "eventPeriod": "행사 기간 또는 null (KOTRA 등)",
  "keywords": ["반도체 장비", "디스플레이 장비", "TGV 장비"],
  "classificationStatus": "미분류/검토 필요 (분야를 확정하지 못한 경우만)",
  "budget": "예산 문자열 또는 null",
  "currency": "통화 (외화는 임의 환산하지 않고 원래 통화 유지)",
  "contractMethod": "계약방식 또는 null",
  "deliveryCondition": "인도조건/납품장소 또는 null",
  "paymentCondition": "지급조건 또는 null",
  "eligibility": "참가자격 또는 null",
  "description": "핵심 요약(원문 기반, 지어내지 않음) 또는 null",
  "attachments": [{ "name": "파일명", "url": "다운로드 URL" }],
  "url": "원문 공고 URL",
  "originalUrl": "원문 URL(명시적 보관)",
  "source": "한국나노기술원 | ...",
  "sourceCode": "KANC | NNFC | KRISS | KOTRA | EBNEW | MOFCOM",
  "sourceSiteUrl": "출처 사이트 URL",
  "sourceCountry": "출처 사이트의 국가 코드 (예: CN — 프로젝트 대상국과 다른 개념)",
  "sourceType": "China Site 등",
  "detectedLanguage": "zh-CN 등",
  "noticeType": "사전규격 | 정식입찰 | 프로젝트 정보 | 공급사 모집 | 수출상담회 | 구매상담회 | 낙찰·수주결과 | null",
  "projectNo": "공고번호 또는 null",
  "g2bBidNo": "본문에 나라장터 공고번호가 있으면 추출 (KRISS 등)",
  "firstSeenAt": "우리 시스템이 처음 발견한 시각 — NEW 배지(48시간)와 Telegram 발송 기준",
  "translatedTitle": "번역 제목 (중국 출처)",
  "originalTitle": "원문 제목 (항상 보존)",
  "translatedSummary": "번역 요약",
  "originalSummary": "원문 요약",
  "originalOrg": "원문 발주기관명",
  "translationIncomplete": "true면 번역이 불완전(로마자 폴백) — 화면에 '번역 미완료' 배지 표시"
}
```

### 분야가 확정되지 않은 공고

수집기가 분야를 하나도 확정하지 못하면 `keywords`가 빈 배열이 되고
`classificationStatus`에 `"미분류/검토 필요"`가 들어간다. 화면에서는 이런
공고를 **"기타 / 미분류" 그룹**으로 목록 맨 아래에 따로 보여준다 —
분야 그룹에만 의존하면 이 공고들이 화면에서 통째로 사라지기 때문이다.

## 1. GitHub Pages 활성화

1. 저장소 Settings → Pages
2. Source: `Deploy from a branch`
3. Branch: `main` / `/ (root)` 선택 → Save
4. 몇 분 뒤 `https://<username>.github.io/g2b-alert/` 에서 확인 가능

## 2. GitHub Actions 자동 수집

- `.github/workflows/fetch-announcements.yml`(워크플로 이름: **Fetch Project
  Radar Announcements**)이 매일 07:00(KST)에 실행되어
  `scripts/fetch_announcements.py`(orchestrator)가 등록된 모든 수집기를
  실행하고 결과를 합쳐 `data/announcements.json`에 저장한다.
- 실행 순서: 이전 데이터 스냅샷 → 수집 → Telegram 신규 알림 → 데이터 커밋.
- 저장소 Actions 탭에서 `Run workflow`로 즉시 수동 실행도 가능하다 (workflow_dispatch).
- 수집 자체에는 인증키가 필요 없다(전부 공개 게시판/공개 검색). Telegram
  알림에만 Repository Secret이 필요하다(아래 참고).

### 수집 실패 시 동작 (기존 데이터 유지)

**수집기 하나가 실패해도 다른 수집기와 기존 데이터에 영향을 주지 않는다.**
실패한 수집원은 이번 실행분을 건너뛰고, 이전에 저장된 해당 출처(`sourceCode`)의
데이터를 그대로 유지한다. 이 방식은 일시적 장애로 데이터가 사라지는 것을
막아주지만, **아무 표시가 없으면 낡은 데이터를 최신으로 오인하게 되므로**
아래 Health Check로 실패 사실을 함께 남긴다.

### 수집원 Health Check

매 실행마다 수집원별 상태를 `data/announcements.json`의 `sourceHealth`에 기록한다.

| 필드 | 의미 |
|---|---|
| `ok` | 이번 실행에서 새로 수집됐는지 |
| `lastStatus` | `정상` / `오류` / `결과 없음(기존 유지)` |
| `lastError` | 오류 요약(있는 경우) |
| `collectedThisRun` | 이번 실행 수집 건수 |
| `lastRunAt` | 이번 실행 시각 |
| `lastSuccessAt` | 마지막으로 정상 수집된 시각 (실패해도 이전 값 유지) |
| `consecutiveFailures` | 연속 실패 횟수 (성공하면 0) |

- **Actions 로그**: 실패한 수집원은 `::warning::`으로 출력돼 실행 화면 상단
  주석으로 뜬다. 워크플로 자체는 계속 성공으로 끝나되(다른 수집원까지 막지
  않기 위해) 장애는 눈에 보이게 한다.
- **화면**: 실패 중인 수집원이 있으면 헤더에 경고가 표시된다
  (예: `⚠ 수집 실패 중: KOTRA(마지막 정상 수집 …) — 해당 출처는 이전에
  수집된 공고가 그대로 표시됩니다.`). 전부 정상이면 아무것도 표시하지 않는다.

### Telegram 알림 (실제 운영 중)

- `scripts/notify_telegram.py`가 수집 직후 별도 스텝으로 실행돼, 이전 스냅샷과
  비교해 **새로 추가된 공고만** 발송한다. "신규"의 기준은 공고 `id`가 이전
  스냅샷에 없던 경우다(내용이 바뀐 기존 공고는 신규로 보지 않는다).
- 1회 실행당 최대 20건까지만 보낸다(연동 첫날 등 대량 발송 방지).
- Repository Secret `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`가 필요하며,
  둘 중 하나라도 없으면 아무것도 보내지 않고 조용히 종료한다(파이프라인은
  실패하지 않는다).
- 이 스크립트는 검색/필터/UI 로직과 완전히 분리돼 있다.
- 설정 화면의 "텔레그램으로 알림 받기" 버튼은 이미 연결돼 있다는 안내만
  띄운다(구독 설정 UI가 아니라 안내용이다).

### KANC (한국나노기술원)

- 공식 API/RSS가 없어 공개 입찰공고 게시판(`https://kanc.re.kr/gnb04/snb02_01.do`)
  HTML을 직접 수집한다 (로그인/CAPTCHA 없는 공개 게시판만 대상).
- 분류는 2단계:
  1. "매각", "취소"가 제목에 있으면 무조건 제외
  2. "장비운용/운용용역/운영용역" 등 장비 **운영** 용역 패턴이면 제외
     ("장비"라는 단어가 있어도 장비 구매가 아니라 인력/용역업체 선정인
     경우가 있어, 이 패턴은 장비 신호보다 우선해서 제외한다)
  3. `EQUIPMENT_INCLUDE_TERMS`(구매/제작/설치/장비/설비/사전규격 등) 신호가
     있으면 포함 (그 외 서비스성 단어가 같이 있어도 장비 신호 우선)
  4. 장비 신호 없이 서비스성 단어(위탁/교육/행사/컨설팅 등)만 있으면 제외
  5. 둘 다 없으면 기본 제외
- `noticeType`으로 "사전규격"/"정식입찰"을 구분하며, 사전규격공개는
  제외 대상이 아니라 우선 수집 대상이다.
- 목록 페이지에는 마감일이 없어 상세페이지에서 정규식으로 추출한다.
  추출한 마감일이 등록일보다 이전이면(원문 게시물 자체의 오타 가능성)
  다음 후보 패턴으로 대체하며, 끝내 찾지 못하면 `dueDate: null`로 두고
  화면에 "마감일 확인 필요"로 표시한다(임의로 날짜를 만들어내지 않는다).
- 예산(`사업예산 ... KRW`), 계약방법, 인도조건, 지급조건, 첨부파일(실제
  다운로드 링크 포함)도 상세페이지 본문에서 확인되는 경우에만 채운다.
- KANC는 이미 반도체/나노 장비 전문 게시판이라 카테고리 분류 시 넓은
  필터를 쓰지 않고, 디스플레이/TGV 신호가 명확할 때만 그쪽으로 분류하고
  나머지는 기본값으로 "반도체 장비"에 둔다. `country`/`countryCode`는
  항상 "국내"/"KR"이다.
- "TGV 장비" 분류는 `common.TGV_STRONG_TERMS`(유리기판/TGV/Glass Etching 등
  명확한 신호)가 있을 때만 인정한다. "도금"/"plating"만 있는 경우(예:
  반도체 공정용 일반 도금 장비)는 TGV로 보지 않고 다른 카테고리(기본값
  반도체 장비)로 남긴다 — "도금" 자체는 TGV 공정(Cu Plating 등)의 하위
  키워드로 `common.TGV_WEAK_PLATING_TERMS`에 남아있지만, 단독으로는
  카테고리를 결정하지 않는다.

### NNFC (나노종합기술원)

- 공식 API/RSS 확인되지 않아 공개 입찰공고 게시판
  (`https://www.nnfc.re.kr/bbs/BBSMSTR_000000000003/list.do`) HTML을
  직접 수집한다 (로그인/CAPTCHA 없는 공개 게시판, `?pageIndex=N`으로
  페이지네이션, 상세는 `view.do?nttId=...` GET 요청으로 접근 가능함을 확인).
- **분류 방식이 KANC와 다르다**: 이 게시판은 "알림마당 > 입찰공고"라는
  이름 그대로 NNFC가 직접 발주하는 조달 공고만 모아둔 전용 게시판인데,
  실제 목록을 보면 "300mm 실리콘 건식식각 공정용 칠러"처럼 장비/부품명을
  그대로 제목에 쓰고 "구매"/"장비" 같은 일반 키워드를 쓰지 않는 경우가
  많아 KANC 방식(장비 신호가 있어야 포함)을 그대로 쓰면 실제 장비 공고를
  놓치는 것을 테스트로 확인했다. 그래서 NNFC는 **기본 포함**(서비스/행사/
  교육/고도화/안전보건/결과안내 등 명백한 비-장비 신호가 있을 때만 제외)
  방식을 쓴다.
- "(제안평가 결과 안내)"처럼 이미 끝난 절차에 대한 공지는 열려있는 기회가
  아니므로 별도로 제외한다.
- 마감일/예산 라벨 표기가 문서 템플릿마다 달라("입찰마감", "견적서제출
  마감일시", "입찰서접수마감", "마감일 : 시작일~종료일" 범위 표기 등)
  여러 패턴을 순서대로 시도하고, 그래도 못 찾으면 `dueDate: null`로 둔다.
  예산도 원화(`사업예산`/`배정예산` ... 원)를 우선 찾고, 외화만 있는 경우
  (예: "배정예산 : JPY(¥) 150,000,000")는 임의로 원화 환산하지 않고
  원래 통화 그대로("JPY 150,000,000") 표시한다.

### KOTRA (대한무역투자진흥공사)

- KOTRA는 일반 입찰 사이트가 아니라 수출상담회/구매상담회/공급사 모집/
  해외 신규 투자 프로젝트 같은 "영업 기회 정보"를 다룬다. 그래서
  `noticeType`도 "사전규격"/"정식입찰"이 아니라 "프로젝트 정보"/
  "공급사 모집"/"수출상담회"/"구매상담회"로 분류한다.
- 공식 API/JSON은 없고, "사업신청" 목록이 두 개의 POST 기반 서버 렌더링
  AJAX 엔드포인트로 온다(신청기한 있는 사업 / 상시신청 가능 사업).
  페이지네이션은 `startCount=(페이지-1)*페이지크기` 오프셋 방식이며,
  짧은 간격으로 연속 요청하면 500 에러가 나는 것을 확인해 요청 사이
  2초 대기를 둔다(로그인/CAPTCHA는 없음 — 접근 제한 우회가 아니라
  요청 속도 조절이다).
- 상세페이지(`selectBizMntInfoDetail.do?dtlBizMntNo=...`)는 GET만으로
  접근 가능하며, 태그 목록(예: "truly", "디스플레이", "중국")에 실제
  국가명이 그대로 들어있어 이를 국가 판별에 사용한다. KOTRA는 국내
  기관이지만 표시되는 `country`는 **프로젝트 대상 국가**다(KOTRA 자체
  소재지가 아님) — 태그에 국가명이 없으면 "사업진행장소"(국내/해외)로
  대체하고, 그마저 없으면 "확인 필요"로 표시한다.
- 관련성 판단은 2단계: ① 목록 카드 제목에 반도체/디스플레이/TGV 관련
  키워드가 있어야 상세페이지를 가져오고 ② 상세페이지의 제목+본문+태그를
  합쳐 다시 한 번 확인한다. "세정"처럼 짧은 한글 단어는 "관세정책"
  같은 무관한 단어 속에 우연히 포함되는 오탐이 실제로 발생해(테스트로
  발견), 2글자 이하 한글 키워드는 공백으로 구분된 독립 단어일 때만
  인정하도록 처리했다.
- **마감된 프로젝트도 삭제하지 않는다.** 신규 투자·후속 프로젝트
  가능성이 있는 영업 정보이기 때문에, `status`를 "진행중"/"마감임박"/
  "마감"으로 구분해 저장하고 `scripts/fetch_announcements.py`의
  `is_still_open()`이 KOTRA는 날짜로 걸러내지 않도록 예외 처리했다.
- 예산 정보는 KOTRA 사업신청 페이지 특성상 거의 없어 대부분 `null`이며,
  화면에는 "예산 정보 없음"으로 표시된다(0원으로 표시하지 않는다).

### EBNEW (중국 비롄왕/必联网, China Site)

- 공식 API 없음. 처음엔 GET 쿼리 파라미터로 검색되는 줄 알았으나, 실제
  폼(`id="searchBidProjForm"`)을 읽어보니 **POST** `https://ss.ebnew.com/tradingSearch/index.htm`
  에 `key`(검색어)/`sortMethod=timeDesc`(최신순)/`currentPage` 필드로
  요청해야 진짜 검색이 되는 것을 확인했다(로그인 불필요, 실제 당일
  날짜 공고까지 나오는 것까지 검증함).
- `SEARCH_KEYWORDS`(반도체/디스플레이/TGV 관련 중국어 키워드 약 14개)로
  각각 검색해 후보를 모으고, 상세페이지(`www.ebnew.com/businessShow/{id}.html`,
  GET)에서 마감일/발주기관/지역/품목을 정규식으로 추출한다.
- **번역은 외부 번역 API를 쓰지 않는다.** 기본은
  `scripts/collectors/zh_translate.py`의 회사명/기술용어/행정용어 용어집
  치환이고, 용어집으로 덮지 못한 한자는 pypinyin 로마자 표기로 폴백한다.
  `originalTitle`/`originalSummary`에 원문을 항상 보존하고, 뜻을 지어내지
  않는다. 회사명은 "BOE(징둥팡)"처럼 영문명+한국식 발음을 병기한다.
- **EBNEW 제목만** `scripts/collectors/zh_ko_argos.py`(C″ 방식)를 추가로
  거친다: 회사명·전문용어·약어·세대·숫자단위를 자리표시자로 보호(양옆에
  공백을 넣어 인접 한자와 분리) → 용어집으로 덮이지 않은 구간만 Argos
  zh→en→ko(오프라인 모델, 한국어 직접 모델이 없어 영어를 경유) → 복원 →
  후처리 → 자동 검증. **숫자·약어·회사명·보호 토큰 중 하나라도 어긋나면
  결과를 버리고 기존 zh_translate 결과를 그대로 쓴다.** 모델이 없어도
  (Actions 캐시 실패 등) 용어집 경로는 그대로 동작한다.
  MOFCOM은 기존 방식이 이미 우수해 이 경로를 쓰지 않는다.
- **EBNEW 회사명·발주기관**은 `zh_ko_argos.ORG_NAME_TERMS`(EBNEW 전용 사전)를
  제목과 발주기관 양쪽에 똑같이 적용해 표기를 통일한다. 실제 운영 데이터에
  나오는 회사만 등록하며, 공식 영문명이 확인되면 "한국어 표기(공식 영문명)",
  확인하지 못하면 한국어 독음만 쓴다 — 뜻을 추측해 회사명을 지어내지 않는다.
  저장된 공고를 다시 번역할 때는 `python scripts/retranslate_ebnew.py`
  (미리보기) / `--apply`(저장) — 제목 관련 필드만 바꾸고 id는 건드리지
  않으므로 Telegram 신규 공고 재발송이 발생하지 않는다.
- 관련성 판단은 2단계(목록 제목에서 1차 필터 → 상세 확인 없이 바로 강한/
  낮은 신호 재검사)로, "세정"류 짧은 키워드의 오탐 문제는 아직 발견되지
  않았지만 KANC/NNFC/KOTRA와 같은 원칙(강한 신호 우선)을 적용한다.
- 같은 공고가 검색어마다 다른 내부 ID로 재색인되는 경우가 실제로 있어,
  제목+발행일 조합으로 2차 중복 제거를 한다.
- 예산은 상세페이지에 `采购预算`/`项目预算`/`预算金额` 같은 라벨이 있을
  때만 채우고(대부분 공개 안 됨), 외화만 있으면 임의 환산하지 않고
  원래 통화를 유지한다.
- 화면에는 `China Site` 배지(🌐)를 국가 배지 옆에 별도로 표시한다
  (예: `[중국] [China Site] [EBNEW]`).
- KOTRA와 마찬가지로 마감된 공고(특히 낙찰·수주결과)도 삭제하지 않는다.

### 새 수집원 추가 방법

1. `scripts/collectors/<이름>.py`에 `collect() -> list[dict]` 함수 구현
   (반환 스키마는 `scripts/collectors/common.py` 상단 docstring 참고)
2. `scripts/fetch_announcements.py`의 `COLLECTORS` 리스트에 추가
   (마감된 공고도 계속 보여줄 출처라면 `KEEP_EXPIRED_SOURCES`에도 추가)
3. `scripts/collectors/common.py`의 `SOURCES` 목록에 추가
4. `app.js`의 `SOURCE_LINK_LABELS`에 `{ 코드: "OO 원문 보기" }` 한 줄 추가
   (없으면 `"{source} 원문 보기"`로 자동 처리되므로 필수는 아니다)
5. `index.html`의 "수집 출처" 칩 목록과 개수 표기를 갱신

Health Check(`sourceHealth`)는 `COLLECTORS`에 등록만 하면 자동으로 따라온다.

## 3. 로컬 미리보기

정적 파일이므로 별도 빌드 없이 아무 정적 서버로 열면 된다.

```bash
cd g2b-alert
python -m http.server 8080
# http://localhost:8080 접속
```

## 아직 안 된 것 / 알려진 한계

- **KOTRA 수집이 GitHub Actions에서 실패한다** — Actions(Azure) IP 대역에서
  TCP 연결이 차단되는 것으로 확인됐다(위 수집 출처 항목 참고). 로컬 실행은
  정상이며, 실패 시 이전 데이터를 유지하고 Health Check 경고로 표시된다.
- **중국어 번역 품질** — EBNEW 제목은 C″ 방식으로 크게 개선됐지만(21건 중
  20건 채택, 한글 비중 평균 30%→50%), 발주처·요약과 MOFCOM은 여전히 용어집
  치환 + 로마자 폴백이라 상당수 공고가 `translationIncomplete`로 표시된다.
  용어집에 없는 중국 기업 브랜드명은 뜻을 지어내지 않고 로마자로 표기한다.
  원문 제목과 원문 링크는 항상 보존된다.
- **접속 게이트(Cloudflare Worker)** — 코드와 배포 안내는 있지만 실제 배포
  여부는 이 저장소에서 확인할 수 없다. 미배포 상태에서 헤더의 "로그아웃"
  링크는 아무 동작도 하지 않는 무해한 링크다.
- **자동화 테스트 코드 없음.**
- 추가 예정: KIMM/KITECH/KETI/EBIZ4U 수집원, 낙찰 결과 정보(낙찰업체/
  낙찰금액/낙찰률) 수집.
