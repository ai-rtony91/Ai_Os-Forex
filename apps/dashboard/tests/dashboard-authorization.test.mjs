import assert from 'node:assert/strict'
import http from 'node:http'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { generateKeyPair, exportJWK, SignJWT } from 'jose'
import { createDashboardApi } from '../server/dashboardApi.js'
import { createDashboardAuthAdapters } from '../server/dashboardAuthAdapters.js'

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
