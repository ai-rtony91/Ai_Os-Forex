import assert from 'node:assert/strict'
import test from 'node:test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { formatSseEvent } from '../server/dashboardEventStream.js'
import { createDashboardReadModel } from '../server/dashboardReadModel.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

test('SSE payloads include UTC timestamp and source', () => {
  const timestamp = new Date().toISOString()
  const message = formatSseEvent('heartbeat', { timestamp, source: 'demonstration' })
  assert.match(message, /^event: heartbeat/m)
  assert.match(message, /"timestamp":".*Z"/)
  assert.match(message, /"source":"demonstration"/)
})

test('broker response excludes account identifiers', () => {
  const broker = createDashboardReadModel(root).brokerStatus()
  assert.doesNotMatch(JSON.stringify(broker), /account_id|accountid/i)
  assert.equal(broker.data.connection_state, 'NOT CONNECTED')
})

test('About response denies affiliation', () => {
  const about = createDashboardReadModel(root).about()
  assert.match(about.data.affiliation, /not affiliated with or endorsed/i)
  assert.equal(about.data.vehicle, '2024 Lamborghini Revuelto')
})
