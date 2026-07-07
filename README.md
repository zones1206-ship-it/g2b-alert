# 장비 입찰 공고 알리미 (g2b-alert)

반도체·디스플레이·도금 장비 업계 관련 입찰 공고를 여러 수집원에서
모아 키워드로 필터링해서 보여주는 개인용 알림 대시보드. 순수 정적
HTML/CSS/JS + GitHub Actions로 구성했으며, Netlify 등 외부 호스팅은
사용하지 않는다.

## 수집 출처

| 출처 | sourceCode | 방식 |
|---|---|---|
| 나라장터 (조달청) | `G2B` | 공공데이터포털 오픈API |
| 한국나노기술원 (KANC) | `KANC` | 공개 입찰공고 게시판 HTML 수집 (공식 API/RSS 없음) |

새 수집원은 `scripts/collectors/`에 모듈 하나만 추가하면 붙일 수 있는
구조로 되어 있다 (아래 "수집기 구조" 참고).

## 구성

```
g2b-alert/
├── index.html                          화면 (키워드 선택 / 공고 리스트)
├── style.css
├── app.js                               필터링, D-day/출처/공고유형 뱃지, localStorage 저장
├── data/announcements.json              수집된 공고 데이터 (Actions가 매일 갱신)
├── scripts/
│   ├── fetch_announcements.py           여러 수집기를 실행해 결과를 합치는 orchestrator
│   └── collectors/
│       ├── common.py                    공유 상수(카테고리, 출처 목록 등)
│       ├── g2b.py                       나라장터 수집기
│       └── kanc.py                      한국나노기술원 수집기
└── .github/workflows/fetch-announcements.yml   매일 1회 자동 수집
```

## 데이터 스키마

각 공고 아이템은 아래 필드를 가진다 (수집원이 늘어나도 동일한 스키마 유지):

```json
{
  "id": "출처 내 고유 ID",
  "title": "공고명",
  "org": "발주기관",
  "dueDate": "YYYY-MM-DD 또는 null (확인 불가 시 화면에 '마감일 확인 필요'로 표시)",
  "keywords": ["반도체 장비", "..."],
  "budget": "예산 문자열 또는 null",
  "eligibility": "참가자격 또는 null",
  "description": "부가 설명 또는 null",
  "url": "원문 공고 URL",
  "source": "나라장터 | 한국나노기술원",
  "sourceCode": "G2B | KANC",
  "noticeType": "사전규격 | 정식입찰 | null (수집원에 따라 없을 수 있음)"
}
```

## 1. 나라장터 API 키 발급 절차

1. [공공데이터포털](https://www.data.go.kr) 회원가입 및 로그인
2. 검색창에 **"나라장터 입찰공고정보서비스"** 검색
   - 제공기관: 조달청 / 서비스명: `BidPublicInfoService`
3. 상세 페이지에서 **활용신청** 클릭
   - 활용 목적: 개인 학습/업무 참고용으로 작성
   - 라이선스 표시 여부 등 안내에 따라 작성 후 제출
4. **일반 인증키(Encoding/Decoding)** 는 승인 즉시 자동 발급됨 (보통 1~2시간, 늦어도 1일 이내)
   - 마이페이지 > 데이터활용 > 오픈API 활용신청 현황에서 확인
5. 발급된 키 중 **Decoding 키**를 사용한다 (URL에 다시 인코딩되지 않도록)

> 참고: 서비스 상세 스펙(요청 파라미터, 응답 필드명)은 활용신청 승인 후
> "참고문서"에서 최신 명세를 반드시 확인할 것. `scripts/fetch_announcements.py`는
> 표준 파라미터(`inqryDiv`, `inqryBgnDt`, `inqryEndDt`, `bidNtceNm` 등)를
> 기준으로 작성되었으므로 실제 응답 필드에 맞춰 미세 조정이 필요할 수 있다.

## 2. GitHub 저장소 secrets 설정

저장소 Settings → Secrets and variables → Actions → New repository secret

| Name          | Value                    |
|---------------|--------------------------|
| `G2B_API_KEY` | 발급받은 Decoding 인증키 |

secret이 없으면 `fetch_announcements.py`는 아무 것도 하지 않고 종료하므로,
키 발급 전까지는 `data/announcements.json`의 샘플 데이터로 화면을 확인할 수 있다.

## 3. GitHub Pages 활성화

1. 저장소 Settings → Pages
2. Source: `Deploy from a branch`
3. Branch: `main` / `/ (root)` 선택 → Save
4. 몇 분 뒤 `https://<username>.github.io/g2b-alert/` 에서 확인 가능

## 4. GitHub Actions 자동 수집

- `.github/workflows/fetch-announcements.yml`이 매일 07:00(KST)에 실행되어
  `scripts/fetch_announcements.py`(orchestrator)가 등록된 모든 수집기를
  실행하고 결과를 합쳐 `data/announcements.json`에 저장한다.
- **수집기 하나가 실패해도 다른 수집기와 기존 데이터에 영향을 주지 않는다.**
  실패한 수집원은 이번 실행분을 건너뛰고 이전에 저장된 해당 출처(`sourceCode`)의
  데이터를 그대로 유지한다.
- 저장소 Actions 탭에서 `Run workflow`로 즉시 수동 실행도 가능하다 (workflow_dispatch).

### G2B (나라장터)

- 사용 API: `BidPublicInfoService` / `getBidPblancListInfoServc`
  (`https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc`)
- 공고명 검색 파라미터(`bidNtceNm`)는 실제로는 서버에서 제목을 필터링해주지
  않는 것으로 확인되어 사용하지 않는다. 대신 조회 기간(최근 30일) 내 전체
  공고를 페이지네이션으로 받아온 뒤, `scripts/collectors/g2b.py`의
  `CATEGORY_MATCH_TERMS` 사전으로 로컬에서 제목을 분류한다.
  세부 검색어(예: 반도체 장비 → 웨이퍼, wafer, EFEM, FOUP, 클린룸 등) 중
  하나라도 제목에 포함되면 매칭되고, 여러 카테고리에 매칭되면 `keywords`
  배열에 모두 저장되어 결과 화면 여러 그룹에 동시 표시된다.
- 인증키가 잘못되었거나 활용신청이 아직 승인되지 않으면 API가 JSON 대신
  XML 에러를 반환하는데, 이를 감지해 에러 로그를 남기고 기존 G2B 데이터를
  보존한다.
- 502/503/504 등 일시적 오류는 점진적 대기(3→10→20→40→60초)로 최대 5회
  재시도한다.

### KANC (한국나노기술원)

- 공식 API/RSS가 없어 공개 입찰공고 게시판(`https://kanc.re.kr/gnb04/snb02_01.do`)
  HTML을 직접 수집한다 (로그인/CAPTCHA 없는 공개 게시판만 대상).
- 분류는 2단계: ① "매각", "취소" 등이 제목에 있으면 무조건 제외 ②
  `EQUIPMENT_INCLUDE_TERMS`(구매/제작/설치/장비/설비/사전규격 등) 신호가
  있으면 포함(서비스성 단어가 같이 있어도 장비 신호 우선) ③ 장비 신호 없이
  `SERVICE_EXCLUDE_TERMS`(운영용역/위탁/교육/행사/컨설팅 등)만 있으면 제외
  ④ 둘 다 없으면 기본 제외.
- `noticeType`으로 "사전규격"/"정식입찰"을 구분하며, 사전규격공개는
  제외 대상이 아니라 우선 수집 대상이다.
- 목록 페이지에는 마감일이 없어 상세페이지에서 정규식으로 추출한다.
  추출한 마감일이 등록일보다 이전이면(원문 게시물 자체의 오타 가능성)
  다음 후보 패턴으로 대체하며, 끝내 찾지 못하면 `dueDate: null`로 두고
  화면에 "마감일 확인 필요"로 표시한다(임의로 날짜를 만들어내지 않는다).
- KANC는 이미 반도체/나노 장비 전문 게시판이라 카테고리 분류 시 나라장터처럼
  넓은 필터를 쓰지 않고, 디스플레이/도금 신호가 명확할 때만 그쪽으로 분류하고
  나머지는 기본값으로 "반도체 장비"에 둔다.

### 새 수집원 추가 방법

1. `scripts/collectors/<이름>.py`에 `collect() -> list[dict]` 함수 구현
   (반환 스키마는 `scripts/collectors/common.py` 상단 docstring 참고)
2. `scripts/fetch_announcements.py`의 `COLLECTORS` 리스트에 추가
3. `app.js`의 `SOURCE_LINK_LABELS`에 `{ 코드: "OO 원문 보기" }` 한 줄 추가
4. (선택) `index.html`의 "수집 출처" 칩 목록에 추가

## 5. 로컬 미리보기

정적 파일이므로 별도 빌드 없이 아무 정적 서버로 열면 된다.

```bash
cd g2b-alert
python -m http.server 8080
# http://localhost:8080 접속
```

## 다음 단계 (제외 범위)

- 텔레그램 봇 연동 ("텔레그램으로 알림 받기" 버튼은 현재 안내 문구만 표시)
- 키워드 커스텀 추가/삭제 UI
