import assert from 'node:assert/strict'
import test from 'node:test'
import { getLoginPresentation, getLoginProviders } from '../src/pages/loginAuthPresentation.js'

test('identity_required enables the Microsoft sign-in action', () => {
  assert.deepEqual(getLoginPresentation({ phase: 'identity_required' }), {
    available: true,
    tone: 'ready',
    message: 'Use your approved Microsoft identity to continue.',
  })
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
  assert.deepEqual(microsoftOnly.map(({ id, enabled }) => [id, enabled]), [['microsoft', true], ['github', false]])
  const both = getLoginProviders({ phase: 'identity_required', providers: ['microsoft', 'github', 'https://untrusted.test'] })
  assert.deepEqual(both.map(({ href, enabled }) => [href, enabled]), [['/auth/login', true], ['/auth/login?provider=github', true]])
  assert.equal(getLoginProviders({ phase: 'identity_required' })[0].enabled, true)
  assert.equal(getLoginProviders({ phase: 'identity_required', providers: [] }).some(({ enabled }) => enabled), false)
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
