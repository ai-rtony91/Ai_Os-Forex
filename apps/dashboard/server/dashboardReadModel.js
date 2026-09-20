import fs from 'node:fs'
import path from 'node:path'
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
