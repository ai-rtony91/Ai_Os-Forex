import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { getLoginPresentation, getLoginProviders } from '../src/pages/loginAuthPresentation.js'

const loginPortalSource = readFileSync(fileURLToPath(new URL('../src/pages/LoginPortalPage.jsx', import.meta.url)), 'utf8')
const appShellStyles = readFileSync(fileURLToPath(new URL('../src/app/AiosAppShell.css', import.meta.url)), 'utf8')

test('identity_required enables only providers returned by the server', () => {
  assert.deepEqual(getLoginPresentation({ phase: 'identity_required' }), {
    available: true,
    tone: 'ready',
    message: 'Use your approved Microsoft identity to continue.',
  })
  assert.equal(getLoginProviders({ phase: 'identity_required' }).some(({ enabled }) => enabled), false)
})

test('turnstile_required keeps the action closed and shows the human check', () => {
  const state = getLoginPresentation({ phase: 'turnstile_required' })
  assert.equal(state.available, false)
  assert.match(state.message, /human verification/i)
})

test('configuration, Cloudflare, Turnstile, and network failures remain distinct and closed', () => {
  assert.match(getLoginPresentation({ code: 'AUTH_CONFIGURATION_UNAVAILABLE' }).message, /temporarily unavailable/i)
  assert.match(getLoginPresentation({ code: 'CLOUDFLARE_ACCESS_REJECTED' }).message, /secure access could not be verified/i)
  assert.match(getLoginPresentation({ code: 'TURNSTILE_VERIFICATION_FAILED' }).message, /human verification could not be completed/i)
  assert.match(getLoginPresentation({ phase: 'error' }).message, /authentication service is unavailable/i)
  for (const input of [{ code: 'AUTH_CONFIGURATION_UNAVAILABLE' }, { code: 'CLOUDFLARE_ACCESS_REJECTED' }, { phase: 'error' }]) {
    assert.equal(getLoginPresentation(input).available, false)
  }
})

test('provider actions have fixed local routes and only configured providers are enabled', () => {
  const microsoftOnly = getLoginProviders({ phase: 'identity_required', providers: ['microsoft'] })
  assert.deepEqual(microsoftOnly.map(({ id, label, enabled }) => [id, label, enabled]), [
    ['microsoft', 'SSO with Microsoft', true],
    ['github', 'SSO with GitHub', false],
  ])
  const githubOnly = getLoginProviders({ phase: 'identity_required', providers: ['github'] })
  assert.deepEqual(githubOnly.map(({ id, label, enabled }) => [id, label, enabled]), [
    ['microsoft', 'SSO with Microsoft', false],
    ['github', 'SSO with GitHub', true],
  ])
  const both = getLoginProviders({ phase: 'identity_required', providers: ['microsoft', 'github', 'https://untrusted.test'] })
  assert.deepEqual(both.map(({ href, enabled }) => [href, enabled]), [['/auth/login', true], ['/auth/login?provider=github', true]])
  assert.equal(getLoginProviders({ phase: 'identity_required', providers: [] }).some(({ enabled }) => enabled), false)
})

test('Microsoft SSO button is presented as one integrated control', () => {
  assert.match(loginPortalSource, /microsoftProviderIcon/)
  assert.doesNotMatch(loginPortalSource, /providerSsoBadge/)
  assert.doesNotMatch(appShellStyles, /providerSsoBadge/)
})

test('provider availability never overrides a failed or incomplete authentication check', () => {
  for (const input of [
    { phase: 'checking' }, { phase: 'error' }, { phase: 'turnstile_required' },
    { phase: 'identity_required', code: 'CLOUDFLARE_ACCESS_REJECTED' },
    { phase: 'identity_required', code: 'UNKNOWN_ERROR' },
  ]) {
    assert.equal(getLoginProviders({ ...input, providers: ['microsoft', 'github'] }).some(({ enabled }) => enabled), false)
  }
})
