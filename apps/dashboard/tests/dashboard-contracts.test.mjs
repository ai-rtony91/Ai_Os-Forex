import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createEnvelope, createDashboardReadModel, validateEnvelope } from '../server/dashboardReadModel.js'
import { AUTHORIZED_ENDPOINTS, buildCapabilities, isLoopbackHostname } from '../server/dashboardApi.js'

const dashboardRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

test('API envelope validates and preserves UNKNOWN instead of zero', () => {
  const envelope = createEnvelope({ data: { missing: 'UNKNOWN' } })
  assert.equal(validateEnvelope(envelope), true)
  assert.equal(envelope.data.missing, 'UNKNOWN')
  assert.notEqual(envelope.data.missing, 0)
})

test('demonstration snapshot is explicit and modes remain separated', () => {
  const snapshot = createDashboardReadModel(dashboardRoot).snapshot()
  assert.equal(snapshot.source, 'demonstration')
  assert.match(snapshot.data.label, /NOT BROKER DATA/)
  assert.equal(snapshot.mode, 'PAPER')
  assert.doesNotMatch(JSON.stringify(snapshot.data), /PRACTICE.*LIVE|LIVE.*PRACTICE/)
})

test('local preview capability is never advertised for production hosts', () => {
  assert.equal(isLoopbackHostname('localhost:8080'), true)
  assert.equal(isLoopbackHostname('127.0.0.1:8080'), true)
  assert.equal(isLoopbackHostname('terminal.example.com'), false)
})

test('login providers are explicitly unconfigured', () => {
  const capabilities = buildCapabilities('localhost:8080')
  assert.deepEqual(Object.values(capabilities.authentication), ['NOT CONFIGURED', 'NOT CONFIGURED', 'NOT CONFIGURED', 'NOT CONFIGURED'])
  assert.equal(capabilities.local_preview_available, true)
})

test('no authorized endpoint supports trade or shell execution', () => {
  const snapshot = createDashboardReadModel(dashboardRoot).snapshot()
  assert.doesNotMatch(JSON.stringify(snapshot), /execute_trade|shell_command|child_process/)
  assert.doesNotMatch(AUTHORIZED_ENDPOINTS.join(' '), /trade|order|shell|command/i)
})

test('server keeps local loopback default and binds for Azure App Service when detected', () => {
  const serverSource = fs.readFileSync(path.join(dashboardRoot, 'server.js'), 'utf8')
  assert.match(serverSource, /AIOS_DASHBOARD_HOST/)
  assert.match(serverSource, /WEBSITE_SITE_NAME \? '0\.0\.0\.0' : '127\.0\.0\.1'/)
  assert.match(serverSource, /server\.listen\(port, host/)
})
