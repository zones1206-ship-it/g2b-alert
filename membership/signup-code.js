(function(root){
  'use strict';
  function create(auth, now = Date.now) {
    let busy=false, nextSend=0;
    return {
      async verify(email, token) {
        if(busy) return {error:'busy'};
        if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return {error:'email'};
        if(!/^\d{6,10}$/.test(token.trim())) return {error:'code'};
        busy=true;
        try {
          const {data,error}=await auth.verifyOtp({email:email.trim(),token:token.trim(),type:'email'});
          if(error) return {error:error.status===429?'rate':'code'};
          return data?.session && data?.user ? {user:data.user} : {error:'code'};
        } catch {return {error:'connection'};}
        finally {busy=false;}
      },
      sent(){nextSend=now()+60000;},
      remaining(){return Math.max(0,Math.ceil((nextSend-now())/1000));},
      async resend(email) {
        if(busy) return {error:'busy'};
        if(now()<nextSend) return {error:'rate'};
        if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return {error:'email'};
        busy=true; nextSend=now()+60000;
        try {
          const {error}=await auth.signInWithOtp({email:email.trim(),options:{shouldCreateUser:false}});
          return error ? {error:error.status===429?'rate':'connection'} : {sent:true};
        }catch{return {error:'connection'};}
        finally{busy=false;}
      }
    };
  }
  function mount(auth, anchor, getEmail, language) {
    const controller=create(auth);
    const panel=document.createElement('section');
    panel.hidden=true;
    panel.innerHTML='<p class="code-recipient"></p><form><label for="signupCode"></label><input id="signupCode" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6,10}" minlength="6" maxlength="10" required><button type="submit" class="primary"></button></form><button type="button" class="text-button"></button><p role="status" aria-live="polite"></p>';
    anchor.after(panel);
    const form=panel.querySelector('form'),input=panel.querySelector('input'),verify=form.querySelector('button'),resend=panel.querySelector('.text-button'),status=panel.querySelector('[role=status]');
    let activeEmail='',message='sent';
    const messages={sent:['메일의 인증번호를 입력하세요. 새 번호는 60초 후 다시 받을 수 있습니다.','Enter the code from your email. You can resend after 60 seconds.'],code:['번호가 틀렸거나 만료되었습니다. 최신 메일의 번호를 확인하거나 다시 받아주세요.','The code is invalid or expired. Check the latest email or request a new code.'],rate:['잠시 후 다시 시도해주세요. 재전송은 60초 간격으로 가능합니다.','Please wait before retrying. Resend is available every 60 seconds.'],busy:['확인 중입니다.','Checking…'],email:['이메일 주소를 확인해주세요.','Check your email address.'],connection:['연결하지 못했습니다. 다시 시도해주세요.','Unable to connect. Try again.'],done:['이메일 인증이 완료되었습니다.','Your email is verified.']};
    function render(){const en=language()==='en'; panel.querySelector('.code-recipient').textContent=activeEmail;panel.querySelector('label').textContent=en?'Email verification code':'이메일 인증번호';verify.textContent=en?'Verify and continue':'인증하고 계속';const wait=controller.remaining();resend.textContent=wait?(en?'Resend in '+wait+'s':wait+'초 후 다시 받기'):(en?'Resend code':'인증번호 다시 받기');resend.disabled=wait>0||message==='busy';status.textContent=messages[message][en?1:0];}
    async function run(action){verify.disabled=resend.disabled=true;message='busy';render();const result=await action();input.value='';message=result.error||(result.user?'done':'sent');render();verify.disabled=false;render();if(result.user)panel.hidden=true;}
    form.addEventListener('submit',e=>{e.preventDefault();run(()=>controller.verify(activeEmail,input.value));});
    resend.addEventListener('click',()=>{activeEmail=getEmail().trim();run(()=>controller.resend(activeEmail));});
    auth.onAuthStateChange((_event,session)=>{if(session){panel.hidden=true;input.value='';}});
    setInterval(()=>{if(!panel.hidden)render();},1000);
    render();
    return {show(sent=false){activeEmail=getEmail().trim();panel.hidden=false;if(sent)controller.sent();message='sent';render();input.focus();},hide(){panel.hidden=true;input.value='';},render};
  }
  const api={create,mount};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.SignupCode=api;
})(typeof window!=='undefined'?window:globalThis);
