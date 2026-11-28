(function (root) {
  'use strict';
  function validation(input, mode) {
    if (mode !== 'update' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((input.email || '').trim())) return 'email';
    if (mode !== 'reset' && !input.password) return 'password';
    if (mode === 'signup' || mode === 'update') {
      if (input.password.length < 8 || input.password.length > 128) return 'length';
      if (input.password !== input.confirm) return 'match';
    }
    if (mode === 'signup' && (!input.terms || !input.privacy)) return 'consent';
    return null;
  }
  function errorCode(error) {
    const known = {
      invalid_credentials: 'credentials', email_not_confirmed: 'unconfirmed',
      over_email_send_rate_limit: 'rate', over_request_rate_limit: 'rate',
      weak_password: 'length', same_password: 'same',
      email_address_not_authorized: 'mailSetup', signup_disabled: 'unavailable',
      user_already_exists: 'checkEmail', email_exists: 'checkEmail',
      otp_expired: 'expired', flow_state_expired: 'expired',
      identity_already_exists: 'identityExists', manual_linking_disabled: 'unavailable',
    };
    return known[error?.code] || (error?.status === 429 ? 'rate' : 'connection');
  }
  function callbackError(search, hash) {
    const query = new URLSearchParams(search), fragment = new URLSearchParams(hash.replace(/^#/, ''));
    const get = key => fragment.get(key) || query.get(key) || '';
    if (!get('error')) return null;
    const description = get('error_description');
    if (get('error_code') === 'identity_already_exists') return 'identityExists';
    if (description.includes('already belongs')) return 'linkRequired';
    if (description.includes('confirmation email has been sent')) return 'checkEmail';
    if (description.includes('Unverified email')) return 'unconfirmed';
    return errorCode({code: get('error_code')});
  }
  function createController(auth, config, callbackUrl) {
    let busy = false;
    let recovery = false;
    function ready() {
      return Boolean(config.registrationReady && config.policyVersion && config.termsUrl && config.privacyUrl);
    }
    return {
      ready,
      socialReady(provider) {
        return ready() && ['google', 'kakao', 'custom:naver'].includes(provider)
          && config.socialProviders?.[provider] === true;
      },
      async social(provider) {
        if (busy) return {error: 'busy'};
        if (!this.socialReady(provider)) return {error: 'unavailable'};
        busy = true;
        try {
          const result = await auth.signInWithOAuth({provider, options: {redirectTo: callbackUrl}});
          return result.error ? {error: errorCode(result.error)} : {message: 'working'};
        } catch { return {error: 'connection'}; }
        finally { busy = false; }
      },
      async link(provider) {
        if (busy) return {error: 'busy'};
        if (!this.socialReady(provider)) return {error: 'unavailable'};
        busy = true;
        try {
          const {data, error} = await auth.getUser();
          if (error || !data?.user) return {error: 'credentials'};
          const result = await auth.linkIdentity({provider, options: {redirectTo: callbackUrl}});
          return result.error ? {error: errorCode(result.error)} : {message: 'working'};
        } catch { return {error: 'connection'}; }
        finally { busy = false; }
      },
      observe(event, session) {
        if (event === 'PASSWORD_RECOVERY') recovery = Boolean(session);
        if (event === 'SIGNED_OUT') recovery = false;
      },
      async submit(mode, input) {
        if (busy) return {error: 'busy'};
        const invalid = validation(input, mode);
        if (invalid) return {error: invalid};
        if ((mode === 'signup' || mode === 'reset') && !ready()) return {error: 'unavailable'};
        if (mode === 'update' && !recovery) return {error: 'expired'};
        busy = true;
        try {
          let result;
          const email = (input.email || '').trim();
          if (mode === 'signup') {
            result = await auth.signUp({email, password: input.password,
              options: {emailRedirectTo: callbackUrl, data: {
                terms_version: config.policyVersion, privacy_version: config.policyVersion,
              }}});
            // Confirmed existing accounts may receive an obfuscated success
            // without any signup mail. Request a login code for that case;
            // never change the existing password or create another account.
            const existing = ['user_already_exists', 'email_exists'].includes(result.error?.code)
              || (!result.error && Array.isArray(result.data?.user?.identities)
                && result.data.user.identities.length === 0 && !result.data?.session);
            if (existing) {
              result = await auth.signInWithOtp({email, options: {shouldCreateUser:false}});
            }
          } else if (mode === 'signin') {
            result = await auth.signInWithPassword({email, password: input.password});
          } else if (mode === 'reset') {
            result = await auth.resetPasswordForEmail(email, {redirectTo: callbackUrl});
          } else if (mode === 'update') {
            result = await auth.updateUser({password: input.password});
          } else return {error: 'unavailable'};
          if (result.error) return {error: errorCode(result.error)};
          if (mode === 'signup' || mode === 'reset') return {message: 'checkEmail'};
          if (mode === 'update') { recovery = false; return {message: 'updated'}; }
          return result.data?.user ? {message: 'signedIn', user: result.data.user} : {error: 'connection'};
        } catch { return {error: 'connection'}; }
        finally { busy = false; }
      },
      async signOut() {
        try {
          const {error} = await auth.signOut();
          if (error) return {error: errorCode(error)};
          recovery = false;
          return {message: 'signedOut'};
        } catch { return {error: 'connection'}; }
      },
    };
  }
  const api = {validation, errorCode, callbackError, createController};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.MemberAuth = api;
})(typeof window !== 'undefined' ? window : globalThis);
