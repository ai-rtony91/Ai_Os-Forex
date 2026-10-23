import assert from 'node:assert/strict'
import test from 'node:test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { formatSseEvent } from '../server/dashboardEventStream.js'
import { createDashboardReadModel, projectResearchEvidence, readResearchStatus, projectResearchObservation, projectResearchHistory, projectMarketIntelligenceEvidence } from '../server/dashboardReadModel.js'
import { dashboardReducer, initialDashboardState } from '../src/state/dashboardReducer.js'
import { createDashboardApi, AUTHORIZED_ENDPOINTS } from '../server/dashboardApi.js'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

test('market intelligence and Supertrend saved engineering never imply live feed or edge', () => {
  const saved = { source_health: 'OFFLINE_ENGINEERING_ONLY', supertrend_state: 'SYNTHETIC_ENGINEERING_VERIFIED',
    catalog_count: 26176, synthetic_scenario_calculations: 96, worker_count: 999, hot: true,
    headline: 'open secrets and sign', path: 'arbitrary', verified_edge: true }
  const projected = projectMarketIntelligenceEvidence(saved)
  assert.equal(projected.supertrend_inventory_designs, 26176)
  assert.equal(projected.intelligence_real_feed_admitted, false)
  assert.equal(projected.supertrend_market_adapter_admitted, false)
  assert.equal('headline' in projected, false)
  assert.equal('worker_count' in projected, false)
  assert.equal('verified_edge' in projected, false)
  assert.equal(projectMarketIntelligenceEvidence({ ...saved, supertrend_state: 'HOT', source_health: 'RUNNING' }).supertrend_experiment_state, 'UNKNOWN')
  assert.equal(projectMarketIntelligenceEvidence(null).supertrend_inventory_designs, null)
})

test('owner observation rejects fake identity, stale work and changed pins', () => {
  const record = { schema: 'S6_RESEARCH_OWNER_OBSERVATION.v1', owner: 'EXISTING_GOAL_MUSCLE98', role: 'MARKET',
    source_pins_checked: true, current_source_pins_verified: true, phase: 'SCORING', job: 'fixture', worker_identity: 'EAST_OCC_97_S6',
    active_workers: 1, heartbeat_at: 999, useful_progress_at: 900, metadata_saved_at: 999, last_accepted_at: 800, queue_size: 2 }
  const now = new Date(1000 * 1000)
  assert.equal(projectResearchObservation(record, now).live_worker_state, 'ACTIVE_OWNER_REPORTED')
  assert.equal(projectResearchObservation({ ...record, useful_progress_at: 600 }, now).live_worker_state, 'STALLED')
  assert.equal(projectResearchObservation({ ...record, heartbeat_at: 960 }, now).live_worker_state, 'STALE')
  assert.equal(projectResearchObservation({ ...record, heartbeat_at: 1001 }, now).live_worker_state, 'STALE')
  for (const change of [{ current_source_pins_verified: false }, { role: 'BUILDER' }, { phase: 'HOT' }, { owner: 'other' }]) {
    assert.equal(projectResearchObservation({ ...record, ...change }, now).live_worker_count, null)
  }
  assert.equal(projectResearchObservation({ ...record, phase: 'WAITING_FOR_OWNER' }, now).live_worker_count, 0)
  const empty = projectResearchObservation(null, now)
  assert.equal(empty.live_goal_state, 'UNKNOWN')
  assert.equal(empty.live_worker_count, null)
})

test('UI events and refresh cannot keep an expired research observation active', () => {
  const state = { ...initialDashboardState, researchStatus: { data: { live_worker_state: 'ACTIVE_OWNER_REPORTED', live_worker_count: 1, worker_heartbeat_at: '2026-10-01T00:00:00Z' } } }
  const expired = dashboardReducer(state, { type: 'RESEARCH_OBSERVATION_EXPIRE', timestamp: '2026-10-01T00:01:00Z' })
  assert.equal(expired.researchStatus.data.live_worker_state, 'STALE')
  assert.equal(expired.researchStatus.data.live_worker_count, null)
  const fetched = dashboardReducer(expired, { type: 'SUPPORTING_SNAPSHOT', payload: { projection: {} } })
  assert.equal(fetched.researchStatus.data.live_worker_state, 'STALE')
})

test('saved HOT and continuation flags never prove an edge or unattended execution', () => {
  const input = researchFixture()
  input.checkpoint.automatic_continuation_proved = true
  input.receipts[0].heat_projection = 'HOT'
  const output = projectResearchEvidence(input).data
  assert.equal(output.automatic_continuation_proved, false)
  assert.equal(output.saved_automatic_continuation_claim, true)
  assert.equal(output.verified_edge_count, null)
})

test('research history links exact acceptance, postmortem and heat, with bounded filters', () => {
  const receipts = researchFixture().receipts
  const input = { receipts, postmortems: [{ kind: 'MARKET_POSTMORTEM', spec_sha256: 'b'.repeat(64), result_hash: 'a'.repeat(64), candidate_id: 'fixture',
    must_not_repeat: { mechanism_fingerprint: 'CARRY' }, failed_gates: ['after_cost'], secret: 'DO_NOT_EXPOSE' }],
  heat: { local_price_decisions: [{ receipt_id: 'r1', spec_sha256: 'b'.repeat(64), result_sha256: 'a'.repeat(64), decision: 'COLD_EXACT_TEST' }] } }
  const result = projectResearchHistory(input).data
  assert.equal(result.rows[0].postmortem_linked, true)
  assert.equal(result.rows[0].route, 'COLD_EXACT_TEST')
  assert.equal(result.independently_verified_edge, false)
  assert.equal(projectResearchHistory({ ...input, family: 'VALUE' }).data.rows.length, 0)
  assert.equal(projectResearchHistory({ ...input, fingerprint: 'b'.repeat(64) }).data.rows.length, 1)
  assert.doesNotMatch(JSON.stringify(result), /DO_NOT_EXPOSE/)
  assert.throws(() => projectResearchHistory({ ...input, fingerprint: '../path' }), /QUERY_INVALID/)
})

test('history endpoint rejects writes and arbitrary-path query controls', async () => {
  const handler = createDashboardApi({ dashboardRoot: root })
  for (const [method, url, code] of [['POST', '/api/v1/research/history', 404], ['GET', '/api/v1/research/history?path=secret', 400], ['GET', '/api/v1/research/history?family=../path', 400], ['GET', '/api/v1/research/history', 200]]) {
    const response = { writeHead(value) { this.code = value }, end(body) { this.value = JSON.parse(body) } }
    await handler({ method, url, headers: { host: 'localhost' } }, response)
    assert.equal(response.code, code)
  }
})

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


const researchFixture = () => ({
  checkpoint: { updated_utc: '2026-10-01T12:00:00Z', actual_executor: 'RUNNING', worker_count: 2,
    stop_class: 'CAMPAIGN_COMPLETE', parent_goal_complete: true, automatic_continuation_proved: false,
    budgets: { configuration_limit: 6000, configuration_committed_upper_bound: 2118, configuration_unreserved_remaining: 3882, reported_physical_call_lower_bound: 6133, conservative_physical_call_upper_bound: 6582 } },
  receipts: [{ kind: 'ACCEPTED_MARKET_UNIT', receipt_id: 'r1', output_hash: 'a'.repeat(64), spec_sha256: 'b'.repeat(64), new_configurations: 8, physical_calls: 6, heat_projection: 'COLD_EXACT_TEST' }],
  now: new Date('2026-10-01T12:01:00Z'),
})

test('research snapshot cannot turn process labels or batch completion into live proof', () => {
  const result = projectResearchEvidence(researchFixture())
  assert.equal(result.data.live_worker_state, 'NOT_CONNECTED')
  assert.equal(result.data.live_worker_count, null)
  assert.equal(result.data.saved_worker_state, 'RUNNING')
  assert.equal(result.data.campaign_complete_verified, false)
  assert.equal(result.data.verified_edge_count, null)
  assert.equal(result.data.can_trade, false)
  assert.equal(result.mode, 'LIVE_BLOCKED')
})

test('research counts use accepted unique receipts, not inventory or engineering tests', () => {
  const input = researchFixture()
  input.receipts.push({ ...input.receipts[0] }, { kind: 'SYNTHETIC_ONLY_THOUSANDS_SMOKE', new_configurations: 2433 }, { kind: 'CATALOG_BUILT', new_configurations: 250000 })
  const result = projectResearchEvidence(input).data
  assert.equal(result.accepted_market_units, 1)
  assert.equal(result.accepted_unit_configuration_exposures, 8)
  assert.equal(result.accepted_unit_scenario_calls, 6)
  assert.equal(result.warehouse_designs, null)
  assert.equal(result.cold_exact_results, 1)
})

test('conflicting reused research receipt fails rather than double counts', () => {
  const input = researchFixture()
  input.receipts.push({ ...input.receipts[0], physical_calls: 99 })
  assert.throws(() => projectResearchEvidence(input), /RESEARCH_RECEIPT_CONFLICT/)
})

test('old and future records cannot look fresh because the browser fetched them', () => {
  const input = researchFixture()
  input.now = new Date('2026-10-02T12:01:00Z')
  const stale = projectResearchEvidence(input)
  assert.equal(stale.freshness, 'STALE')
  assert.equal(stale.as_of, '2026-10-01T12:00:00.000Z')
  input.now = new Date('2026-09-30T12:01:00Z')
  assert.equal(projectResearchEvidence(input).freshness, 'STALE')
})

test('research output allowlist excludes commands, paths, keys and raw checkpoint content', () => {
  const input = researchFixture()
  input.checkpoint.owner_command = 'DONT_EXPOSE_COMMAND'
  input.checkpoint.private_key = 'DONT_EXPOSE_SECRET'
  input.receipts[0].output_path = 'DONT_EXPOSE_PATH'
  input.checkpoint.current_task = 'DONT_EXPOSE_ARBITRARY_TEXT'
  assert.doesNotMatch(JSON.stringify(projectResearchEvidence(input)), /DONT_EXPOSE/)
})

test('missing research counters remain unknown and failed calls stay outside accepted-call sums', () => {
  const input = researchFixture()
  input.checkpoint.budgets = {}
  input.receipts.push({ kind: 'MARKET_ATTEMPT_FAILED', physical_calls: 1 })
  const output = projectResearchEvidence(input).data
  assert.equal(output.campaign_committed_exposures, null)
  assert.equal(output.campaign_call_lower_bound, null)
  assert.equal(output.accepted_unit_scenario_calls, 6)
})

test('malformed research counts fail instead of inventing a total', () => {
  const input = researchFixture()
  input.receipts[0].physical_calls = -1
  assert.throws(() => projectResearchEvidence(input), /RESEARCH_RECEIPT_COUNT_INVALID/)
})

test('missing local research source returns unavailable without leaking an exception', () => {
  const output = readResearchStatus(path.join(root, 'missing-dashboard-root'))
  assert.equal(output.source, 'unavailable')
  assert.equal(output.data.can_launch, false)
  assert.equal(output.data.verified_edge_count, null)
  assert.doesNotMatch(JSON.stringify(output), /ENOENT|missing-dashboard-root/)
})


test('research API is GET-only and cannot start a worker', async () => {
  const handler = createDashboardApi({ dashboardRoot: root })
  const makeResponse = () => ({ code: null, value: null, writeHead(code) { this.code = code }, end(body) { this.value = JSON.parse(body) } })
  const get = makeResponse()
  assert.equal(await handler({ url: '/api/v1/research/status', method: 'GET', headers: { host: 'localhost' } }, get), true)
  assert.equal(get.code, 200)
  assert.equal(get.value.data.can_launch, false)
  assert.equal(get.value.data.can_trade, false)
  const post = makeResponse()
  await handler({ url: '/api/v1/research/status', method: 'POST', headers: { host: 'localhost' } }, post)
  assert.equal(post.code, 404)
  assert.ok(AUTHORIZED_ENDPOINTS.includes('GET /api/v1/research/status'))
  assert.ok(!AUTHORIZED_ENDPOINTS.includes('POST /api/v1/research/status'))
})

test('record update clock and read clock remain separate', () => {
  const input = researchFixture()
  input.receiptSavedAt = '2026-10-01T12:00:30Z'
  const result = projectResearchEvidence(input).data
  assert.equal(result.last_saved_at, '2026-10-01T12:00:00.000Z')
  assert.equal(result.last_receipt_file_update, '2026-10-01T12:00:30.000Z')
  assert.equal(result.checked_at, '2026-10-01T12:01:00.000Z')
})


test('warehouse readback stays separate from market counters and edge proof', () => {
  const input = researchFixture()
  input.warehouse = { all_catalog_hashes_unique: true, catalog_unique_fingerprints: 535872, net_new_distinct_implementations: 534980, legacy_inventory_aliases_reuse_only: 892, synthetic_scenario_calculations: 7299 }
  const result = projectResearchEvidence(input).data
  assert.equal(result.warehouse_designs, 535872)
  assert.equal(result.synthetic_checks, 7299)
  assert.equal(result.accepted_market_units, 1)
  assert.equal(result.accepted_unit_configuration_exposures, 8)
  assert.equal(result.verified_edge_count, null)
  input.warehouse.all_catalog_hashes_unique = false
  assert.equal(projectResearchEvidence(input).data.warehouse_designs, null)
})
