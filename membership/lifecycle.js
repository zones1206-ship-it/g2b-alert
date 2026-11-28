(function(root){
  'use strict';
  function create(client, version) {
    return {
      async consent() {
        const {data,error}=await client.auth.getUser();
        if(error||!data?.user) throw new Error('authentication');
        const result=await client.from('member_consents').select('policy_version').eq('user_id',data.user.id).maybeSingle();
        if(result.error) throw new Error('connection');
        return result.data?.policy_version===version;
      },
      async accept(checked) {
        if(!checked) throw new Error('consent');
        const {error}=await client.rpc('accept_member_policy',{version});
        if(error) throw new Error('connection');
      },
      async remove(checked) {
        if(!checked) throw new Error('confirmation');
        const {data,error}=await client.auth.getUser();
        if(error||!data?.user) throw new Error('authentication');
        const result=await client.rpc('delete_my_membership',{confirmation:'DELETE MY ACCOUNT'});
        if(result.error) throw new Error('connection');
        // Account removal succeeded even if the already-revoked session cannot sign out remotely.
        await client.auth.signOut({scope:'local'}).catch(()=>{});
      }
    };
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={create};else root.MemberLifecycle={create};
})(typeof window!=='undefined'?window:globalThis);
