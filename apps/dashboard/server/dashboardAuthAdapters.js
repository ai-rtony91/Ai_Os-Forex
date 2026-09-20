import { createRemoteJWKSet, jwtVerify } from 'jose'

const CLOUDFLARE_CERTS_PATH = '/cdn-cgi/access/certs'
const ENTRA_KEYS_PATH = '/discovery/v2.0/keys'

function trimSlash(value = '') { return String(value || '').replace(/\/$/, '') }
function splitList(value = '') { return String(value || '').split(',').map((item) => item.trim()).filter(Boolean) }
function normalizeIssuer(value = '') { return trimSlash(value) }
function requireUrl(value, name) {
  try { return new URL(value) } catch { throw new Error(`${name}_INVALID`) }
}
function normalizeAudience(audience) {
  return Array.isArray(audience) ? audience : [audience]
}
function containsAudience(tokenAudience, expectedAudience) {
  const tokenValues = normalizeAudience(tokenAudience)
  return tokenValues.includes(expectedAudience)
}
function assertAllowedIdentity(payload, env) {
  const allowedEmails = splitList(env.AIOS_AUTH_ALLOWED_EMAILS || env.AIOS_ENTRA_ALLOWED_EMAILS)
  const allowedTenantIds = splitList(env.AIOS_ENTRA_ALLOWED_TENANT_IDS || env.AIOS_ENTRA_TENANT_ID)
  const email = String(payload.email || payload.preferred_username || '').toLowerCase()
  const tenantId = String(payload.tid || '')
  if (allowedEmails.length && !allowedEmails.map((item) => item.toLowerCase()).includes(email)) {
    throw new Error('IDENTITY_EMAIL_NOT_ALLOWED')
  }
  if (allowedTenantIds.length && !allowedTenantIds.includes(tenantId)) {
    throw new Error('IDENTITY_TENANT_NOT_ALLOWED')
  }
}
function cloudflareTeamDomain(env) {
  return normalizeIssuer(env.AIOS_CLOUDFLARE_TEAM_DOMAIN || env.CLOUDFLARE_ACCESS_TEAM_DOMAIN)
}
function entraAuthority(env) { return normalizeIssuer(env.AIOS_ENTRA_AUTHORITY) }
function entraIssuer(env) { return normalizeIssuer(env.AIOS_ENTRA_ISSUER || env.AIOS_ENTRA_AUTHORITY) }
function entraJwksUrl(env) {
  if (env.AIOS_ENTRA_JWKS_URI) return requireUrl(env.AIOS_ENTRA_JWKS_URI, 'AIOS_ENTRA_JWKS_URI')
  const authority = entraAuthority(env)
  if (!authority) throw new Error('AIOS_ENTRA_AUTHORITY_REQUIRED')
  return new URL(`${authority}${ENTRA_KEYS_PATH}`)
}
function makeJwks(url, cache) {
  const key = url.toString()
  if (!cache.has(key)) cache.set(key, createRemoteJWKSet(url))
  return cache.get(key)
}

export function createDashboardAuthAdapters({ env = process.env, fetchImpl = globalThis.fetch, jwksCache = new Map() } = {}) {
  return {
    async verifyAccessAssertion(assertion) {
      const teamDomain = cloudflareTeamDomain(env)
      const audience = env.AIOS_CLOUDFLARE_ACCESS_AUD || ''
      if (!teamDomain || !audience) throw new Error('CLOUDFLARE_ACCESS_CONFIG_REQUIRED')
      const jwksUrl = new URL(`${teamDomain}${CLOUDFLARE_CERTS_PATH}`)
      const { payload } = await jwtVerify(assertion, makeJwks(jwksUrl, jwksCache), {
        issuer: teamDomain,
        audience,
        algorithms: ['RS256'],
      })
      if (payload.type && payload.type !== 'app') throw new Error('CLOUDFLARE_ACCESS_TOKEN_TYPE_REJECTED')
      if (!containsAudience(payload.aud, audience)) throw new Error('CLOUDFLARE_ACCESS_AUDIENCE_REJECTED')
      return payload
    },

    async exchangeAuthorizationCode(code, verifier, { config } = {}) {
      const tokenUrl = env.AIOS_ENTRA_TOKEN_URL || `${entraAuthority(env)}/oauth2/v2.0/token`
      if (!fetchImpl || !tokenUrl || !config?.clientId || !config?.redirectUri) throw new Error('ENTRA_TOKEN_EXCHANGE_CONFIG_REQUIRED')
      const body = new URLSearchParams({
        client_id: config.clientId,
        grant_type: 'authorization_code',
        code,
        redirect_uri: config.redirectUri,
        code_verifier: verifier,
      })
      if (env.AIOS_ENTRA_CLIENT_SECRET) body.set('client_secret', env.AIOS_ENTRA_CLIENT_SECRET)
      const response = await fetchImpl(tokenUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body,
      })
      if (!response.ok) throw new Error('ENTRA_TOKEN_EXCHANGE_FAILED')
      return response.json()
    },

    async verifyIdentityToken(idToken, nonce) {
      const issuer = entraIssuer(env)
      const clientId = env.AIOS_ENTRA_CLIENT_ID || ''
      if (!issuer || !clientId) throw new Error('ENTRA_ID_TOKEN_CONFIG_REQUIRED')
      const { payload } = await jwtVerify(idToken, makeJwks(entraJwksUrl(env), jwksCache), {
        issuer,
        audience: clientId,
        algorithms: ['RS256'],
      })
      if (nonce && payload.nonce !== nonce) throw new Error('ENTRA_NONCE_REJECTED')
      assertAllowedIdentity(payload, env)
      return payload
    },

    async verifyTurnstile(token, { request, config } = {}) {
      if (!fetchImpl || !config?.turnstileSecretKey) throw new Error('TURNSTILE_CONFIG_REQUIRED')
      const remoteAddress = String(request?.headers?.['cf-connecting-ip'] || request?.socket?.remoteAddress || '').split(',')[0].trim()
      const body = new URLSearchParams({ secret: config.turnstileSecretKey, response: token })
      if (remoteAddress) body.set('remoteip', remoteAddress)
      const response = await fetchImpl('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
        method: 'POST',
        headers: { 'content-type': 'application/x-www-form-urlencoded' },
        body,
      })
      if (!response.ok) return false
      const result = await response.json()
      if (result.success !== true) return false
      const expectedHostnames = splitList(env.AIOS_TURNSTILE_ALLOWED_HOSTNAMES)
      if (expectedHostnames.length && !expectedHostnames.includes(String(result.hostname || ''))) return false
      return true
    },
  }
}
