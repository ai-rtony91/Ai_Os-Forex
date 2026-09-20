import crypto from 'node:crypto'
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
function base64Url(input) {
  return Buffer.from(input).toString('base64').replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_')
}
function base64UrlJson(value) { return base64Url(JSON.stringify(value)) }
function sha256(input) { return crypto.createHash('sha256').update(input).digest() }
function randomId() { return crypto.randomUUID ? crypto.randomUUID() : crypto.randomBytes(16).toString('hex') }
function normalizeThumbprint(value = '') { return String(value || '').replace(/:/g, '').trim() }
function managedIdentityEndpoint(env) { return env.IDENTITY_ENDPOINT || env.MSI_ENDPOINT || '' }
function managedIdentityHeader(env) { return env.IDENTITY_HEADER || env.MSI_SECRET || '' }
function keyVaultAccessTokenScope(env) { return env.AIOS_KEY_VAULT_TOKEN_RESOURCE || 'https://vault.azure.net' }
async function fetchManagedIdentityToken(env, fetchImpl) {
  const endpoint = managedIdentityEndpoint(env)
  const secretHeader = managedIdentityHeader(env)
  if (!endpoint || !secretHeader) throw new Error('AZURE_MANAGED_IDENTITY_CONFIG_REQUIRED')
  const url = new URL(endpoint)
  url.searchParams.set('api-version', '2019-08-01')
  url.searchParams.set('resource', keyVaultAccessTokenScope(env))
  const response = await fetchImpl(url, { headers: { 'x-identity-header': secretHeader, secret: secretHeader } })
  if (!response.ok) throw new Error('AZURE_MANAGED_IDENTITY_TOKEN_FAILED')
  const result = await response.json()
  if (!result.access_token) throw new Error('AZURE_MANAGED_IDENTITY_TOKEN_MISSING')
  return result.access_token
}
async function signWithKeyVault({ env, fetchImpl, signingInput }) {
  const keyId = env.AIOS_ENTRA_CLIENT_ASSERTION_KEY_VAULT_KEY_ID || env.AIOS_ENTRA_KEY_VAULT_KEY_ID || ''
  if (!keyId) throw new Error('ENTRA_CLIENT_ASSERTION_KEY_ID_REQUIRED')
  if (!fetchImpl) throw new Error('ENTRA_CLIENT_ASSERTION_FETCH_REQUIRED')
  const token = await fetchManagedIdentityToken(env, fetchImpl)
  const signUrl = new URL(`${String(keyId).replace(/\/$/, '')}/sign`)
  signUrl.searchParams.set('api-version', env.AIOS_KEY_VAULT_API_VERSION || '7.4')
  const response = await fetchImpl(signUrl, {
    method: 'POST',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify({ alg: 'RS256', value: base64Url(sha256(signingInput)) }),
  })
  if (!response.ok) throw new Error('KEY_VAULT_SIGN_FAILED')
  const result = await response.json()
  if (!result.value) throw new Error('KEY_VAULT_SIGNATURE_MISSING')
  return result.value
}
async function createCertificateClientAssertion({ env, fetchImpl, tokenUrl, clientId }) {
  const thumbprint = normalizeThumbprint(env.AIOS_ENTRA_CLIENT_CERT_THUMBPRINT || env.AIOS_ENTRA_CLIENT_CERTIFICATE_THUMBPRINT)
  if (!thumbprint) throw new Error('ENTRA_CLIENT_CERT_THUMBPRINT_REQUIRED')
  if (!tokenUrl || !clientId) throw new Error('ENTRA_CLIENT_ASSERTION_CONFIG_REQUIRED')
  const now = Math.floor(Date.now() / 1000)
  const header = { alg: 'RS256', typ: 'JWT', x5t: base64Url(Buffer.from(thumbprint, 'hex')) }
  const payload = { aud: tokenUrl, iss: clientId, sub: clientId, jti: randomId(), nbf: now - 60, iat: now, exp: now + 300 }
  const signingInput = `${base64UrlJson(header)}.${base64UrlJson(payload)}`
  const signature = await signWithKeyVault({ env, fetchImpl, signingInput })
  return `${signingInput}.${signature}`
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
      else if (env.AIOS_ENTRA_CLIENT_ASSERTION_KEY_VAULT_KEY_ID || env.AIOS_ENTRA_KEY_VAULT_KEY_ID) {
        body.set('client_assertion_type', 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer')
        body.set('client_assertion', await createCertificateClientAssertion({ env, fetchImpl, tokenUrl, clientId: config.clientId }))
      }
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
