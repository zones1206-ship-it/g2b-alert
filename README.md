# 나라장터 공고 알리미 (g2b-alert)

반도체/디스플레이 장비 업계 관련 나라장터(조달청) 입찰공고를 키워드로
필터링해서 보여주는 개인용 알림 대시보드. 순수 정적 HTML/CSS/JS +
GitHub Actions로 구성했으며, Netlify 등 외부 호스팅은 사용하지 않는다.

## 구성

```
g2b-alert/
├── index.html                 화면 (키워드 선택 / 공고 리스트)
├── style.css
├── app.js                     필터링, D-day 뱃지, localStorage 저장
├── data/announcements.json    수집된 공고 데이터 (Actions가 매일 갱신)
├── scripts/fetch_announcements.py   나라장터 API 호출 스크립트
└── .github/workflows/fetch-announcements.yml   매일 1회 자동 수집
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
  `scripts/fetch_announcements.py`로 최신 공고를 가져오고,
  키워드(반도체 장비, 세정 설비, 디스플레이 장비, 트롤리, 자동화 설비,
  검사 장비, 클린룸, 이송 시스템)에 매칭되는 공고만 `data/announcements.json`에 저장한다.
- 저장소 Actions 탭에서 `Run workflow`로 즉시 수동 실행도 가능하다 (workflow_dispatch).
- 데이터가 갱신되면 워크플로우가 직접 커밋/푸시하므로 별도 배포 단계 없이
  GitHub Pages가 자동으로 최신 화면을 서빙한다.

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
