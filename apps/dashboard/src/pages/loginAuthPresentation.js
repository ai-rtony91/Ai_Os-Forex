export function getLoginPresentation({ phase = '', code = '' } = {}) {
  if (phase === 'checking') return { available: false, tone: 'closed', message: 'Checking secure access…' }
  if (phase === 'identity_required') return { available: true, tone: 'ready', message: 'Use your approved Microsoft identity to continue.' }
  if (phase === 'turnstile_required') return { available: false, tone: 'ready', message: 'Complete the human verification to continue.' }
  if (phase === 'turnstile_error' || code === 'TURNSTILE_VERIFICATION_FAILED') return { available: false, tone: 'closed', message: 'Human verification could not be completed. Access remains closed.' }
  if (code === 'CLOUDFLARE_ACCESS_REJECTED' || code === 'CLOUDFLARE_ACCESS_REQUIRED') return { available: false, tone: 'closed', message: 'Secure access could not be verified. Access remains closed.' }
  if (code === 'AUTH_CONFIGURATION_UNAVAILABLE') return { available: false, tone: 'closed', message: 'Sign-in is temporarily unavailable. Access remains closed.' }
  if (phase === 'error') return { available: false, tone: 'closed', message: 'Authentication service is unavailable. Access remains closed.' }
  return { available: false, tone: 'closed', message: 'Sign-in is temporarily unavailable. Access remains closed.' }
}
