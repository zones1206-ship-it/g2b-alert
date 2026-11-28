// Browser-safe publishable key only. Never put a secret/service-role key here.
window.MEMBERSHIP_CONFIG = Object.freeze({
  url: 'https://dhcovligkujzqythlkuy.supabase.co',
  publishableKey: 'sb_publishable_98wOEJWzKgqI-8XDBNG3yQ_fEmSbNTF',
  // Public trial: notices remain public. This is not a paid-content access gate.
  registrationReady: true,
  // Google is published; Kakao login is enabled. NAVER awaits public review.
  socialProviders: Object.freeze({google: true, kakao: true, 'custom:naver': false}),
  policyVersion: '2026-11-28',
  termsUrl: 'https://zones1206-ship-it.github.io/g2b-alert/membership/terms.html',
  privacyUrl: 'https://zones1206-ship-it.github.io/g2b-alert/membership/privacy.html',
});
