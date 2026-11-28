(function(){
  'use strict';
  const menu=document.getElementById('membershipMenu');
  if(!menu)return;
  const client=supabase.createClient(MEMBERSHIP_CONFIG.url,MEMBERSHIP_CONFIG.publishableKey,{auth:{flowType:'pkce',detectSessionInUrl:false}});
  let user=null,revision=0;
  function render(){
    const en=document.documentElement.lang==='en';
    menu.replaceChildren();
    function link(text,url){const a=document.createElement('a');a.textContent=text;a.href=url;a.className='logout-link';menu.append(a);}
    if(user){
      const button=document.createElement('button');button.type='button';button.className='logout-link';button.textContent=en?'Log out':'로그아웃';
      button.onclick=async()=>{button.disabled=true;try{const {error}=await client.auth.signOut();if(error)throw error;location.replace(new URL('membership/?mode=signin',location.href).href);}catch{button.textContent=en?'Retry logout':'로그아웃 재시도';button.disabled=false;}};
      menu.append(button);link(en?'Delete account':'회원 탈퇴','membership/?action=delete');
    }else link(en?'Sign up / Log in':'회원가입 / 로그인','membership/');
  }
  client.auth.onAuthStateChange((_event,session)=>{const current=++revision;if(!session){user=null;render();return;}setTimeout(async()=>{try{const {data,error}=await client.auth.getUser();if(current!==revision)return;user=error?null:data?.user;render();}catch{user=null;render();}},0);});
  new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  render();
})();
