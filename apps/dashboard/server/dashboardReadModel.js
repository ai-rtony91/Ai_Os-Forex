import fs from 'node:fs'
import path from 'node:path'
import { Buffer } from 'node:buffer'
import { createHash } from 'node:crypto'
import { sanitizeDashboardPayload } from './dashboardSanitizer.js'

export const DASHBOARD_SCHEMA_VERSION = 'aios.dashboard.v1'
export const EXECUTION_MODES = Object.freeze(['BACKTEST', 'REPLAY', 'PAPER', 'PRACTICE', 'LIVE_BLOCKED', 'HALTED', 'UNKNOWN'])
export const DATA_SOURCES = Object.freeze(['runtime', 'demonstration', 'unavailable'])

export function createEnvelope({ source = 'unavailable', mode = 'UNKNOWN', freshness = 'UNKNOWN', data = {}, asOf = new Date().toISOString() } = {}) {
  return {
    schema_version: DASHBOARD_SCHEMA_VERSION,
    source: DATA_SOURCES.includes(source) ? source : 'unavailable',
    mode: EXECUTION_MODES.includes(mode) ? mode : 'UNKNOWN',
    as_of: asOf,
    freshness: ['FRESH', 'STALE', 'UNKNOWN'].includes(freshness) ? freshness : 'UNKNOWN',
    data: sanitizeDashboardPayload(data),
  }
}

export function validateEnvelope(envelope) {
  return Boolean(
    envelope?.schema_version === DASHBOARD_SCHEMA_VERSION
    && DATA_SOURCES.includes(envelope.source)
    && EXECUTION_MODES.includes(envelope.mode)
    && !Number.isNaN(Date.parse(envelope.as_of))
    && ['FRESH', 'STALE', 'UNKNOWN'].includes(envelope.freshness)
    && envelope.data && typeof envelope.data === 'object' && !Array.isArray(envelope.data)
  )
}

export function readFixture(dashboardRoot, fileName) {
  const fixturePath = path.resolve(dashboardRoot, 'mock-data', fileName)
  const fixtureRoot = path.resolve(dashboardRoot, 'mock-data')
  if (!fixturePath.startsWith(`${fixtureRoot}${path.sep}`)) throw new Error('Fixture path rejected.')
  return JSON.parse(fs.readFileSync(fixturePath, 'utf8'))
}

export function createDashboardReadModel(dashboardRoot) {
  const fixture = (name) => createEnvelope(readFixture(dashboardRoot, name))
  return {
    snapshot: () => fixture('aios-obsidian-dashboard-v1.example.json'),
    researchStatus: () => readResearchStatus(dashboardRoot),
    researchHistory: (query) => readResearchHistory(dashboardRoot, query),
    marketDrivers: () => fixture('aios-market-drivers-v1.example.json'),
    about: () => fixture('aios-about-v1.example.json'),
    brokerStatus: () => createEnvelope({ source: 'unavailable', mode: 'LIVE_BLOCKED', data: {
      broker_name: 'OANDA architecture reference', environment: 'NOT CONNECTED', connection_state: 'NOT CONNECTED',
      api_latency: 'UNAVAILABLE', last_heartbeat: 'UNKNOWN', instrument_count: 'UNKNOWN', data_freshness: 'UNKNOWN',
      orders_today: 'UNKNOWN', rejection_count: 'UNKNOWN', spread_state: 'UNKNOWN', account_synchronization_state: 'NOT CONNECTED',
      credential_handling_state: 'RUNTIME ONLY',
    }}),
    maintenanceStatus: () => createEnvelope({ source: 'unavailable', mode: 'UNKNOWN', data: {
      system_health: 'UNKNOWN', repository_state: 'UNAVAILABLE', dashboard_build_state: 'UNKNOWN', test_state: 'UNKNOWN',
      published_version: 'NOT CONFIGURED', broker_adapter_state: 'NOT CONNECTED', dataset_state: 'UNAVAILABLE',
      backup_state: 'UNAVAILABLE', dependency_review_state: 'UNKNOWN', configuration_drift: 'UNKNOWN', pending_maintenance_reviews: 'UNKNOWN',
    }}),
  }
}


const RESEARCH_RELATIVE_ROOT = '.aios/staging/forex_edge_master_tournament_v1/outcome_campaign_v3/research_binding_s6'
const RESEARCH_MAX_FILE_BYTES = 2 * 1024 * 1024
const FIXED_RESEARCH_CODE = [`${RESEARCH_RELATIVE_ROOT}/research_binding.py`, `${RESEARCH_RELATIVE_ROOT}/research_consumer.py`,
  `${RESEARCH_RELATIVE_ROOT}/finalize_evidence.py`, 'automation/orchestration/continuation/aios_autonomous_job_continuation.py']
const STOP_CLASSES = new Set(['OWNER_ACTION_REQUIRED', 'SAFETY_INTEGRITY_BLOCK', 'RESOURCE_TIME_BLOCK', 'UNRECOVERABLE_FAILURE', 'CAMPAIGN_COMPLETE'])
const safeCount = (value) => Number.isSafeInteger(value) && value >= 0 ? value : null
const safeStamp = (value) => typeof value === 'string' && Number.isFinite(Date.parse(value)) ? new Date(value).toISOString() : null
const safeIdentity = (value) => typeof value === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(value) ? value : null
const secondsStamp = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? new Date(value * 1000).toISOString() : null

export function projectResearchObservation(observation, now = new Date()) {
  const empty = { live_worker_state: 'NOT_CONNECTED', live_worker_count: null, current_phase: 'UNKNOWN', current_job: null,
    worker_identity: null, queue_size: null, worker_heartbeat_at: null, useful_progress_at: null,
    observation_saved_at: null, last_accepted_at: null, observation_kind: 'OWNER_REPORTED_NOT_PROCESS_PROBE', live_goal_state: 'UNKNOWN' }
  const phaseLimits = { READING: 120, SCORING: 300, SAVING: 60, CHECKING: 60, ROUTING: 60, STOPPED: 0, WAITING_FOR_OWNER: 0 }
  if (!observation || observation.schema !== 'S6_RESEARCH_OWNER_OBSERVATION.v1' || observation.owner !== 'EXISTING_GOAL_MUSCLE98'
    || observation.role !== 'MARKET' || observation.source_pins_checked !== true || observation.current_source_pins_verified !== true
    || !Object.hasOwn(phaseLimits, observation.phase)) return empty
  const checked = new Date(now).getTime() / 1000
  const validTime = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= checked
  const fresh = validTime(observation.heartbeat_at) && checked - observation.heartbeat_at <= 30
  const useful = validTime(observation.useful_progress_at) && checked - observation.useful_progress_at <= phaseLimits[observation.phase]
  let state = 'UNKNOWN'
  let count = null
  if (!fresh) state = 'STALE'
  else if (['STOPPED', 'WAITING_FOR_OWNER'].includes(observation.phase)) { state = observation.phase; count = 0 }
  else if (!useful) state = 'STALLED'
  else if (safeIdentity(observation.worker_identity) && safeIdentity(observation.job) && observation.active_workers === 1) { state = 'ACTIVE_OWNER_REPORTED'; count = 1 }
  return { ...empty, live_worker_state: state, live_worker_count: count, current_phase: observation.phase,
    current_job: safeIdentity(observation.job), worker_identity: safeIdentity(observation.worker_identity), queue_size: safeCount(observation.queue_size),
    worker_heartbeat_at: validTime(observation.heartbeat_at) ? secondsStamp(observation.heartbeat_at) : null,
    useful_progress_at: validTime(observation.useful_progress_at) ? secondsStamp(observation.useful_progress_at) : null,
    observation_saved_at: validTime(observation.metadata_saved_at) ? secondsStamp(observation.metadata_saved_at) : null,
    last_accepted_at: validTime(observation.last_accepted_at) ? secondsStamp(observation.last_accepted_at) : null }
}

// Saved research records are evidence of past work, not a live worker heartbeat.
export function projectResearchEvidence({ checkpoint, receipts, warehouse = null, observation = null, receiptSavedAt = null, now = new Date(), staleAfterMs = 120000 }) {
  if (!checkpoint || typeof checkpoint !== 'object' || Array.isArray(checkpoint) || !Array.isArray(receipts)) throw new Error('RESEARCH_INPUT_INVALID')
  const checkedAt = new Date(now)
  if (!Number.isFinite(checkedAt.getTime())) throw new Error('RESEARCH_TIME_INVALID')
  const lastSaved = safeStamp(checkpoint.updated_utc)
  const age = lastSaved ? checkedAt.getTime() - Date.parse(lastSaved) : null
  const fresh = age !== null && age >= 0 && age <= staleAfterMs
  const accepted = new Map()
  for (const row of receipts) {
    if (row?.kind !== 'ACCEPTED_MARKET_UNIT') continue
    if (typeof row.receipt_id !== 'string' || typeof row.output_hash !== 'string' || !/^[a-f0-9]{64}$/i.test(row.output_hash)) throw new Error('RESEARCH_RECEIPT_INVALID')
    if (safeCount(row.new_configurations) === null || safeCount(row.physical_calls) === null) throw new Error('RESEARCH_RECEIPT_COUNT_INVALID')
    const signature = JSON.stringify([row.output_hash, row.spec_sha256 ?? null, row.new_configurations, row.physical_calls, row.heat_projection ?? null])
    if (accepted.has(row.receipt_id) && accepted.get(row.receipt_id).signature !== signature) throw new Error('RESEARCH_RECEIPT_CONFLICT')
    accepted.set(row.receipt_id, { signature, row })
  }
  const rows = [...accepted.values()].map(({ row }) => row)
  const budgets = checkpoint.budgets ?? {}
  const stop = STOP_CLASSES.has(checkpoint.stop_class) ? checkpoint.stop_class : 'UNKNOWN'
  const recordedState = ['STOPPED', 'RUNNING', 'TESTED', 'COMPLETE', 'BLOCKED'].includes(checkpoint.actual_executor) ? checkpoint.actual_executor : 'UNKNOWN'
  const countHeat = (label) => rows.filter((row) => row.heat_projection === label).length
  const warehouseRecorded = warehouse?.all_catalog_hashes_unique === true && safeCount(warehouse.catalog_unique_fingerprints) !== null
  return createEnvelope({
    source: 'runtime', mode: 'LIVE_BLOCKED', freshness: fresh ? 'FRESH' : 'STALE',
    asOf: lastSaved ?? checkedAt.toISOString(),
    data: {
      label: 'SAVED RESEARCH RECORDS - NOT LIVE WORKER PROOF',
      checked_at: checkedAt.toISOString(), last_saved_at: lastSaved,
      last_receipt_file_update: safeStamp(receiptSavedAt),
      last_saved_age_seconds: age !== null && age >= 0 ? Math.floor(age / 1000) : null,
      live_worker_state: 'NOT_CONNECTED', live_worker_count: null, live_goal_state: 'UNKNOWN',
      saved_worker_state: recordedState, saved_worker_count: safeCount(checkpoint.worker_count), saved_stop_class: stop,
      accepted_market_units: rows.length,
      accepted_unit_configuration_exposures: rows.reduce((sum, row) => sum + row.new_configurations, 0),
      accepted_unit_scenario_calls: rows.reduce((sum, row) => sum + row.physical_calls, 0),
      cold_exact_results: countHeat('COLD_EXACT_TEST'),
      warm_recorded_results: countHeat('WARM'), hot_recorded_results: countHeat('HOT'),
      other_recorded_results: rows.filter((row) => !['COLD_EXACT_TEST', 'WARM', 'HOT'].includes(row.heat_projection)).length,
      campaign_configuration_limit: safeCount(budgets.configuration_limit),
      campaign_committed_exposures: safeCount(budgets.configuration_committed_upper_bound),
      campaign_remaining_exposures: safeCount(budgets.configuration_unreserved_remaining),
      campaign_call_lower_bound: safeCount(budgets.reported_physical_call_lower_bound),
      campaign_call_upper_bound: safeCount(budgets.conservative_physical_call_upper_bound),
      research_deadline: safeStamp(budgets.research_ends),
      warehouse_designs: warehouseRecorded ? warehouse.catalog_unique_fingerprints : null,
      warehouse_new_designs: warehouseRecorded ? safeCount(warehouse.net_new_distinct_implementations) : null,
      warehouse_legacy_aliases: warehouseRecorded ? safeCount(warehouse.legacy_inventory_aliases_reuse_only) : null,
      warehouse_evidence: warehouseRecorded ? 'RECORDED_CATALOG_TEST_READBACK_NOT_MARKET_RESULTS' : 'NOT_CONNECTED',
      synthetic_checks: warehouseRecorded ? safeCount(warehouse.synthetic_scenario_calculations) : null,
      verified_edge_count: null,
      live_proof_verifier_connected: false, campaign_complete_verified: false,
      receipt_validation: 'STRUCTURE_AND_DUPLICATE_CHECK_ONLY',
      automatic_continuation_proved: false,
      saved_automatic_continuation_claim: checkpoint.automatic_continuation_proved === true,
      real_scout_configurations: null, static_rejected_specs: null, blocked_specs: null,
      distinct_trade_sequences: null, independent_proof_candidates: null,
      builder_worker_state: 'UNKNOWN', builder_worker_count: null,
      ...projectMarketIntelligenceEvidence(checkpoint.market_intelligence),
      ...projectResearchObservation(observation, checkedAt),
      next_step: stop === 'OWNER_ACTION_REQUIRED' ? 'Review the saved owner gate; it may have changed since this record.' : 'Check the current worker and next approved job.',
      read_only: true, can_launch: false, can_sign: false, can_trade: false,
    },
  })
}

export function projectMarketIntelligenceEvidence(saved) {
  // Fixed scalar projection of saved engineering evidence. Never follows paths,
  // publishes raw headlines, infers worker presence, or turns a score into HOT.
  const sourceStates = new Set(['OFFLINE_ENGINEERING_ONLY', 'DATA_BLOCKED', 'UNKNOWN', 'STALE'])
  const experimentStates = new Set(['SYNTHETIC_ENGINEERING_VERIFIED', 'DATA_BLOCKED', 'PREPARING', 'UNKNOWN'])
  const valid = saved && typeof saved === 'object' && !Array.isArray(saved)
  return {
    intelligence_source_health: valid && sourceStates.has(saved.source_health) ? saved.source_health : 'UNKNOWN',
    supertrend_experiment_state: valid && experimentStates.has(saved.supertrend_state) ? saved.supertrend_state : 'UNKNOWN',
    supertrend_inventory_designs: valid ? safeCount(saved.catalog_count) : null,
    supertrend_synthetic_cost_checks: valid ? safeCount(saved.synthetic_scenario_calculations) : null,
    intelligence_real_feed_admitted: false,
    supertrend_market_adapter_admitted: false,
    intelligence_evidence_kind: 'SAVED_ENGINEERING_ONLY_NOT_LIVE_OR_EDGE',
  }
}

function boundedResearchRead(repoRoot, relativePath, fixedCode = false) {
  const expected = path.resolve(repoRoot, relativePath)
  const realRoot = fs.realpathSync(repoRoot)
  const realPath = fs.realpathSync(expected)
  if (fixedCode && !FIXED_RESEARCH_CODE.includes(relativePath)) throw new Error('RESEARCH_CODE_PATH_REJECTED')
  const allowedRoot = fixedCode ? realRoot : path.join(realRoot, RESEARCH_RELATIVE_ROOT)
  if (!realPath.startsWith(`${allowedRoot}${path.sep}`) || realPath !== path.join(realRoot, relativePath)) throw new Error('RESEARCH_PATH_REJECTED')
  const fd = fs.openSync(realPath, 'r')
  try {
    const before = fs.fstatSync(fd)
    if (!before.isFile() || before.size > RESEARCH_MAX_FILE_BYTES) throw new Error('RESEARCH_RECORD_TOO_LARGE')
    const buffer = Buffer.alloc(before.size)
    let offset = 0
    while (offset < buffer.length) {
      const count = fs.readSync(fd, buffer, offset, buffer.length - offset, offset)
      if (!count) throw new Error('RESEARCH_RECORD_CHANGED')
      offset += count
    }
    const after = fs.fstatSync(fd)
    if (after.size !== before.size || after.mtimeMs !== before.mtimeMs) throw new Error('RESEARCH_RECORD_CHANGED')
    return { text: buffer.toString('utf8').replace(/^\uFEFF/, ''), sha256: createHash('sha256').update(buffer).digest('hex'), stamp: `${before.size}:${before.mtimeMs}:${before.ino}`, filePath: realPath, modifiedAt: new Date(before.mtimeMs).toISOString() }
  } finally { fs.closeSync(fd) }
}

export function readResearchStatus(dashboardRoot, now = new Date()) {
  try {
    const sourceRoot = path.basename(dashboardRoot) === 'dist' ? path.dirname(dashboardRoot) : dashboardRoot
    const repoRoot = path.resolve(sourceRoot, '..', '..')
    const checkpointFile = boundedResearchRead(repoRoot, `${RESEARCH_RELATIVE_ROOT}/STATUS_CHECKPOINT.json`)
    const receiptFile = boundedResearchRead(repoRoot, `${RESEARCH_RELATIVE_ROOT}/RESULT_RECEIPTS.jsonl`)
    const checkpoint = JSON.parse(checkpointFile.text)
    const receipts = receiptFile.text.split(/\r?\n/).filter((line) => line.trim()).map((line) => JSON.parse(line))
    let warehouseFile = null
    let warehouse = null
    try {
      warehouseFile = boundedResearchRead(repoRoot, `${RESEARCH_RELATIVE_ROOT}/tests/bait_warehouse_100x_20261001/VALIDATION_READBACK.json`)
      warehouse = JSON.parse(warehouseFile.text)
    } catch { warehouseFile = null }
    let observationFile = null
    let observation = null
    try {
      observationFile = boundedResearchRead(repoRoot, `${RESEARCH_RELATIVE_ROOT}/MARKET_WORKER_OBSERVATION.json`)
      observation = JSON.parse(observationFile.text)
      // Only these fixed code files are hashed. Never follow a path from an observation.
      observation.current_source_pins_verified = FIXED_RESEARCH_CODE.every((relative) => {
        const expected = path.join(repoRoot, relative)
        const expectedHash = observation.source_pins?.[expected]
        return typeof expectedHash === 'string' && boundedResearchRead(repoRoot, relative, true).sha256 === expectedHash
      })
    } catch { observationFile = null; observation = null }
    for (const file of [checkpointFile, receiptFile, warehouseFile, observationFile].filter(Boolean)) {
      const after = fs.statSync(file.filePath)
      if (`${after.size}:${after.mtimeMs}:${after.ino}` !== file.stamp) throw new Error('RESEARCH_RECORD_CHANGED')
    }
    return projectResearchEvidence({ checkpoint, receipts, warehouse, observation, receiptSavedAt: receiptFile.modifiedAt, now })
  } catch {
    // Never expose paths, arbitrary exception messages, credentials, or old data as live progress.
    return createEnvelope({ source: 'unavailable', mode: 'LIVE_BLOCKED', freshness: 'UNKNOWN', data: {
      label: 'RESEARCH RECORDS UNAVAILABLE', live_worker_state: 'UNKNOWN', live_worker_count: null,
      verified_edge_count: null, campaign_complete_verified: false,
      reason: 'Research records are absent, changing, invalid, or outside the read boundary.',
      read_only: true, can_launch: false, can_sign: false, can_trade: false,
    } })
  }
}

export function projectResearchHistory({ receipts, postmortems, heat, fingerprint = null, family = null }) {
  if (fingerprint !== null && !/^[a-f0-9]{64}$/.test(fingerprint)) throw new Error('RESEARCH_QUERY_INVALID')
  if (family !== null && !safeIdentity(family)) throw new Error('RESEARCH_QUERY_INVALID')
  const accepted = new Map()
  for (const row of receipts.filter((r) => r.kind === 'ACCEPTED_MARKET_UNIT')) {
    const previous = accepted.get(row.receipt_id)
    if (previous && JSON.stringify(previous) !== JSON.stringify(row)) throw new Error('RESEARCH_RECEIPT_CONFLICT')
    accepted.set(row.receipt_id, row)
  }
  const rows = [...accepted.values()].flatMap((row) => {
    const post = postmortems.find((p) => p.kind === 'MARKET_POSTMORTEM' && p.spec_sha256 === row.spec_sha256 && p.result_hash === row.output_hash)
    const decision = heat?.local_price_decisions?.find((d) => d.receipt_id === row.receipt_id && d.result_sha256 === row.output_hash && d.spec_sha256 === row.spec_sha256)
    const mechanism = safeIdentity(post?.must_not_repeat?.mechanism_fingerprint)
    if ((fingerprint && fingerprint !== row.spec_sha256) || (family && family !== mechanism)) return []
    return [{ receipt_id: typeof row.receipt_id === 'string' && /^[A-Za-z0-9_.:-]{1,512}$/.test(row.receipt_id) ? row.receipt_id : null, candidate_id: safeIdentity(post?.candidate_id),
      fingerprint: /^[a-f0-9]{64}$/.test(row.spec_sha256 ?? '') ? row.spec_sha256 : null, family: mechanism,
      result_hash: /^[a-f0-9]{64}$/.test(row.output_hash ?? '') ? row.output_hash : null,
      route: decision?.decision === row.heat_projection ? decision.decision : 'ROUTING_NOT_LINKED',
      postmortem_linked: Boolean(post), rejection_scope: 'FROZEN_EXACT_TEST_SCOPE_UNCHANGED',
      failed_gates: Array.isArray(post?.failed_gates) ? post.failed_gates.map(safeIdentity).filter(Boolean).slice(0, 30) : [],
      proof_state: 'DEVELOPMENT_USED_NOT_INDEPENDENT_EDGE' }]
  })
  return createEnvelope({ source: 'runtime', mode: 'LIVE_BLOCKED', data: { rows: rows.slice(-200),
    total_matched: rows.length, record_kind: 'SAVED_ACCEPTANCE_POSTMORTEM_ROUTING_LINKS', independently_verified_edge: false, read_only: true } })
}

export function readResearchHistory(dashboardRoot, query = {}) {
  try {
    const sourceRoot = path.basename(dashboardRoot) === 'dist' ? path.dirname(dashboardRoot) : dashboardRoot
    const repoRoot = path.resolve(sourceRoot, '..', '..')
    const files = ['RESULT_RECEIPTS.jsonl', 'POSTMORTEMS.jsonl', 'HOT_COLD_UPDATE_RECEIPT.json'].map((name) => boundedResearchRead(repoRoot, `${RESEARCH_RELATIVE_ROOT}/${name}`))
    const lines = (file) => file.text.split(/\r?\n/).filter((line) => line.trim()).map((line) => JSON.parse(line))
    const result = projectResearchHistory({ receipts: lines(files[0]), postmortems: lines(files[1]), heat: JSON.parse(files[2].text), ...query })
    for (const file of files) {
      const after = fs.statSync(file.filePath)
      if (`${after.size}:${after.mtimeMs}:${after.ino}` !== file.stamp) throw new Error('RESEARCH_RECORD_CHANGED')
    }
    return result
  } catch {
    return createEnvelope({ source: 'unavailable', mode: 'LIVE_BLOCKED', data: { rows: [], record_kind: 'RESEARCH_HISTORY_UNAVAILABLE', read_only: true } })
  }
}
