import assert from 'node:assert/strict'
import fs from 'node:fs'
import { Readable } from 'node:stream'
import test from 'node:test'
import { createDashboardAuth } from '../server/dashboardAuth.js'

const configuredEnv = Object.freeze({
  AIOS_PUBLIC_ORIGIN: 'https://dashboard.example.test',
  AIOS_ENTRA_AUTHORITY: 'https://tenant.example.test/tenant/policy',
  AIOS_ENTRA_CLIENT_ID: 'public-client-id',
  AIOS_ENTRA_REDIRECT_URI: 'https://dashboard.example.test/auth/callback',
  AIOS_ENTRA_POST_LOGOUT_REDIRECT_URI: 'https://dashboard.example.test/login',
  AIOS_AUTH_SESSION_SECRET: 'test-only-session-secret-with-sufficient-length',
  AIOS_CLOUDFLARE_ACCESS_AUD: 'access-audience',
  AIOS_TURNSTILE_SITE_KEY: 'public-turnstile-site-key',
  AIOS_TURNSTILE_SECRET_KEY: 'server-only-turnstile-secret',
})

function adapters(overrides = {}) {
  return {
    verifyAccessAssertion: async (assertion) => assertion === 'valid-access-assertion',
    exchangeAuthorizationCode: async () => ({ id_token: 'opaque-id-token' }),
    verifyIdentityToken: async (_token, nonce) => ({ sub: 'operator-1', name: 'Anthony', email: 'owner@example.test', nonce }),
    verifyTurnstile: async (token) => token === 'valid-turnstile-token',
    ...overrides,
  }
}

async function invoke(handler, { path = '/auth/session', method = 'GET', headers = {}, body = '' } = {}) {
  const request = Readable.from(body ? [body] : [])
  request.url = path
  request.method = method
  request.headers = Object.fromEntries(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]))
  request.socket = { remoteAddress: '127.0.0.1' }
  const result = { statusCode: null, headers: {}, body: '' }
  const response = {
    writeHead(statusCode, responseHeaders = {}) {
      result.statusCode = statusCode
      result.headers = Object.fromEntries(Object.entries(responseHeaders).map(([key, value]) => [key.toLowerCase(), value]))
    },
    end(chunk = '') { result.body += chunk ? String(chunk) : '' },
  }
  result.handled = await handler(request, response)
  result.json = result.body ? JSON.parse(result.body) : null
  return result
}

function updateCookieJar(jar, setCookie = []) {
  for (const item of Array.isArray(setCookie) ? setCookie : [setCookie]) {
    const [pair] = item.split(';')
    const separator = pair.indexOf('=')
    const name = pair.slice(0, separator)
    const value = pair.slice(separator + 1)
    if (value) jar.set(name, value)
    else jar.delete(name)
  }
}

function cookieHeader(jar) {
  return [...jar].map(([name, value]) => `${name}=${value}`).join('; ')
}

test('missing external configuration and verifier adapters fail closed without leaking values', async () => {
  const auth = createDashboardAuth({ env: {}, fetchImpl: null })
  const response = await invoke(auth)
  assert.equal(response.statusCode, 503)
  assert.equal(response.json.authenticated, false)
  assert.equal(response.json.code, 'AUTH_CONFIGURATION_UNAVAILABLE')
  assert.doesNotMatch(response.body, /secret|tenant|site-key/i)
  assert.equal(auth.hasValidSession({ headers: {} }), false)
})

test('only exact authentication routes are handled', async () => {
  const auth = createDashboardAuth({ env: {}, fetchImpl: null })
  const response = await invoke(auth, { path: '/api/runtime/visibility' })
  assert.equal(response.handled, false)
  assert.equal(response.statusCode, null)
})

test('Cloudflare Access is required before login or sign-up begins', async () => {
  const auth = createDashboardAuth({ env: configuredEnv, ...adapters() })
  for (const path of ['/auth/login', '/auth/signup']) {
    const response = await invoke(auth, { path })
    assert.equal(response.statusCode, 401)
    assert.equal(response.json.code, 'CLOUDFLARE_ACCESS_REQUIRED')
  }
})

test('Cloudflare Access verifier failures emit one sanitized server-side category and keep the public 401 unchanged', async () => {
  const cases = [
    [{ code: 'ERR_JWT_CLAIM_VALIDATION_FAILED', claim: 'iss' }, 'ISSUER_MISMATCH'],
    [{ code: 'ERR_JWS_SIGNATURE_VERIFICATION_FAILED' }, 'KEY_OR_SIGNATURE_REJECTED'],
    [{ code: 'ERR_JWT_EXPIRED', claim: 'exp' }, 'ASSERTION_TIME_INVALID'],
    [{ code: 'CLOUDFLARE_ACCESS_TOKEN_TYPE_REJECTED' }, 'TOKEN_TYPE_REJECTED'],
    [{ code: 'UNEXPECTED_ADAPTER_FAILURE' }, 'ADAPTER_ERROR'],
  ]
  const sensitiveMarker = 'sensitive-assertion-material'

  for (const [errorShape, expectedCategory] of cases) {
    const categories = []
    const auth = createDashboardAuth({
      env: configuredEnv,
      ...adapters({
        verifyAccessAssertion: async () => {
          const error = new Error(sensitiveMarker)
          Object.assign(error, errorShape)
          throw error
        },
      }),
      accessVerifierCategorySink: (category) => categories.push(category),
    })
    const response = await invoke(auth, {
      headers: { 'CF-Access-Jwt-Assertion': sensitiveMarker },
    })

    assert.equal(response.statusCode, 401)
    assert.deepEqual(response.json, {
      authenticated: false,
      code: 'CLOUDFLARE_ACCESS_REJECTED',
      message: 'Cloudflare Access verification failed.',
    })
    assert.deepEqual(categories, [expectedCategory])
    assert.doesNotMatch(JSON.stringify(categories), new RegExp(sensitiveMarker))
    assert.doesNotMatch(response.body, new RegExp(sensitiveMarker))
  }
})

test('a false verifier result emits ADAPTER_ERROR once and remains denied if the diagnostic sink fails', async () => {
  let emissions = 0
  const auth = createDashboardAuth({
    env: configuredEnv,
    ...adapters({ verifyAccessAssertion: async () => false }),
    accessVerifierCategorySink: (category) => {
      emissions += 1
      assert.equal(category, 'ADAPTER_ERROR')
      throw new Error('diagnostic sink unavailable')
    },
  })
  const response = await invoke(auth, {
    headers: { 'CF-Access-Jwt-Assertion': 'rejected-access-assertion' },
  })

  assert.equal(emissions, 1)
  assert.equal(response.statusCode, 401)
  assert.equal(response.json.code, 'CLOUDFLARE_ACCESS_REJECTED')
})

test('login and sign-up redirects use PKCE, callback state, secure cookies, and distinct prompts', async () => {
  const auth = createDashboardAuth({ env: configuredEnv, ...adapters() })
  for (const [path, prompt] of [['/auth/login', 'login'], ['/auth/signup', 'create']]) {
    const response = await invoke(auth, { path, headers: { 'CF-Access-Jwt-Assertion': 'valid-access-assertion' } })
    assert.equal(response.statusCode, 302)
    const location = new URL(response.headers.location)
    assert.equal(location.searchParams.get('client_id'), 'public-client-id')
    assert.equal(location.searchParams.get('redirect_uri'), configuredEnv.AIOS_ENTRA_REDIRECT_URI)
    assert.equal(location.searchParams.get('code_challenge_method'), 'S256')
    assert.ok(location.searchParams.get('code_challenge'))
    assert.ok(location.searchParams.get('state'))
    assert.equal(location.searchParams.get('prompt'), prompt)
    assert.match(response.headers['set-cookie'][0], /HttpOnly; Secure; SameSite=Lax/)
    assert.doesNotMatch(response.headers.location, /session-secret|turnstile-secret/)
  }
})

test('callback state is mandatory and a successful callback creates only a pending Turnstile identity', async () => {
  const auth = createDashboardAuth({ env: configuredEnv, ...adapters() })
  const jar = new Map()
  const start = await invoke(auth, { path: '/auth/login', headers: { 'CF-Access-Jwt-Assertion': 'valid-access-assertion' } })
  updateCookieJar(jar, start.headers['set-cookie'])
  const state = new URL(start.headers.location).searchParams.get('state')

  const rejected = await invoke(auth, {
    path: '/auth/callback?code=code-1&state=wrong-state',
    headers: { 'CF-Access-Jwt-Assertion': 'valid-access-assertion', cookie: cookieHeader(jar) },
  })
  assert.equal(rejected.statusCode, 400)
  assert.equal(rejected.json.code, 'INVALID_CALLBACK_STATE')

  const accepted = await invoke(auth, {
    path: `/auth/callback?code=code-1&state=${encodeURIComponent(state)}`,
    headers: { 'CF-Access-Jwt-Assertion': 'valid-access-assertion', cookie: cookieHeader(jar) },
  })
  assert.equal(accepted.statusCode, 302)
  assert.equal(accepted.headers.location, '/login?stage=turnstile')
  assert.ok(accepted.headers['set-cookie'].some((value) => value.startsWith('__Host-aios-auth-pending=')))
  assert.ok(accepted.headers['set-cookie'].every((value) => /HttpOnly; Secure; SameSite=Lax/.test(value)))
  assert.ok(accepted.headers['set-cookie'].every((value) => !value.startsWith('__Host-aios-session=') || value.startsWith('__Host-aios-session=;')))
})

test('Turnstile runs after Access and callback but before server session creation', async () => {
  const calls = []
  const auth = createDashboardAuth({
    env: configuredEnv,
    ...adapters({
      verifyAccessAssertion: async () => { calls.push('access'); return true },
      exchangeAuthorizationCode: async () => { calls.push('exchange'); return { id_token: 'opaque-id-token' } },
      verifyIdentityToken: async () => { calls.push('identity'); return { sub: 'operator-1', name: 'Anthony' } },
      verifyTurnstile: async () => { calls.push('turnstile'); return true },
    }),
  })
  const jar = new Map()
  const access = { 'CF-Access-Jwt-Assertion': 'valid-access-assertion' }
  const start = await invoke(auth, { path: '/auth/login', headers: access })
  updateCookieJar(jar, start.headers['set-cookie'])
  const state = new URL(start.headers.location).searchParams.get('state')
  const callback = await invoke(auth, {
    path: `/auth/callback?code=code-1&state=${encodeURIComponent(state)}`,
    headers: { ...access, cookie: cookieHeader(jar) },
  })
  updateCookieJar(jar, callback.headers['set-cookie'])

  const pending = await invoke(auth, { path: '/auth/session', headers: { ...access, cookie: cookieHeader(jar) } })
  assert.equal(pending.statusCode, 200)
  assert.equal(pending.json.phase, 'turnstile_required')
  assert.equal(pending.json.turnstileSiteKey, 'public-turnstile-site-key')

  const badCsrf = await invoke(auth, {
    path: '/auth/turnstile', method: 'POST',
    headers: { ...access, cookie: cookieHeader(jar), 'content-type': 'application/json', 'x-aios-csrf': 'wrong' },
    body: JSON.stringify({ token: 'valid-turnstile-token' }),
  })
  assert.equal(badCsrf.statusCode, 403)
  assert.equal(badCsrf.json.code, 'INVALID_CSRF_TOKEN')

  const verified = await invoke(auth, {
    path: '/auth/turnstile', method: 'POST',
    headers: { ...access, cookie: cookieHeader(jar), 'content-type': 'application/json', 'x-aios-csrf': pending.json.csrfToken },
    body: JSON.stringify({ token: 'valid-turnstile-token' }),
  })
  assert.equal(verified.statusCode, 200)
  assert.equal(verified.json.destination, '/overview')
  assert.ok(verified.headers['set-cookie'].some((value) => value.startsWith('__Host-aios-session=')))
  assert.deepEqual(calls, ['access', 'access', 'exchange', 'identity', 'access', 'access', 'access', 'turnstile'])
})



test('Turnstile fails closed when public site key is absent', async () => {
  const env = { ...configuredEnv }
  delete env.AIOS_TURNSTILE_SITE_KEY
  const auth = createDashboardAuth({ env, ...adapters() })
  const response = await invoke(auth, { path: '/auth/session', headers: { 'CF-Access-Jwt-Assertion': 'valid-access-assertion' } })
  assert.equal(response.statusCode, 503)
  assert.equal(response.json.code, 'AUTH_CONFIGURATION_UNAVAILABLE')
  assert.doesNotMatch(response.body, /server-only-turnstile-secret|public-turnstile-site-key/)
})

test('invalid or missing Turnstile token is denied before session creation', async () => {
  const auth = createDashboardAuth({ env: configuredEnv, ...adapters() })
  const jar = new Map()
  const access = { 'CF-Access-Jwt-Assertion': 'valid-access-assertion' }
  const start = await invoke(auth, { path: '/auth/login', headers: access })
  updateCookieJar(jar, start.headers['set-cookie'])
  const state = new URL(start.headers.location).searchParams.get('state')
  const callback = await invoke(auth, {
    path: `/auth/callback?code=code-1&state=${encodeURIComponent(state)}`,
    headers: { ...access, cookie: cookieHeader(jar) },
  })
  updateCookieJar(jar, callback.headers['set-cookie'])
  const pending = await invoke(auth, { path: '/auth/session', headers: { ...access, cookie: cookieHeader(jar) } })

  for (const body of [{}, { token: '' }, { token: 'expired-or-invalid-token' }]) {
    const denied = await invoke(auth, {
      path: '/auth/turnstile', method: 'POST',
      headers: { ...access, cookie: cookieHeader(jar), 'content-type': 'application/json', 'x-aios-csrf': pending.json.csrfToken },
      body: JSON.stringify(body),
    })
    assert.equal(denied.statusCode, 403)
    assert.equal(denied.json.code, 'TURNSTILE_VERIFICATION_FAILED')
    assert.doesNotMatch(denied.body, /server-only-turnstile-secret|public-turnstile-site-key/)
  }
})

test('Turnstile client integration uses only public site key and never exposes server secret', () => {
  const login = fs.readFileSync(new URL('../src/pages/LoginPortalPage.jsx', import.meta.url), 'utf8')
  assert.match(login, /https:\/\/challenges\.cloudflare\.com\/turnstile\/v0\/api\.js\?render=explicit/)
  assert.match(login, /authState\.turnstileSiteKey/)
  assert.match(login, /fetch\('\/auth\/turnstile'/)
  assert.doesNotMatch(login, /AIOS_TURNSTILE_SECRET_KEY|turnstileSecretKey|server-only-turnstile-secret|secret:/)
})

test('logout requires session CSRF and clears all authentication cookies', async () => {
  const auth = createDashboardAuth({ env: configuredEnv, ...adapters() })
  const withoutSession = await invoke(auth, { path: '/auth/logout', method: 'POST' })
  assert.equal(withoutSession.statusCode, 200)
  assert.equal(withoutSession.json.authenticated, false)
  assert.equal(withoutSession.headers['set-cookie'].length, 3)
  assert.ok(withoutSession.headers['set-cookie'].every((value) => /Max-Age=0; HttpOnly; Secure; SameSite=Lax/.test(value)))
})

test('portal uses the owner-selected complete artwork and has no localhost no-auth bypass or placeholder fallback', () => {
  const login = fs.readFileSync(new URL('../src/pages/LoginPortalPage.jsx', import.meta.url), 'utf8')
  const symbol = fs.readFileSync(new URL('../src/AiosSymbol.jsx', import.meta.url), 'utf8')
  const symbolCss = fs.readFileSync(new URL('../src/AiosSymbol.css', import.meta.url), 'utf8')
  const motion = fs.readFileSync(new URL('../src/design/aios-motion.css', import.meta.url), 'utf8')
  assert.match(login, /newLoginBackgroundUrl/)
  assert.match(login, /'orbitron'/)
  assert.match(login, /className="loginArtwork"/)
  assert.doesNotMatch(login, /AiosSymbol|MarketConstellation|Slanted partial-A|Signal tower|Orbital globe|Dollar coin/i)
  assert.doesNotMatch(login, /LOCAL PREVIEW|NO AUTH|placeholder|emoji/i)
  assert.match(symbol, /markA/)
  assert.match(symbol, /markI/)
  assert.match(symbol, /markO/)
  assert.match(symbol, /markS/)
  assert.match(symbolCss, /globeClockwise/)
  assert.match(symbolCss, /ringCounterClockwise/)
  assert.match(motion, /rotate\(360deg\)/)
  assert.match(motion, /rotate\(-360deg\)/)
})
