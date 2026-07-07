# 접속 게이트 (Cloudflare Worker)

GitHub Pages는 정적 호스팅이라 서버 인증을 자체적으로 할 수 없다. 이 폴더의
`worker.js`는 Cloudflare의 실제 서버(엣지) 위에서 돌아가는 작은 프록시로,
아래 흐름으로 동작한다.

```
방문자 → (커스텀 도메인, Cloudflare Worker: 비밀번호/세션 확인) → GitHub Pages 원본
```

기존 저장소 코드(`index.html`/`app.js`/`data/*.json` 등)는 전혀 바뀌지 않는다.
Worker가 앞단에서 인증 안 된 요청을 통째로 막기 때문에, `data/announcements.json`
같은 "숨은 API"도 로그인 전에는 아예 원본에 도달하지 못한다.

## 왜 GitHub Pages 위에 바로 못 만드나

GitHub Pages는 요청받은 파일을 그대로 내려주기만 한다(서버 코드 실행 불가).
프론트엔드 JS로만 비밀번호를 비교하면, 페이지의 JS/데이터 파일 자체는 로그인
화면을 거치지 않고도 URL만 알면 그대로 받아갈 수 있어 실질적인 보호가 안 된다.
그래서 Cloudflare Worker(진짜 서버 실행 환경)를 앞단에 두는 방식을 쓴다.

## 준비물

1. **도메인 하나** (이미 있으면 서브도메인만 써도 됨, 예: `bid.내도메인.com`).
   `*.github.io` 자체에는 Cloudflare를 못 물린다 — 반드시 본인 소유 도메인이 필요하다.
2. **Cloudflare 계정** (무료 플랜으로 충분).

## 설정 절차

### 1) 도메인을 Cloudflare에 연결

1. [Cloudflare 대시보드](https://dash.cloudflare.com) → Add a Site → 도메인 입력 (Free 플랜)
2. Cloudflare가 안내하는 네임서버로 도메인 등록기관(레지스트라)에서 네임서버 변경
3. 반영까지 몇 분~몇 시간 소요

### 2) GitHub Pages에 커스텀 도메인 연결

1. 저장소 Settings → Pages → Custom domain에 `bid.내도메인.com` 입력 → Save
2. Cloudflare DNS에서 CNAME 레코드 추가:
   - Name: `bid` (또는 원하는 서브도메인)
   - Target: `zones1206-ship-it.github.io`
   - Proxy status: **Proxied(주황 구름)** — 반드시 Proxied여야 Worker가 가로챌 수 있다
3. GitHub Pages 설정 화면에서 "Enforce HTTPS" 체크

### 3) 비밀번호 해시 만들기 (로컬 PC에서만, 커밋 금지)

터미널에서 실행 (Node.js 필요, 이 저장소에 커밋하지 않음):

```bash
node -e "
const crypto = require('crypto');
const salt = crypto.randomBytes(16).toString('hex');
const password = '여기에_실제_비밀번호';
const hash = crypto.createHash('sha256').update(salt + password).digest('hex');
console.log('SITE_PASSWORD_SALT=' + salt);
console.log('SITE_PASSWORD_HASH=' + hash);
"
```

출력된 두 값을 복사해둔다(비밀번호 원문은 어디에도 저장하지 않는다).

### 4) Worker 배포

1. Cloudflare 대시보드 → Workers & Pages → Create → Worker
2. 이름 지정(예: `g2b-alert-gate`) 후 생성
3. "Edit code"에서 이 저장소의 `security/cloudflare-worker/worker.js` 내용을 그대로 붙여넣고 Deploy
4. Worker → Settings → Variables and Secrets 에서 아래를 **Secret**으로 등록:

   | 이름 | 값 |
   |---|---|
   | `SITE_PASSWORD_HASH` | 위에서 만든 해시 |
   | `SITE_PASSWORD_SALT` | 위에서 만든 salt |
   | `SESSION_SECRET` | 임의의 긴 무작위 문자열(예: `openssl rand -hex 32` 결과) |
   | `AUTH_SESSION_HOURS` | `24` (선택, 기본값도 24) |
   | `ORIGIN_HOST` | `zones1206-ship-it.github.io` |
   | `ORIGIN_PATH_PREFIX` | 저장소가 프로젝트 페이지라면 `/g2b-alert`, 커스텀 도메인을 루트로 쓰면 빈 값 |

5. Worker → Settings → Triggers → Routes(또는 Domains & Routes)에서
   `bid.내도메인.com/*` 를 이 Worker에 연결

### 5) 확인

- `https://bid.내도메인.com` 접속 시 비밀번호 화면이 먼저 뜨는지 확인
- 올바른 비밀번호 입력 후 기존 사이트가 정상 표시되는지 확인
- 새로고침/다른 경로 이동해도 로그인 유지되는지 확인 (세션 쿠키, 24시간)
- 우측 상단 "로그아웃"(프론트엔드에 별도 추가 필요 — 링크는 `/__auth/logout`)
- 잘못된 비밀번호 5회 입력 시 10분 잠기는지 확인
- `data/announcements.json`을 로그인 없이 직접 열어봤을 때도 로그인 화면이 뜨는지 확인
  (Worker가 모든 경로를 가로채므로 정적 파일도 보호된다)

## 로그아웃 버튼

`index.html` 헤더에 이미 추가돼 있다(`/__auth/logout` 링크). Worker를
배포하지 않은 상태에서는 그냥 아무 동작도 없는 무해한 링크이고, Worker를
배포하면 실제 로그아웃(세션 쿠키 삭제 + 로그인 화면 이동)으로 동작한다.

## 한계 / 참고

- 로그인 시도 횟수 제한은 Worker 메모리에 저장돼, Worker가 재시작되면
  초기화될 수 있다. 더 엄격하게 하려면 Cloudflare KV나 Durable Object로
  승격할 수 있다(현재는 무료 플랜에서 바로 쓸 수 있는 가장 단순한 방식을 택함).
- 비밀번호 해시는 bcrypt/argon2가 아니라 SHA-256+salt다. Cloudflare
  Workers 런타임은 Web Crypto API(SHA 계열)를 기본 제공하고 bcrypt는
  기본 제공하지 않는다. 평문 저장/비교를 하지 않는다는 핵심 원칙은
  동일하게 지켰다.
