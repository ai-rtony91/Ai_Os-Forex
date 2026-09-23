import assert from 'node:assert/strict'
import http from 'node:http'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { generateKeyPair, exportJWK, SignJWT } from 'jose'
import { createDashboardApi } from '../server/dashboardApi.js'
import { createDashboardAuthAdapters } from '../server/dashboardAuthAdapters.js'

const githubTestConfig = {
  githubClientId: 'test-client-id',
  githubRedirectUri: 'https://dashboard.example.test/auth/github/callback',
}
const githubTestEnv = { AIOS_GITHUB_CLIENT_SECRET: 'test-client-secret', AIOS_GITHUB_ALLOWED_USER_IDS: '12345' }

test('GitHub code exchange verifies an approved immutable ID without exposing the provider token', async () => {
  const calls = []
  const adapters = createDashboardAuthAdapters({
    env: githubTestEnv,
    fetchImpl: async (url, request) => {
      calls.push([url, request])
      assert.equal(request.redirect, 'error')
      assert.ok(request.signal instanceof AbortSignal)
      if (url === 'https://github.com/login/oauth/access_token') {
        assert.equal(request.method, 'POST')
        assert.equal(request.body.get('code_verifier'), 'test-pkce-verifier')
        assert.equal(request.body.get('client_secret'), 'test-client-secret')
        assert.equal(request.body.get('redirect_uri'), githubTestConfig.githubRedirectUri)
        return { ok: true, json: async () => ({ access_token: 'private-access-token', token_type: 'bearer', scope: 'read:user' }) }
      }
      assert.equal(url, 'https://api.github.com/user')
      assert.equal(request.headers.authorization, 'Bearer private-access-token')
      return { ok: true, json: async () => ({ id: 12345, login: 'renamed-owner', type: 'User', email: 'untrusted-link@example.test' }) }
    },
  })
  const identity = await adapters.exchangeGitHubAuthorizationCode('test-code', 'test-pkce-verifier', { config: githubTestConfig })
  assert.deepEqual(identity, { sub: 'github:12345', name: 'renamed-owner', email: '' })
  assert.equal(calls.length, 2)
  assert.doesNotMatch(JSON.stringify(identity), /private-access-token|test-client-secret|untrusted-link/)
})

test('GitHub rejects unexpected scopes, provider failures, and accounts outside the user-ID allow-list', async () => {
  const validTokens = { access_token: 'test-token', token_type: 'bearer', scope: 'read:user' }
  const validProfile = { id: 12345, login: 'owner', type: 'User' }
  const cases = [
    { tokens: { ...validTokens, scope: 'read:user,repo' }, expected: /GITHUB_TOKEN_REJECTED/, requests: 1 },
    { tokens: { ...validTokens, scope: undefined }, expected: /GITHUB_TOKEN_REJECTED/, requests: 1 },
    { tokens: { ...validTokens, token_type: 'unexpected' }, expected: /GITHUB_TOKEN_REJECTED/, requests: 1 },
    { tokens: { error: 'bad_verification_code' }, expected: /GITHUB_TOKEN_REJECTED/, requests: 1 },
    { tokenOk: false, expected: /GITHUB_TOKEN_EXCHANGE_FAILED/, requests: 1 },
    { profileOk: false, expected: /GITHUB_IDENTITY_REJECTED/, requests: 2 },
    { profile: { ...validProfile, id: 98765 }, expected: /GITHUB_IDENTITY_NOT_ALLOWED/, requests: 2 },
    { profile: { ...validProfile, id: '12345' }, expected: /GITHUB_IDENTITY_NOT_ALLOWED/, requests: 2 },
    { profile: { ...validProfile, type: 'Organization' }, expected: /GITHUB_IDENTITY_NOT_ALLOWED/, requests: 2 },
    { profile: { ...validProfile, id: Number.MAX_SAFE_INTEGER + 1 }, expected: /GITHUB_IDENTITY_NOT_ALLOWED/, requests: 2 },
  ]
  for (const item of cases) {
    let requests = 0
    const adapters = createDashboardAuthAdapters({
      env: githubTestEnv,
      fetchImpl: async () => {
        requests++
        return requests === 1
          ? { ok: item.tokenOk !== false, json: async () => item.tokens || validTokens }
          : { ok: item.profileOk !== false, json: async () => item.profile || validProfile }
      },
    })
    await assert.rejects(adapters.exchangeGitHubAuthorizationCode('test-code', 'verifier', { config: githubTestConfig }), item.expected)
    assert.equal(requests, item.requests)
  }
})

test('GitHub never calls the provider without a secret and explicit approved user IDs', async () => {
  for (const env of [{}, { ...githubTestEnv, AIOS_GITHUB_ALLOWED_USER_IDS: '' }, { ...githubTestEnv, AIOS_GITHUB_ALLOWED_USER_IDS: 'owner' }, { ...githubTestEnv, AIOS_GITHUB_CLIENT_SECRET: '' }]) {
    const adapters = createDashboardAuthAdapters({ env, fetchImpl: async () => assert.fail('provider must not be called') })
    await assert.rejects(adapters.exchangeGitHubAuthorizationCode('code', 'verifier', { config: githubTestConfig }), /GITHUB_CONFIG_REQUIRED/)
  }
})

function responseRecorder() {
  const result = { statusCode: null, headers: {}, body: '' }
  const response = {
    writeHead(statusCode, headers = {}) {
      result.statusCode = statusCode
      result.headers = Object.fromEntries(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]))
    },
    write(chunk = '') { result.body += chunk ? String(chunk) : '' },
    end(chunk = '') { result.body += chunk ? String(chunk) : '' },
  }
  return { response, result }
}

async function invokeApi(api, { path, method = 'GET', headers = {} }) {
  const request = { url: path, method, headers: { host: '127.0.0.1:8080', ...headers }, on() {} }
  const { response, result } = responseRecorder()
  result.handled = await api(request, response)
  result.json = result.body && result.headers['content-type']?.includes('application/json') ? JSON.parse(result.body) : null
  return result
}

async function withJwksServer(jwk, fn) {
  const server = http.createServer((request, response) => {
    if (request.url === '/cdn-cgi/access/certs' || request.url === '/discovery/v2.0/keys') {
      response.writeHead(200, { 'content-type': 'application/json; charset=utf-8' })
      response.end(JSON.stringify({ keys: [jwk] }))
      return
    }
    response.writeHead(404)
    response.end('not found')
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const origin = `http://127.0.0.1:${address.port}`
  try { return await fn(origin) } finally { await new Promise((resolve) => server.close(resolve)) }
}

test('all non-public dashboard API routes require a server session before returning data', async () => {
  const api = createDashboardApi({
    dashboardRoot: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'),
    requireDataAccess(_request, response) {
      response.writeHead(401, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
      response.end(JSON.stringify({ authenticated: false, code: 'SESSION_REQUIRED' }))
      return false
    },
  })
  const publicHealth = await invokeApi(api, { path: '/api/v1/health' })
  assert.equal(publicHealth.statusCode, 200)
  assert.deepEqual(Object.keys(publicHealth.json.data).sort(), ['read_only', 'service', 'state'])

  const protectedRoutes = [
    '/api/v1/dashboard/snapshot',
    '/api/v1/dashboard/events',
    '/api/v1/market-drivers',
    '/api/v1/broker/status',
    '/api/v1/maintenance/status',
    '/api/v1/about',
    '/api/v1/about/gallery',
    '/api/v1/about/gallery/items/0123456789abcdef0123/image',
  ]
  for (const path of protectedRoutes) {
    const result = await invokeApi(api, { path })
    assert.equal(result.statusCode, 401, path)
    assert.doesNotMatch(result.body, /NOT BROKER DATA|STREAM_CONNECTED|founding_journey|broker/i, path)
  }

  const strategy = await invokeApi(api, { path: '/api/v1/strategy-drafts/validate', method: 'POST' })
  assert.equal(strategy.statusCode, 401)
})

test('auth adapters verify Cloudflare Access and Entra JWTs with issuer, audience, expiry, nonce, and allow-list checks', async () => {
  const { publicKey, privateKey } = await generateKeyPair('RS256')
  const jwk = await exportJWK(publicKey)
  jwk.kid = 'test-key-1'
  jwk.alg = 'RS256'
  jwk.use = 'sig'

  await withJwksServer(jwk, async (origin) => {
    const env = {
      AIOS_CLOUDFLARE_TEAM_DOMAIN: origin,
      AIOS_CLOUDFLARE_ACCESS_AUD: 'access-audience',
      AIOS_ENTRA_AUTHORITY: origin,
      AIOS_ENTRA_ISSUER: `${origin}/issuer`,
      AIOS_ENTRA_JWKS_URI: `${origin}/discovery/v2.0/keys`,
      AIOS_ENTRA_CLIENT_ID: 'client-id',
      AIOS_ENTRA_ALLOWED_EMAILS: 'owner@example.test',
      AIOS_ENTRA_ALLOWED_TENANT_IDS: 'tenant-1',
    }
    const adapters = createDashboardAuthAdapters({ env })
    const access = await new SignJWT({ aud: ['access-audience'], type: 'app', email: 'owner@example.test' })
      .setProtectedHeader({ alg: 'RS256', kid: 'test-key-1' })
      .setIssuer(origin)
      .setSubject('access-subject')
      .setIssuedAt()
      .setExpirationTime('5m')
      .sign(privateKey)
    const accessPayload = await adapters.verifyAccessAssertion(access)
    assert.equal(accessPayload.email, 'owner@example.test')

    const idToken = await new SignJWT({ nonce: 'nonce-1', email: 'owner@example.test', preferred_username: 'owner@example.test', tid: 'tenant-1' })
      .setProtectedHeader({ alg: 'RS256', kid: 'test-key-1' })
      .setIssuer(`${origin}/issuer`)
      .setAudience('client-id')
      .setSubject('entra-subject')
      .setIssuedAt()
      .setExpirationTime('5m')
      .sign(privateKey)
    const identity = await adapters.verifyIdentityToken(idToken, 'nonce-1')
    assert.equal(identity.sub, 'entra-subject')

    await assert.rejects(() => adapters.verifyIdentityToken(idToken, 'wrong-nonce'), /ENTRA_NONCE_REJECTED/)

    const wrongAudience = await new SignJWT({ nonce: 'nonce-1', email: 'owner@example.test', tid: 'tenant-1' })
      .setProtectedHeader({ alg: 'RS256', kid: 'test-key-1' })
      .setIssuer(`${origin}/issuer`)
      .setAudience('other-client')
      .setSubject('entra-subject')
      .setIssuedAt()
      .setExpirationTime('5m')
      .sign(privateKey)
    await assert.rejects(() => adapters.verifyIdentityToken(wrongAudience, 'nonce-1'))

    const wrongEmail = await new SignJWT({ nonce: 'nonce-1', email: 'intruder@example.test', tid: 'tenant-1' })
      .setProtectedHeader({ alg: 'RS256', kid: 'test-key-1' })
      .setIssuer(`${origin}/issuer`)
      .setAudience('client-id')
      .setSubject('entra-subject')
      .setIssuedAt()
      .setExpirationTime('5m')
      .sign(privateKey)
    await assert.rejects(() => adapters.verifyIdentityToken(wrongEmail, 'nonce-1'), /IDENTITY_EMAIL_NOT_ALLOWED/)
  })
})


test('Turnstile adapter accepts only successful siteverify responses for configured hostname', async () => {
  const env = {
    AIOS_TURNSTILE_ALLOWED_HOSTNAMES: 'dashboard.algobots.trade',
  }
  const fetchImpl = async (_url, request) => {
    assert.equal(String(_url), 'https://challenges.cloudflare.com/turnstile/v0/siteverify')
    assert.match(String(request.body), /secret=server-only-turnstile-secret/)
    return { ok: true, json: async () => ({ success: true, hostname: 'dashboard.algobots.trade' }) }
  }
  const adapters = createDashboardAuthAdapters({ env, fetchImpl })
  const accepted = await adapters.verifyTurnstile('valid-token', {
    request: { headers: { 'cf-connecting-ip': '203.0.113.10' } },
    config: { turnstileSecretKey: 'server-only-turnstile-secret' },
  })
  assert.equal(accepted, true)
})

test('Turnstile adapter rejects failed, expired, and wrong-hostname siteverify responses', async () => {
  const env = {
    AIOS_TURNSTILE_ALLOWED_HOSTNAMES: 'dashboard.algobots.trade',
  }
  for (const result of [
    { success: false, hostname: 'dashboard.algobots.trade', 'error-codes': ['timeout-or-duplicate'] },
    { success: true, hostname: 'aios-command-center.mrtonyrodriguez87.chatgpt.site' },
    { success: true, hostname: '' },
  ]) {
    const adapters = createDashboardAuthAdapters({
      env,
      fetchImpl: async () => ({ ok: true, json: async () => result }),
    })
    const accepted = await adapters.verifyTurnstile('candidate-token', {
      request: { headers: { 'cf-connecting-ip': '203.0.113.10' } },
      config: { turnstileSecretKey: 'server-only-turnstile-secret' },
    })
    assert.equal(accepted, false, JSON.stringify(result))
  }
})

function decodeBase64UrlJson(value) {
  return JSON.parse(Buffer.from(value.replace(/-/g, '+').replace(/_/g, '/'), 'base64url').toString('utf8'))
}

test('Entra code exchange uses Key Vault signed certificate client assertion without exposing private key material', async () => {
  const calls = []
  const env = {
    AIOS_ENTRA_AUTHORITY: 'https://login.microsoftonline.com/tenant-id/v2.0',
    AIOS_ENTRA_CLIENT_ASSERTION_KEY_VAULT_KEY_ID: 'https://aios-dashboard-auth-kv.vault.azure.net/keys/aios-entra-client-assertion/key-version',
    AIOS_ENTRA_CLIENT_CERT_THUMBPRINT: '00112233445566778899aabbccddeeff00112233',
    IDENTITY_ENDPOINT: 'https://127.0.0.1/msi/token',
    IDENTITY_HEADER: 'managed-identity-header',
  }
  const fetchImpl = async (url, request = {}) => {
    calls.push({ url: String(url), request })
    if (String(url).startsWith('https://127.0.0.1/msi/token')) {
      assert.equal(new URL(String(url)).searchParams.get('resource'), 'https://vault.azure.net')
      assert.equal(request.headers['x-identity-header'], 'managed-identity-header')
      return { ok: true, json: async () => ({ access_token: 'managed-identity-token' }) }
    }
    if (String(url).startsWith('https://aios-dashboard-auth-kv.vault.azure.net/keys/aios-entra-client-assertion/key-version/sign')) {
      assert.equal(request.headers.authorization, 'Bearer managed-identity-token')
      const body = JSON.parse(request.body)
      assert.equal(body.alg, 'RS256')
      assert.match(body.value, /^[A-Za-z0-9_-]+$/)
      return { ok: true, json: async () => ({ value: 'signed-by-key-vault' }) }
    }
    assert.equal(String(url), 'https://login.microsoftonline.com/tenant-id/v2.0/oauth2/v2.0/token')
    const body = request.body
    const assertion = body.get('client_assertion')
    assert.equal(body.get('client_assertion_type'), 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer')
    assert.equal(body.get('client_id'), 'client-id')
    assert.equal(body.get('code_verifier'), 'pkce-verifier')
    assert.equal(body.get('client_secret'), null)
    const [encodedHeader, encodedPayload, signature] = assertion.split('.')
    assert.equal(signature, 'signed-by-key-vault')
    const header = decodeBase64UrlJson(encodedHeader)
    const payload = decodeBase64UrlJson(encodedPayload)
    assert.equal(header.alg, 'RS256')
    assert.equal(header.typ, 'JWT')
    assert.equal(header.x5t, 'ABEiM0RVZneImaq7zN3u_wARIjM')
    assert.equal(payload.aud, String(url))
    assert.equal(payload.iss, 'client-id')
    assert.equal(payload.sub, 'client-id')
    assert.ok(payload.jti)
    assert.ok(payload.exp > payload.iat)
    assert.ok(payload.exp - payload.iat <= 300)
    return { ok: true, json: async () => ({ id_token: 'id-token' }) }
  }
  const adapters = createDashboardAuthAdapters({ env, fetchImpl })
  const tokens = await adapters.exchangeAuthorizationCode('auth-code', 'pkce-verifier', {
    config: { clientId: 'client-id', redirectUri: 'https://dashboard.algobots.trade/auth/callback' },
  })
  assert.deepEqual(tokens, { id_token: 'id-token' })
  assert.equal(calls.length, 3)
  assert.doesNotMatch(JSON.stringify(calls), /PRIVATE KEY|BEGIN RSA|BEGIN PRIVATE|server-only-turnstile-secret/i)
})

test('Entra certificate assertion fails closed when certificate or Key Vault signing configuration is missing', async () => {
  const baseEnv = {
    AIOS_ENTRA_AUTHORITY: 'https://login.microsoftonline.com/tenant-id/v2.0',
    IDENTITY_ENDPOINT: 'https://127.0.0.1/msi/token',
    IDENTITY_HEADER: 'managed-identity-header',
  }
  const config = { clientId: 'client-id', redirectUri: 'https://dashboard.algobots.trade/auth/callback' }

  const missingThumbprint = createDashboardAuthAdapters({
    env: { ...baseEnv, AIOS_ENTRA_CLIENT_ASSERTION_KEY_VAULT_KEY_ID: 'https://vault.example.test/keys/k/v' },
    fetchImpl: async () => { throw new Error('fetch should not be called') },
  })
  await assert.rejects(() => missingThumbprint.exchangeAuthorizationCode('code', 'verifier', { config }), /ENTRA_CLIENT_CERT_THUMBPRINT_REQUIRED/)

  const missingManagedIdentity = createDashboardAuthAdapters({
    env: {
      AIOS_ENTRA_AUTHORITY: baseEnv.AIOS_ENTRA_AUTHORITY,
      AIOS_ENTRA_CLIENT_ASSERTION_KEY_VAULT_KEY_ID: 'https://vault.example.test/keys/k/v',
      AIOS_ENTRA_CLIENT_CERT_THUMBPRINT: '00112233445566778899aabbccddeeff00112233',
    },
    fetchImpl: async () => { throw new Error('fetch should not be called') },
  })
  await assert.rejects(() => missingManagedIdentity.exchangeAuthorizationCode('code', 'verifier', { config }), /AZURE_MANAGED_IDENTITY_CONFIG_REQUIRED/)
})

test('Entra certificate assertion fails closed when Key Vault signing fails', async () => {
  const env = {
    AIOS_ENTRA_AUTHORITY: 'https://login.microsoftonline.com/tenant-id/v2.0',
    AIOS_ENTRA_CLIENT_ASSERTION_KEY_VAULT_KEY_ID: 'https://vault.example.test/keys/k/v',
    AIOS_ENTRA_CLIENT_CERT_THUMBPRINT: '00112233445566778899aabbccddeeff00112233',
    IDENTITY_ENDPOINT: 'https://127.0.0.1/msi/token',
    IDENTITY_HEADER: 'managed-identity-header',
  }
  const fetchImpl = async (url) => {
    if (String(url).startsWith('https://127.0.0.1/msi/token')) return { ok: true, json: async () => ({ access_token: 'token' }) }
    return { ok: false, json: async () => ({}) }
  }
  const adapters = createDashboardAuthAdapters({ env, fetchImpl })
  await assert.rejects(() => adapters.exchangeAuthorizationCode('code', 'verifier', {
    config: { clientId: 'client-id', redirectUri: 'https://dashboard.algobots.trade/auth/callback' },
  }), /KEY_VAULT_SIGN_FAILED/)
})
