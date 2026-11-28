(function(root){
  'use strict';
  function create(storage,now=Date.now){
    const key='g2b-signup-intent';let memory=null;
    function clear(){memory=null;try{storage.removeItem(key);}catch{}}
    return {
      begin(){memory={started:now()};try{storage.setItem(key,JSON.stringify(memory));}catch{}},
      clear,
      needsConfirmation(user,hasConsent){
        let intent=memory;try{intent=JSON.parse(storage.getItem(key)||'null')||intent;}catch{}
        if(!user?.id||!intent||!Number.isFinite(intent.started))return false;
        if(now()-intent.started>1800000||now()<intent.started){clear();return false;}
        // Only server-verified identity and its registration date are considered.
        return hasConsent || (Number.isFinite(Date.parse(user.created_at)) && Date.parse(user.created_at)<intent.started);
      }
    };
  }
  root.SignupIntent={create};if(typeof module==='object')module.exports={create};
})(typeof window==='object'?window:globalThis);
