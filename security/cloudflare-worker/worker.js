/**
 * 장비 프로젝트 레이더 — 접속 게이트 (Cloudflare Worker)
 *
 * GitHub Pages는 정적 호스팅이라 서버 코드를 실행할 수 없다. 이 Worker는
 * Cloudflare의 진짜 서버(V8 isolate) 위에서 돌아가며, 커스텀 도메인 앞단에
 * 놓여 모든 요청을 가로챈다:
 *
 *   방문자 -> (Cloudflare Worker: 여기서 비밀번호/세션 확인) -> GitHub Pages 원본
 *
 * 비밀번호 자체나 평문 비교값은 코드/저장소 어디에도 없다. Cloudflare
 * 대시보드의 Worker 환경변수(Secrets)에만 저장하고, 실제 비교는 이
 * Worker 안에서 SHA-256 해시로 한다(요청하신 bcrypt/argon2는 Workers
 * 런타임에서 기본 제공되지 않아, Web Crypto API가 기본 제공하는 SHA-256 +
 * 랜덤 salt 방식을 썼다 — 평문 비밀번호를 저장/비교하지 않는다는 원칙은
 * 동일하게 지킨다).
 *
 * 필요한 환경변수(Cloudflare 대시보드 > Worker > Settings > Variables and
 * Secrets 에서 "Secret"으로 등록 — 코드에 직접 쓰지 않는다):
 *   SITE_PASSWORD_HASH   비밀번호의 SHA-256 해시값(hex). 아래
 *                         "해시 생성 방법"으로 만든다.
 *   SITE_PASSWORD_SALT   해시에 쓴 salt 문자열(임의의 긴 무작위 문자열).
 *   SESSION_SECRET       세션 쿠키 서명용 비밀키(임의의 긴 무작위 문자열).
 *   AUTH_SESSION_HOURS   (선택) 세션 유지 시간(기본 24).
 *   ORIGIN_HOST          프록시할 GitHub Pages 원본 호스트
 *                         (예: "zones1206-ship-it.github.io").
 *   ORIGIN_PATH_PREFIX   (선택) 저장소가 프로젝트 페이지라 경로 접두어가
 *                         필요하면(예: "/g2b-alert") 지정. 커스텀 도메인을
 *                         저장소 루트로 쓰면 빈 문자열로 둔다.
 *
 * 해시 생성 방법 (로컬에서, 실제 비밀번호를 코드/커밋에 남기지 않고):
 *   node -e "const s=require('crypto').randomBytes(16).toString('hex');
 *            const pw=process.argv[1];
 *            require('crypto').createHash('sha256').update(s+pw).digest('hex')
 *              && console.log('SALT=', s)"
 *   위처럼 salt를 먼저 만들고, salt+비밀번호를 SHA-256 해시한 값을
 *   SITE_PASSWORD_HASH로, salt를 SITE_PASSWORD_SALT로 등록한다.
 *   (이 저장소의 scripts 폴더가 아니라 로컬 PC에서만 실행하고 값만
 *   Cloudflare Secrets에 붙여넣을 것 — 이 파일이나 git에는 절대 남기지 않는다.)
 */

const COOKIE_NAME = "g2b_auth";
const MAX_ATTEMPTS = 5;
const LOCKOUT_MINUTES = 10;

// 로그인 시도 제한용 인메모리 카운터. Worker 인스턴스가 재시작되면
// 초기화되므로 완벽한 영구 저장소는 아니지만(진짜 영구 저장이 필요하면
// Cloudflare KV/Durable Object로 승격 가능), 무료 요금제로 바로 쓸 수
// 있는 가장 단순한 방식이다.
const attempts = new Map();

async function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmac(key, message) {
  const cryptoKey = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(key),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, new TextEncoder().encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function makeSessionToken(env) {
  const hours = Number(env.AUTH_SESSION_HOURS || 24);
  const expires = Date.now() + hours * 60 * 60 * 1000;
  const payload = `${expires}`;
  const sig = await hmac(env.SESSION_SECRET, payload);
  return `${payload}.${sig}`;
}

async function isValidSession(token, env) {
  if (!token || !token.includes(".")) return false;
  const [payload, sig] = token.split(".");
  const expected = await hmac(env.SESSION_SECRET, payload);
  if (sig !== expected) return false;
  return Number(payload) > Date.now();
}

function getCookie(request, name) {
  const header = request.headers.get("Cookie") || "";
  const match = header.match(new RegExp(`(?:^|; )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function clientIp(request) {
  return request.headers.get("CF-Connecting-IP") || "unknown";
}

function loginPage(errorMessage) {
  return `<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>장비 프로젝트 레이더 - 접속 인증</title>
<style>
  :root { --navy:#0f1d45; --navy-deep:#0a1533; --bg:#f4f6fb; --border:#e3e7f0; --red:#e0432b; --red-bg:#fdecea; }
  * { box-sizing:border-box; }
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
    background:var(--bg); font-family:"Pretendard","Apple SD Gothic Neo","Segoe UI",-apple-system,sans-serif; padding:20px; }
  .card { width:100%; max-width:360px; background:#fff; border-radius:18px; padding:32px 26px;
    box-shadow:0 4px 24px rgba(15,29,69,.12); }
  h1 { font-size:18px; font-weight:800; color:var(--navy); margin:0 0 4px; text-align:center; }
  p.sub { font-size:13px; color:#6b7280; text-align:center; margin:0 0 24px; }
  .field { position:relative; margin-bottom:14px; }
  input[type="password"], input[type="text"] { width:100%; padding:13px 44px 13px 14px; border:1.5px solid var(--border);
    border-radius:12px; font-size:14px; }
  input:focus { outline:none; border-color:var(--navy); }
  .toggle-btn { position:absolute; right:10px; top:50%; transform:translateY(-50%); background:none; border:none;
    cursor:pointer; color:#9099ab; font-size:12px; padding:6px; }
  button.submit { width:100%; padding:14px; background:var(--navy); color:#fff; border:none; border-radius:12px;
    font-size:15px; font-weight:700; cursor:pointer; margin-top:6px; }
  button.submit:hover { background:var(--navy-deep); }
  .error { background:var(--red-bg); color:var(--red); font-size:13px; padding:10px 12px; border-radius:10px;
    margin-bottom:14px; text-align:center; }
</style></head>
<body>
  <form class="card" method="POST" action="/__auth/login">
    <h1>반도체 · 디스플레이 · TGV</h1>
    <p class="sub">입찰정보 시스템 — 접근 권한이 필요합니다</p>
    ${errorMessage ? `<div class="error">${errorMessage}</div>` : ""}
    <div class="field">
      <input type="password" name="password" id="pw" placeholder="비밀번호 입력" required autofocus>
      <button type="button" class="toggle-btn" onclick="const i=document.getElementById('pw');i.type=i.type==='password'?'text':'password';this.textContent=i.type==='password'?'보기':'숨기기'">보기</button>
    </div>
    <button type="submit" class="submit">접속</button>
  </form>
</body></html>`;
}

async function handleLogin(request, env) {
  const ip = clientIp(request);
  const now = Date.now();
  const record = attempts.get(ip);

  if (record && record.lockedUntil && record.lockedUntil > now) {
    const waitMin = Math.ceil((record.lockedUntil - now) / 60000);
    return new Response(loginPage(`너무 많은 시도가 있었습니다. ${waitMin}분 후 다시 시도해주세요.`), {
      status: 429,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }

  const form = await request.formData();
  const password = form.get("password") || "";
  const salt = env.SITE_PASSWORD_SALT || "";
  const hash = await sha256Hex(salt + password);

  if (hash !== env.SITE_PASSWORD_HASH) {
    const failCount = (record?.count || 0) + 1;
    const next = { count: failCount };
    if (failCount >= MAX_ATTEMPTS) {
      next.lockedUntil = now + LOCKOUT_MINUTES * 60 * 1000;
      next.count = 0;
    }
    attempts.set(ip, next);
    return new Response(loginPage("비밀번호가 올바르지 않습니다."), {
      status: 401,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  }

  attempts.delete(ip);
  const token = await makeSessionToken(env);
  const hours = Number(env.AUTH_SESSION_HOURS || 24);
  const headers = new Headers({ Location: "/" });
  headers.append(
    "Set-Cookie",
    `${COOKIE_NAME}=${encodeURIComponent(token)}; Path=/; Max-Age=${hours * 3600}; HttpOnly; Secure; SameSite=Lax`
  );
  return new Response(null, { status: 302, headers });
}

function handleLogout() {
  const headers = new Headers({ Location: "/" });
  headers.append("Set-Cookie", `${COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax`);
  return new Response(null, { status: 302, headers });
}

async function proxyToOrigin(request, env) {
  const url = new URL(request.url);
  const originUrl = new URL(request.url);
  originUrl.hostname = env.ORIGIN_HOST;
  originUrl.protocol = "https:";
  originUrl.port = "";
  if (env.ORIGIN_PATH_PREFIX && !url.pathname.startsWith(env.ORIGIN_PATH_PREFIX)) {
    originUrl.pathname = env.ORIGIN_PATH_PREFIX.replace(/\/$/, "") + url.pathname;
  }
  const originRequest = new Request(originUrl.toString(), request);
  originRequest.headers.set("Host", env.ORIGIN_HOST);
  return fetch(originRequest);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/__auth/login" && request.method === "POST") {
      return handleLogin(request, env);
    }
    if (url.pathname === "/__auth/logout") {
      return handleLogout();
    }

    const token = getCookie(request, COOKIE_NAME);
    const authed = await isValidSession(token, env);

    if (!authed) {
      // data/*.json 같은 "숨은 API"도 여기서 같이 막힌다 — 인증 안 된
      // 요청은 원본(GitHub Pages)까지 아예 도달하지 못한다.
      return new Response(loginPage(null), {
        status: 401,
        headers: { "Content-Type": "text/html; charset=utf-8" },
      });
    }

    return proxyToOrigin(request, env);
  },
};
