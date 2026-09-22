import crypto from 'node:crypto'
import { Buffer } from 'node:buffer'
import process from 'node:process'

const AUTH_PATHS = new Set([
  '/auth/login',
  '/auth/signup',
  '/auth/callback',
  '/auth/logout',
  '/auth/session',
  '/auth/turnstile',
])

const COOKIE_NAMES = Object.freeze({
  state: '__Host-aios-auth-state',
  pending: '__Host-aios-auth-pending',
  session: '__Host-aios-session',
})

const NO_STORE_HEADERS = Object.freeze({
  'cache-control': 'no-store',
  'content-type': 'application/json; charset=utf-8',
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'no-referrer',
})

const ACCESS_VERIFIER_CATEGORIES = Object.freeze({
  issuerMismatch: 'ISSUER_MISMATCH',
  keyOrSignatureRejected: 'KEY_OR_SIGNATURE_REJECTED',
  assertionTimeInvalid: 'ASSERTION_TIME_INVALID',
  tokenTypeRejected: 'TOKEN_TYPE_REJECTED',
  adapterError: 'ADAPTER_ERROR',
})

const KEY_OR_SIGNATURE_ERROR_CODES = new Set([
  'ERR_JWK_INVALID',
  'ERR_JWKS_INVALID',
  'ERR_JWKS_MULTIPLE_MATCHING_KEYS',
  'ERR_JWKS_NO_MATCHING_KEY',
  'ERR_JWS_SIGNATURE_VERIFICATION_FAILED',
])

function accessVerifierCategory(error) {
  const code = String(error?.code || '')
  const claim = String(error?.claim || '')
  if (code === 'CLOUDFLARE_ACCESS_TOKEN_TYPE_REJECTED') return ACCESS_VERIFIER_CATEGORIES.tokenTypeRejected
  if (code === 'ERR_JWT_EXPIRED' || (code === 'ERR_JWT_CLAIM_VALIDATION_FAILED' && ['exp', 'iat', 'nbf'].includes(claim))) {
    return ACCESS_VERIFIER_CATEGORIES.assertionTimeInvalid
  }
  if (code === 'ERR_JWT_CLAIM_VALIDATION_FAILED' && claim === 'iss') return ACCESS_VERIFIER_CATEGORIES.issuerMismatch
  if (KEY_OR_SIGNATURE_ERROR_CODES.has(code)) return ACCESS_VERIFIER_CATEGORIES.keyOrSignatureRejected
  return ACCESS_VERIFIER_CATEGORIES.adapterError
}

function emitAccessVerifierCategory(sink, category) {
  try {
    sink(category)
  } catch {
    // Diagnostics must never weaken fail-closed authentication.
  }
}

function constantTimeEqual(left, right) {
  const a = Buffer.from(String(left))
  const b = Buffer.from(String(right))
  return a.length === b.length && crypto.timingSafeEqual(a, b)
}

function signValue(value, secret) {
  return crypto.createHmac('sha256', secret).update(value).digest('base64url')
}

function encodeSignedCookie(payload, secret) {
  const value = Buffer.from(JSON.stringify(payload)).toString('base64url')
  return `${value}.${signValue(value, secret)}`
}

function decodeSignedCookie(value, secret, now) {
  if (!value || !secret) return null
  const [payload, signature, extra] = String(value).split('.')
  if (!payload || !signature || extra || !constantTimeEqual(signature, signValue(payload, secret))) return null
  try {
    const decoded = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'))
    if (!Number.isFinite(decoded.expiresAt) || decoded.expiresAt <= now()) return null
    return decoded
  } catch {
    return null
  }
}

function parseCookies(header = '') {
  return String(header).split(';').reduce((cookies, part) => {
    const separator = part.indexOf('=')
    if (separator < 1) return cookies
    const name = part.slice(0, separator).trim()
    const value = part.slice(separator + 1).trim()
    if (name) cookies[name] = value
    return cookies
  }, {})
}

function cookie(name, value, maxAge) {
  return `${name}=${value}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`
}

function clearAuthCookies() {
  return Object.values(COOKIE_NAMES).map((name) => cookie(name, '', 0))
}

function sendJson(response, statusCode, body, headers = {}) {
  response.writeHead(statusCode, { ...NO_STORE_HEADERS, ...headers })
  response.end(JSON.stringify(body))
}

function redirect(response, location, cookies = []) {
  response.writeHead(302, {
    'cache-control': 'no-store',
    location,
    ...(cookies.length ? { 'set-cookie': cookies } : {}),
  })
  response.end()
}

async function readJson(request, limit = 16 * 1024) {
  let body = ''
  for await (const chunk of request) {
    body += chunk
    if (Buffer.byteLength(body) > limit) throw new Error('REQUEST_TOO_LARGE')
  }
  if (!body) return {}
  return JSON.parse(body)
}

function normalizeOrigin(value) {
  if (!value) return ''
  try {
    const url = new URL(value)
    return `${url.protocol}//${url.host}`
  } catch {
    return ''
  }
}

function buildConfig(env, adapters) {
  const authority = String(env.AIOS_ENTRA_AUTHORITY || '').replace(/\/$/, '')
  const publicOrigin = normalizeOrigin(env.AIOS_PUBLIC_ORIGIN)
  const redirectUri = env.AIOS_ENTRA_REDIRECT_URI || (publicOrigin ? `${publicOrigin}/auth/callback` : '')
  const postLogoutRedirectUri = env.AIOS_ENTRA_POST_LOGOUT_REDIRECT_URI || (publicOrigin ? `${publicOrigin}/login` : '')
  const config = {
    publicOrigin,
    authorizeUrl: env.AIOS_ENTRA_AUTHORIZE_URL || (authority ? `${authority}/oauth2/v2.0/authorize` : ''),
    clientId: env.AIOS_ENTRA_CLIENT_ID || '',
    redirectUri,
    logoutUrl: env.AIOS_ENTRA_LOGOUT_URL || (authority ? `${authority}/oauth2/v2.0/logout` : ''),
    postLogoutRedirectUri,
    sessionSecret: env.AIOS_AUTH_SESSION_SECRET || '',
    cloudflareAudience: env.AIOS_CLOUDFLARE_ACCESS_AUD || '',
    turnstileSiteKey: env.AIOS_TURNSTILE_SITE_KEY || '',
    turnstileSecretKey: env.AIOS_TURNSTILE_SECRET_KEY || '',
  }
  const required = [
    'publicOrigin', 'authorizeUrl', 'clientId', 'redirectUri', 'postLogoutRedirectUri',
    'sessionSecret', 'cloudflareAudience', 'turnstileSiteKey', 'turnstileSecretKey',
  ]
  const missing = required.filter((key) => !config[key])
  if (typeof adapters.verifyAccessAssertion !== 'function') missing.push('accessAssertionVerifier')
  if (typeof adapters.exchangeAuthorizationCode !== 'function') missing.push('authorizationCodeExchange')
  if (typeof adapters.verifyIdentityToken !== 'function') missing.push('identityTokenVerifier')
  return { ...config, ready: missing.length === 0, missing }
}

function randomToken(randomBytes, size = 32) {
  return randomBytes(size).toString('base64url')
}

function createPkceChallenge(verifier) {
  return crypto.createHash('sha256').update(verifier).digest('base64url')
}

function requestIp(request) {
  return String(request.headers['cf-connecting-ip'] || request.socket?.remoteAddress || '').split(',')[0].trim()
}

export function createDashboardAuth(options = {}) {
  const env = options.env || process.env
  const fetchImpl = options.fetchImpl || globalThis.fetch
  const now = options.now || Date.now
  const randomBytes = options.randomBytes || crypto.randomBytes
  const accessVerifierCategorySink = typeof options.accessVerifierCategorySink === 'function'
    ? options.accessVerifierCategorySink
    : (category) => console.error(`[dashboard-auth] ${category}`)
  const adapters = {
    verifyAccessAssertion: options.verifyAccessAssertion,
    exchangeAuthorizationCode: options.exchangeAuthorizationCode,
    verifyIdentityToken: options.verifyIdentityToken,
    verifyTurnstile: options.verifyTurnstile,
  }
  const config = buildConfig(env, adapters)

  function sessionFromRequest(request) {
    const cookies = parseCookies(request.headers.cookie)
    return decodeSignedCookie(cookies[COOKIE_NAMES.session], config.sessionSecret, now)
  }

  function pendingFromRequest(request) {
    const cookies = parseCookies(request.headers.cookie)
    return decodeSignedCookie(cookies[COOKIE_NAMES.pending], config.sessionSecret, now)
  }

  async function requireAccess(request, response) {
    const assertion = request.headers['cf-access-jwt-assertion']
    if (!assertion) {
      sendJson(response, 401, {
        authenticated: false,
        code: 'CLOUDFLARE_ACCESS_REQUIRED',
        message: 'Cloudflare Access verification is required.',
      })
      return false
    }
    try {
      const result = await adapters.verifyAccessAssertion(assertion, {
        request,
        audience: config.cloudflareAudience,
      })
      if (!result) throw new Error('ACCESS_REJECTED')
      return true
    } catch (error) {
      emitAccessVerifierCategory(accessVerifierCategorySink, accessVerifierCategory(error))
      sendJson(response, 401, {
        authenticated: false,
        code: 'CLOUDFLARE_ACCESS_REJECTED',
        message: 'Cloudflare Access verification failed.',
      })
      return false
    }
  }

  function requireConfiguration(response) {
    if (config.ready) return true
    sendJson(response, 503, {
      authenticated: false,
      code: 'AUTH_CONFIGURATION_UNAVAILABLE',
      message: 'Authentication is not configured. Access remains closed.',
    })
    return false
  }

  async function beginAuthorization(request, response, mode) {
    if (!requireConfiguration(response) || !(await requireAccess(request, response))) return
    const state = randomToken(randomBytes)
    const nonce = randomToken(randomBytes)
    const verifier = randomToken(randomBytes, 48)
    const statePayload = {
      state,
      nonce,
      verifier,
      mode,
      expiresAt: now() + 10 * 60 * 1000,
    }
    const authorize = new URL(config.authorizeUrl)
    authorize.searchParams.set('client_id', config.clientId)
    authorize.searchParams.set('response_type', 'code')
    authorize.searchParams.set('redirect_uri', config.redirectUri)
    authorize.searchParams.set('response_mode', 'query')
    authorize.searchParams.set('scope', 'openid profile email')
    authorize.searchParams.set('state', state)
    authorize.searchParams.set('nonce', nonce)
    authorize.searchParams.set('code_challenge', createPkceChallenge(verifier))
    authorize.searchParams.set('code_challenge_method', 'S256')
    authorize.searchParams.set('prompt', mode === 'signup' ? 'create' : 'login')
    redirect(response, authorize.toString(), [
      cookie(COOKIE_NAMES.state, encodeSignedCookie(statePayload, config.sessionSecret), 600),
    ])
  }

  async function handleCallback(request, response, url) {
    if (!requireConfiguration(response) || !(await requireAccess(request, response))) return
    const cookies = parseCookies(request.headers.cookie)
    const stateCookie = decodeSignedCookie(cookies[COOKIE_NAMES.state], config.sessionSecret, now)
    const state = url.searchParams.get('state')
    const code = url.searchParams.get('code')
    if (!stateCookie || !state || !constantTimeEqual(stateCookie.state, state) || !code) {
      sendJson(response, 400, { authenticated: false, code: 'INVALID_CALLBACK_STATE' }, {
        'set-cookie': [cookie(COOKIE_NAMES.state, '', 0)],
      })
      return
    }
    try {
      const tokens = await adapters.exchangeAuthorizationCode(code, stateCookie.verifier, { config })
      if (!tokens?.id_token) throw new Error('ENTRA_ID_TOKEN_MISSING')
      const identity = await adapters.verifyIdentityToken(tokens.id_token, stateCookie.nonce, { config })
      if (!identity?.sub) throw new Error('ENTRA_IDENTITY_MISSING')
      const csrfToken = randomToken(randomBytes)
      const pending = encodeSignedCookie({
        sub: identity.sub,
        name: identity.name || '',
        email: identity.email || identity.preferred_username || '',
        csrfToken,
        expiresAt: now() + 10 * 60 * 1000,
      }, config.sessionSecret)
      redirect(response, '/login?stage=turnstile', [
        cookie(COOKIE_NAMES.state, '', 0),
        cookie(COOKIE_NAMES.pending, pending, 600),
      ])
    } catch {
      sendJson(response, 401, { authenticated: false, code: 'ENTRA_CALLBACK_REJECTED' }, {
        'set-cookie': [cookie(COOKIE_NAMES.state, '', 0), cookie(COOKIE_NAMES.pending, '', 0)],
      })
    }
  }

  async function handleSession(request, response) {
    if (!requireConfiguration(response) || !(await requireAccess(request, response))) return
    const session = sessionFromRequest(request)
    if (session) {
      sendJson(response, 200, {
        authenticated: true,
        phase: 'authenticated',
        identity: { name: session.name || '', email: session.email || '' },
        csrfToken: session.csrfToken,
      })
      return
    }
    const pending = pendingFromRequest(request)
    sendJson(response, 200, pending
      ? { authenticated: false, phase: 'turnstile_required', turnstileSiteKey: config.turnstileSiteKey, csrfToken: pending.csrfToken }
      : { authenticated: false, phase: 'identity_required' })
  }

  async function verifyTurnstileToken(token, request) {
    if (typeof adapters.verifyTurnstile === 'function') {
      return adapters.verifyTurnstile(token, { request, config })
    }
    if (!fetchImpl) return false
    const body = new URLSearchParams({
      secret: config.turnstileSecretKey,
      response: token,
      remoteip: requestIp(request),
    })
    const response = await fetchImpl('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body,
    })
    if (!response.ok) return false
    const result = await response.json()
    return result.success === true
  }

  async function handleTurnstile(request, response) {
    if (!requireConfiguration(response) || !(await requireAccess(request, response))) return
    const pending = pendingFromRequest(request)
    if (!pending || !constantTimeEqual(request.headers['x-aios-csrf'] || '', pending.csrfToken)) {
      sendJson(response, 403, { authenticated: false, code: 'INVALID_CSRF_TOKEN' })
      return
    }
    let body
    try {
      body = await readJson(request)
    } catch {
      sendJson(response, 400, { authenticated: false, code: 'INVALID_REQUEST_BODY' })
      return
    }
    if (!body.token || !(await verifyTurnstileToken(body.token, request))) {
      sendJson(response, 403, { authenticated: false, code: 'TURNSTILE_VERIFICATION_FAILED' })
      return
    }
    const session = encodeSignedCookie({
      sub: pending.sub,
      name: pending.name,
      email: pending.email,
      csrfToken: randomToken(randomBytes),
      expiresAt: now() + 8 * 60 * 60 * 1000,
    }, config.sessionSecret)
    sendJson(response, 200, { authenticated: true, destination: '/overview' }, {
      'set-cookie': [cookie(COOKIE_NAMES.pending, '', 0), cookie(COOKIE_NAMES.session, session, 8 * 60 * 60)],
    })
  }

  async function handleLogout(request, response) {
    const session = sessionFromRequest(request)
    if (session && !constantTimeEqual(request.headers['x-aios-csrf'] || '', session.csrfToken)) {
      sendJson(response, 403, { authenticated: true, code: 'INVALID_CSRF_TOKEN' })
      return
    }
    const logoutUrl = config.logoutUrl && config.postLogoutRedirectUri
      ? `${config.logoutUrl}?${new URLSearchParams({ post_logout_redirect_uri: config.postLogoutRedirectUri })}`
      : '/login'
    sendJson(response, 200, { authenticated: false, logoutUrl }, { 'set-cookie': clearAuthCookies() })
  }

  function requireDataAccess(request, response) {
    if (!config.ready) {
      sendJson(response, 503, {
        authenticated: false,
        code: 'AUTH_CONFIGURATION_UNAVAILABLE',
        message: 'Authentication is not configured. Data access remains closed.',
      })
      return false
    }
    const session = sessionFromRequest(request)
    if (!session) {
      sendJson(response, 401, {
        authenticated: false,
        code: 'SESSION_REQUIRED',
        message: 'A valid dashboard session is required.',
      })
      return false
    }
    return true
  }

  async function handler(request, response) {
    const url = new URL(request.url, config.publicOrigin || 'https://dashboard.invalid')
    if (!AUTH_PATHS.has(url.pathname)) return false

    if (url.pathname === '/auth/logout') {
      if (request.method !== 'POST') sendJson(response, 405, { code: 'METHOD_NOT_ALLOWED' }, { allow: 'POST' })
      else await handleLogout(request, response)
      return true
    }
    if (url.pathname === '/auth/turnstile') {
      if (request.method !== 'POST') sendJson(response, 405, { code: 'METHOD_NOT_ALLOWED' }, { allow: 'POST' })
      else await handleTurnstile(request, response)
      return true
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      sendJson(response, 405, { code: 'METHOD_NOT_ALLOWED' }, { allow: 'GET, HEAD' })
      return true
    }
    if (url.pathname === '/auth/session') await handleSession(request, response)
    else if (url.pathname === '/auth/login') await beginAuthorization(request, response, 'login')
    else if (url.pathname === '/auth/signup') await beginAuthorization(request, response, 'signup')
    else if (url.pathname === '/auth/callback') await handleCallback(request, response, url)
    return true
  }

  handler.hasValidSession = (request) => Boolean(config.ready && sessionFromRequest(request))
  handler.requireDataAccess = requireDataAccess
  handler.configuration = () => ({ ready: config.ready, missing: [...config.missing] })
  return handler
}

export { COOKIE_NAMES }
