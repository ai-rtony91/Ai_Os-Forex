export function getLoginPresentation({ phase = '', code = '', providers = [] } = {}) {
  if (code === 'CLOUDFLARE_ACCESS_REJECTED' || code === 'CLOUDFLARE_ACCESS_REQUIRED') return { available: false, tone: 'closed', message: 'Secure access could not be verified. Access remains closed.' }
  if (code === 'AUTH_CONFIGURATION_UNAVAILABLE') return { available: false, tone: 'closed', message: 'Sign-in is temporarily unavailable. Access remains closed.' }
  if (code === 'TURNSTILE_VERIFICATION_FAILED') return { available: false, tone: 'closed', message: 'Human verification could not be completed. Access remains closed.' }
  if (code) return { available: false, tone: 'closed', message: 'Sign-in could not be completed. Access remains closed.' }
  if (phase === 'checking') return { available: false, tone: 'closed', message: 'Checking secure access…' }
  if (phase === 'identity_required') return { available: true, tone: 'ready', message: Array.isArray(providers) && providers.includes('github') ? 'Choose an approved account to continue.' : 'Use your approved Microsoft identity to continue.' }
  if (phase === 'turnstile_required') return { available: false, tone: 'ready', message: 'Complete the human verification to continue.' }
  if (phase === 'turnstile_error') return { available: false, tone: 'closed', message: 'Human verification could not be completed. Access remains closed.' }
  if (phase === 'error') return { available: false, tone: 'closed', message: 'Authentication service is unavailable. Access remains closed.' }
  return { available: false, tone: 'closed', message: 'Sign-in is temporarily unavailable. Access remains closed.' }
}

export function getLoginProviders(authState = {}) {
  const available = getLoginPresentation(authState).available
  const enabled = Array.isArray(authState.providers) ? authState.providers : ['microsoft']
  return [
    { id: 'microsoft', label: 'Sign in with Microsoft', href: '/auth/login' },
    { id: 'github', label: 'Sign in with GitHub', href: '/auth/login?provider=github' },
  ].map((provider) => ({ ...provider, enabled: available && enabled.includes(provider.id) }))
}
