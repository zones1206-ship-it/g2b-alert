(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const config = window.MEMBERSHIP_CONFIG;
  let locale = 'ko';
  try { locale = localStorage.getItem('g2b-alert-locale') === 'en' ? 'en' : 'ko'; } catch {}
  const deletion = new URLSearchParams(location.search).get('action') === 'delete';
  let mode = deletion || new URLSearchParams(location.search).get('mode') === 'signin' ? 'signin' : 'signup', sending = false, member = null, lastStatus = '', awaitingCode = false;
  let emailSignup = false;
  let recent;
  try{recent=window.RecentLogin.create(localStorage,sessionStorage);}catch{recent=window.RecentLogin.create(null,null);}
  let signupIntent;try{signupIntent=window.SignupIntent.create(sessionStorage);}catch{signupIntent=window.SignupIntent.create(null);}
  let existingSignup=false;
  const strings = {
    signup: ['회원가입', 'Sign up'], signin: ['로그인', 'Log in'],
    reset: ['비밀번호 재설정', 'Reset your password'], update: ['새 비밀번호 설정', 'Choose a new password'],
    signupButton: ['회원가입·무료 체험', 'Sign up for a free trial'], signinButton: ['로그인', 'Log in'],
    resetButton: ['재설정 메일 받기', 'Send reset email'], updateButton: ['새 비밀번호 저장', 'Save new password'],
    unavailable: ['회원가입과 메일 발송을 준비 중입니다. 아직 접수되지 않았습니다.', 'Registration and email delivery are not ready. Nothing has been submitted.'],
    preparing: ['회원가입 준비 중', 'Registration coming soon'], working: ['처리 중…', 'Working…'],
    email: ['올바른 이메일 주소를 입력해주세요.', 'Enter a valid email address.'],
    password: ['비밀번호를 입력해주세요.', 'Enter your password.'],
    length: ['비밀번호는 8~128자로 입력해주세요.', 'Use a password between 8 and 128 characters.'],
    match: ['두 비밀번호가 일치하지 않습니다.', 'The passwords do not match.'],
    consent: ['이용약관과 개인정보 수집·이용 안내를 확인하고 동의해주세요.', 'Read and agree to the terms and privacy notice.'],
    credentials: ['이메일 또는 비밀번호를 확인해주세요.', 'Check your email and password.'],
    unconfirmed: ['메일의 인증번호를 입력해 이메일을 확인해주세요.', 'Enter the code from your signup email to verify your email.'],
    rate: ['요청이 많습니다. 잠시 후 다시 시도해주세요.', 'Too many requests. Please try again later.'],
    mailSetup: ['인증메일 발송 설정을 준비 중입니다. 잠시 후 다시 이용해주세요.', 'Email delivery is not ready. Please try again later.'],
    checkEmail: ['해당 주소로 진행할 수 있는 경우 확인 메일이 발송됩니다. 받은편지함과 스팸함을 확인해주세요.', 'If this request can be processed, a confirmation email will be sent. Check your inbox and spam folder.'],
    expired: ['링크가 만료됐거나 유효하지 않습니다. 재설정 메일을 다시 요청해주세요.', 'This link is expired or invalid. Request a new reset email.'],
    connection: ['연결하지 못했습니다. 잠시 후 다시 시도해주세요.', 'Unable to connect. Please try again later.'],
    same: ['기존 비밀번호와 다른 비밀번호를 입력해주세요.', 'Choose a password different from your current password.'],
    signedIn: ['로그인됐습니다.', 'You are logged in.'], signedOut: ['로그아웃됐습니다.', 'You are logged out.'],
    updated: ['비밀번호를 변경했습니다.', 'Your password has been changed.'],
    busy: ['요청을 처리 중입니다.', 'A request is already in progress.'],
    linkRequired: ['기존 가입 방법으로 로그인한 뒤 ‘현재 계정에 네이버 연결’을 눌러주세요.', 'Sign in with your existing method, then choose “Link NAVER to this account”.'],
    identityExists: ['이 네이버 계정은 다른 회원 계정에 연결되어 있습니다. 기존 계정으로 로그인하거나 운영팀에 문의해주세요.', 'This NAVER account is linked to another member. Sign in to that account or contact support.'],
  };
  const t = key => (strings[key] || strings.connection)[locale === 'en' ? 1 : 0];
  function status(key, error = false) {
    lastStatus = key;
    $('status').textContent = key ? t(key) : '';
    $('status').dataset.error = String(error);
  }
  let auth, controller, signupCode, lifecycle;
  try {
    if (!config.url.startsWith('https://') || !config.publishableKey.startsWith('sb_publishable_')) throw new Error();
    const callback = new URL('./', location.href);
    callback.search = ''; callback.hash = '';
    const client = window.supabase.createClient(config.url, config.publishableKey, {
      auth: {flowType:'pkce', persistSession:true, autoRefreshToken:true, detectSessionInUrl:true},
    });
    auth = client.auth; lifecycle = window.MemberLifecycle.create(client, config.policyVersion);
    controller = window.MemberAuth.createController(auth, config, callback.href); signupCode = window.SignupCode.mount(auth, $("accountForm"), () => $("email").value, () => locale);
  } catch { status('connection', true); }

  function view() {
    document.title=t(mode)+' · '+(locale==='ko'?'장비 입찰 정보':'Equipment tenders');
    const signup = mode === 'signup', reset = mode === 'reset', update = mode === 'update';
    const visibleMember = Boolean(member && !update);
    $('accountForm').hidden = visibleMember || awaitingCode || (signup && !emailSignup);
    const choice=signup && !emailSignup && !visibleMember && !awaitingCode;
    document.querySelector('.account-card').dataset.entry=choice?'signup':'signin';
    $('emailStart').hidden=!choice;
    $('signupBack').hidden=!signup || !emailSignup || visibleMember || awaitingCode;
    $('codeBack').hidden = !awaitingCode || visibleMember;
    $('deletePanel').hidden = !visibleMember || !deletion;
    $('policyPanel').hidden = !visibleMember || deletion;
    $('memberPanel').hidden = !visibleMember;
    $('existingPanel').hidden=!existingSignup || !visibleMember;
    if(existingSignup){$('memberPanel').hidden=true;$('policyPanel').hidden=true;}
    $('modeButtons').hidden = visibleMember || update || awaitingCode;
    $('memberEmail').textContent = member?.email || '';
    const linked = member?.identities?.some(identity => identity.provider === 'custom:naver');
    $('linkNaver').hidden = !visibleMember || linked || !controller?.socialReady('custom:naver');
    $('linkNaver').disabled = sending;
    $('naverLinked').hidden = !visibleMember || !linked;
    $('accountHeading').textContent = t(visibleMember ? 'signedIn' : mode);
    if(existingSignup && visibleMember)$('accountHeading').textContent=locale==='ko'?'이미 가입된 계정입니다':'You already have an account';
    $('releaseNote').hidden = Boolean(controller?.ready());
    $('emailRow').hidden = update; $('email').disabled = update;
    $('passwordRow').hidden = reset; $('password').disabled = reset;
    $('passwordHint').hidden = !signup && !update;
    $('password').minLength = signup || update ? 8 : 1;
    $('password').autocomplete = signup || update ? 'new-password' : 'current-password';
    $('confirmRow').hidden = !signup && !update; $('confirm').disabled = !signup && !update;
    $('consents').hidden = !signup;
    $('terms').disabled = !signup; $('privacy').disabled = !signup;
    $('forgot').hidden = mode !== 'signin';
    document.querySelectorAll('[data-mode]').forEach(b => {
      b.setAttribute('aria-pressed', String(b.dataset.mode === mode)); b.disabled = sending;
    });
    $('submit').disabled = sending || !controller || ((signup || reset) && !controller.ready());
    $('submit').textContent = t(sending ? 'working' : ((signup || reset) && !controller?.ready() ? 'preparing' : mode + 'Button'));
    $('logout').disabled = sending || !controller;
    document.querySelector('.social-options').hidden = visibleMember || reset || update || awaitingCode;
    document.querySelector('.email-divider').hidden = visibleMember || reset || update || awaitingCode;
    document.querySelectorAll('[data-provider]').forEach(button => {
      button.disabled = sending || !controller?.socialReady(button.dataset.provider);
      const names={google:'Google',kakao:locale==='ko'?'카카오':'Kakao','custom:naver':locale==='ko'?'네이버':'NAVER'};
      button.querySelector('span').textContent=names[button.dataset.provider]+(choice?(locale==='ko'?'로 시작하기':' — Continue'):'');
      button.setAttribute('aria-label',names[button.dataset.provider]+(choice?(locale==='ko'?'로 시작하기':' sign up'):(locale==='ko'?' 로그인':' login')));
      const badge=button.querySelector('.recent-badge');
      badge.hidden=recent.read()!==button.dataset.provider;
      badge.textContent=locale==='ko'?'최근 로그인':'Last used';
    });
    $('emailRecent').hidden=recent.read()!=='email';
    $('emailRecent').textContent=locale==='ko'?'최근 로그인: 이메일':'Last used: email';
    const social=document.querySelector('.social-options'),divider=document.querySelector('.email-divider');
    social.hidden=visibleMember || reset || update || awaitingCode || (signup && emailSignup);
    divider.hidden=!(!visibleMember && mode==='signin' && !awaitingCode);
    divider.textContent=locale==='ko'?'간편 로그인':'Social sign in';
    if(choice){$('accountHeading').after(social);social.after($('emailStart'));}
    else{$('accountForm').after(divider);divider.after(social);}
    document.querySelectorAll('[data-mode]').forEach(b=>{b.hidden=b.dataset.mode===mode;});
    $('modePrompt').textContent=mode==='signup'?(locale==='ko'?'이미 가입하셨나요?':'Already a member?'):(locale==='ko'?'처음 방문하셨나요?':'New here?');
  }
  function translate() {
    signupCode?.render();
    document.documentElement.lang = locale;
    document.title = (locale==='ko'?(mode==='signin'?'로그인':'회원가입'):(mode==='signin'?'Log in':'Sign up'))+' · '+(locale==='ko'?'장비 입찰 정보':'Equipment tenders');
    document.querySelectorAll('[data-ko][data-en]').forEach(el => {el.textContent = el.dataset[locale];});
    document.querySelectorAll('[data-locale]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.locale === locale)));
    if (lastStatus) $('status').textContent = t(lastStatus);
    view();
  }
  function switchMode(value) {
    if (sending) return;
    mode = value; awaitingCode = false; signupCode?.hide();
    emailSignup=false; recent.cancel(); signupIntent.clear(); existingSignup=false;
    const url=new URL(location.href);url.searchParams.set('mode',value);history.replaceState(null,'',url);
    $('password').value = ''; $('confirm').value = '';
    $('terms').checked = false; $('privacy').checked = false;
    status(''); view(); $('email').focus();
  }
  for (const name of ['terms', 'privacy']) {
    const url = config[name + 'Url'];
    if (url && new URL(url, location.href).protocol === 'https:') {
      $(name + 'Link').href = url; $(name + 'Link').hidden = false; $(name + 'Pending').hidden = true;
    }
  }
  document.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => switchMode(b.dataset.mode)));
  $('emailStart').addEventListener('click',()=>{emailSignup=true;view();$('email').focus();});
  $('signupBack').addEventListener('click',()=>switchMode('signup'));
  $('forgot').addEventListener('click', () => switchMode('reset'));
  $('codeBack').addEventListener('click',()=>switchMode('signup'));
  async function continueToNotices() {
    if(deletion || mode === 'update') {view();return;}
    try {
      const hasConsent=await lifecycle.consent();
      if(signupIntent.needsConfirmation(member,hasConsent)){
        existingSignup=true;status('');view();return;
      }
      signupIntent.clear();
      if(!hasConsent) {
        let accepted = false;
        try {accepted=sessionStorage.getItem('g2b-policy-pending')===config.policyVersion;}catch{}
        if(!accepted){view();return;}
        await lifecycle.accept(true);
      }
      try{sessionStorage.removeItem('g2b-policy-pending');}catch{}
      recent.confirmed(member);
      location.replace(new URL('../',location.href).href);
    } catch {status('connection',true);view();}
  }
  $('existingLogin').addEventListener('click',async()=>{
    $('existingLogin').disabled=true;signupIntent.clear();existingSignup=false;
    await continueToNotices();$('existingLogin').disabled=false;
  });
  $('existingCancel').addEventListener('click',async()=>{
    $('existingCancel').disabled=true;
    try{const {error}=await auth.signOut({scope:'local'});if(error)throw error;
      signupIntent.clear();recent.cancel();try{sessionStorage.removeItem('g2b-policy-pending');}catch{}
      location.replace(new URL('./?mode=signup',location.href).href);
    }catch{status('connection',true);$('existingCancel').disabled=false;}
  });
  $('acceptPolicy').addEventListener('click',async()=>{
    if(!$('memberTerms').checked || !$('memberPrivacy').checked){status('consent',true);return;}
    $('acceptPolicy').disabled=true;
    try {await lifecycle.accept(true);await continueToNotices();}catch{status('connection',true);}
    $('acceptPolicy').disabled=false;
  });
  $('deleteAccount').addEventListener('click',()=>{$('deleteDialog').showModal();$('cancelDelete').focus();});
  $('cancelDelete').addEventListener('click',()=>$('deleteDialog').close());
  $('confirmDelete').addEventListener('click',async()=>{
    const button=$('confirmDelete');button.disabled=true;
    try{await lifecycle.remove(true);try{sessionStorage.removeItem('g2b-policy-pending');}catch{}location.replace(new URL('../?account=deleted',location.href).href);}
    catch{$('deleteError').textContent=locale==='ko'?'탈퇴하지 못했습니다. 다시 로그인한 뒤 시도해 주세요.':'Deletion failed. Sign in again and retry.';button.disabled=false;}
  });
  $('linkNaver').addEventListener('click', async () => {
    if (sending || !controller || !member) return;
    sending = true; view(); status('working');
    const result = await controller.link('custom:naver');
    sending = false; status(result.error || result.message, Boolean(result.error)); view();
  });
  document.querySelectorAll('[data-provider]').forEach(button => button.addEventListener('click', async () => {
    if (sending || !controller) return;
    // Returning members go straight to their provider. New members review
    // policyPanel after authentication, before continuing to notices.
    try{sessionStorage.removeItem('g2b-policy-pending');}catch{}
    sending = true; view(); status('working');
    recent.begin(button.dataset.provider);
    if(mode==='signup')signupIntent.begin();else signupIntent.clear();
    const result = await controller.social(button.dataset.provider);
    if(result.error){recent.cancel();signupIntent.clear();}
    sending = false; status(result.error || result.message, Boolean(result.error)); view();
  }));
  document.querySelectorAll('[data-locale]').forEach(button => button.addEventListener('click', () => {
    locale = button.dataset.locale;
    try { localStorage.setItem('g2b-alert-locale', locale); } catch {}
    translate();
  }));
  $('accountForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (sending || !controller) return;
    const input = {email: $('email').value, password: $('password').value, confirm:$('confirm').value,
      terms:$('terms').checked, privacy:$('privacy').checked};
    const invalid = window.MemberAuth.validation(input, mode);
    if (invalid) { status(invalid, true); return; }
    if(mode==='signup')try{sessionStorage.setItem('g2b-policy-pending',config.policyVersion);}catch{}
    if(mode==='signup'||mode==='signin')recent.begin('email');
    if(mode==='signup')signupIntent.begin();else signupIntent.clear();
    sending = true; view(); status('working');
    const result = await controller.submit(mode, input);
    // Keep passwords out of browser storage, logs and drafts.
    input.password = ''; input.confirm = ''; $('password').value = ''; $('confirm').value = '';
    sending = false;
    if(result.error && result.error!=='unconfirmed' && result.error!=='checkEmail')recent.cancel();
    if (result.user) member = result.user;
    if ((mode === "signup" && (result.message === "checkEmail" || result.error === "checkEmail")) || result.error === "unconfirmed") {awaitingCode=true;signupCode?.show(result.error !== 'unconfirmed');}
    if (result.message === 'updated') mode = 'signin';
    status(result.error || result.message, Boolean(result.error)); view();
  });
  $('logout').addEventListener('click', async () => {
    if (sending || !controller) return;
    sending = true; view();
    const result = await controller.signOut();
    sending = false;
    if (!result.error) { location.replace(new URL('./?mode=signin',location.href).href); return; }
    status(result.error || result.message, Boolean(result.error)); view();
  });
  $('status').after($('modeButtons'));
  translate();
  if (auth) {
    let revision = 0;
    auth.onAuthStateChange((event, session) => {
      const current = ++revision;
      controller.observe(event, session);
      if (event === 'PASSWORD_RECOVERY' && session) mode = 'update';
      if (event === 'SIGNED_OUT') {member = null; mode = 'signin'; view();}
      // Never infer paid access or trust user-editable metadata from a session.
      if (session) {
        // Run outside the SDK auth callback's lock. Ignore stale verification
        // if another tab signs out or changes account while the request is in flight.
        setTimeout(() => {
          auth.getUser().then(({data, error}) => {
            if (current !== revision) return;
            member = !error ? data?.user || null : null;
            // Navigate only after server verification; keep recovery and failed
            // identity-linking flows on this page. Never put tokens in the URL.
            if (member && mode !== 'update' && !window.MemberAuth.callbackError(location.search, location.hash) && !lastStatus.match(/^(identityExists|linkRequired)$/)) {
              continueToNotices();
              return;
            }
            view();
          }).catch(() => {if (current === revision) status('connection', true);});
        }, 0);
      }
    });
    const callbackError = window.MemberAuth.callbackError(location.search, location.hash);
    if (callbackError) {
      recent.cancel();
      signupIntent.clear();
      history.replaceState(null, '', location.pathname); status(callbackError, true);
    }
  }
})();
