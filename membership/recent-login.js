(function(root){
  'use strict';
  const methods=['google','kakao','custom:naver','email'];
  function create(local,session,now=Date.now){
    const pending='g2b-login-attempt',recent='g2b-recent-login';
    function cancel(){try{session.removeItem(pending);}catch{}}
    return {
      begin(method){cancel();if(methods.includes(method))try{session.setItem(pending,JSON.stringify({method,time:now()}));}catch{}},
      cancel,
      confirmed(user){
        try{const value=JSON.parse(session.getItem(pending)||'null');
          if(!user?.id||!value||!methods.includes(value.method)||!Number.isFinite(value.time)||now()-value.time<0||now()-value.time>1800000)return;
          local.setItem(recent,value.method);
        }catch{}finally{cancel();}
      },
      read(){try{const value=local.getItem(recent);return methods.includes(value)?value:null;}catch{return null;}}
    };
  }
  root.RecentLogin={create};
  if(typeof module==='object')module.exports={create};
})(typeof window==='object'?window:globalThis);
