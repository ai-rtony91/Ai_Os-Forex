import assert from 'node:assert/strict'
import test from 'node:test'
import { sanitizeWithReport } from '../server/dashboardSanitizer.js'

test('sanitizer blocks nested secret-like keys in objects and arrays', () => {
  const input = { safe: 1, nested: { access_token: 'never-print', rows: [{ accountId: 'never-print', value: 2 }] } }
  const result = sanitizeWithReport(input)
  assert.deepEqual(result.data, { safe: 1, nested: { rows: [{ value: 2 }] } })
  assert.deepEqual(result.rejectedKeys.sort(), ['access_token', 'accountId'].sort())
})

test('sanitizer report never contains rejected values', () => {
  const sensitiveValue = 'SENSITIVE_FIXTURE_VALUE'
  const result = sanitizeWithReport({ password: sensitiveValue, ok: true })
  assert.doesNotMatch(JSON.stringify(result), new RegExp(sensitiveValue))
  assert.deepEqual(result.data, { ok: true })
})
