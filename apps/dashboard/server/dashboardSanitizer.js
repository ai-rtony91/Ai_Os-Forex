const SENSITIVE_KEY_FRAGMENTS = Object.freeze([
  'authorization', 'bearer', 'token', 'secret', 'password', 'api_key',
  'apikey', 'account_id', 'accountid', 'client_secret', 'refresh_token',
  'access_token', 'private_key', 'session_cookie', 'credential',
])

export function isSensitiveKey(key) {
  const normalized = String(key).toLowerCase()
  return SENSITIVE_KEY_FRAGMENTS.some((fragment) => normalized.includes(fragment))
}

export function sanitizeDashboardPayload(value, rejectedKeys = []) {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeDashboardPayload(item, rejectedKeys))
  }
  if (!value || typeof value !== 'object') return value

  const clean = {}
  for (const [key, child] of Object.entries(value)) {
    if (isSensitiveKey(key)) {
      rejectedKeys.push(key)
      continue
    }
    clean[key] = sanitizeDashboardPayload(child, rejectedKeys)
  }
  return clean
}

export function sanitizeWithReport(value) {
  const rejectedKeys = []
  return { data: sanitizeDashboardPayload(value, rejectedKeys), rejectedKeys }
}
