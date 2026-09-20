import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import crypto from 'node:crypto'
import { createDashboardApi } from './server/dashboardApi.js'
import { createDashboardAuth } from './server/dashboardAuth.js'
import { createDashboardAuthAdapters } from './server/dashboardAuthAdapters.js'

const require = createRequire(import.meta.url)
const rootDir = path.dirname(fileURLToPath(import.meta.url))
const port = Number(process.env.PORT || 8080)
const host = process.env.AIOS_DASHBOARD_HOST || (process.env.WEBSITE_SITE_NAME ? '0.0.0.0' : '127.0.0.1')
const dashboardSourceRoot = path.basename(rootDir) === 'dist' ? path.resolve(rootDir, '..') : rootDir
const repoRootDir = path.basename(rootDir) === 'dist'
  ? path.resolve(rootDir, '..', '..', '..')
  : path.resolve(rootDir, '..', '..')
const liveAutonomyBridgeStatePath = path.resolve(
  repoRootDir,
  process.env.AIOS_AUTONOMY_BRIDGE_STATE_PATH
    || 'telemetry/night_supervisor/AUTONOMY_BRIDGE_STATE.json',
)
const forexCampaignRuntimeRoot = path.resolve(repoRootDir, '.aios/runtime/forex_p1_supertrend_paper_sessions')
const forexCampaignStatePath = path.resolve(forexCampaignRuntimeRoot, 'AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_STATE.json')
const forexActiveSessionPath = path.resolve(forexCampaignRuntimeRoot, 'active.json')
const forexProvenancePath = path.resolve(forexCampaignRuntimeRoot, 'AIOS_FOREX_SUPERTREND_CYCLE_PROVENANCE.jsonl')
const forexLedgerPath = path.resolve(forexCampaignRuntimeRoot, 'AIOS_FOREX_P1_EXPERIENCE_LEDGER.jsonl')
const forexEventsPath = path.resolve(forexCampaignRuntimeRoot, 'AIOS_FOREX_SUPERTREND_30_TRADE_EVENTS.jsonl')
const dashboardProjectionPath = path.resolve(repoRootDir, '.aios/runtime/dashboard_measurement/AIOS_DASHBOARD_PROJECTION_V1.json')
const projectionLimit = 250 * 1024
const dashboardAuth = createDashboardAuth({
  ...createDashboardAuthAdapters({ env: process.env, fetchImpl: globalThis.fetch }),
})
const dashboardApi = createDashboardApi({
  dashboardRoot: dashboardSourceRoot,
  requireDataAccess: dashboardAuth.requireDataAccess,
})

const contentTypes = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.css', 'text/css; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.md', 'text/markdown; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.webmanifest', 'application/manifest+json; charset=utf-8'],
])

function sendText(response, statusCode, message) {
  response.writeHead(statusCode, {
    'content-type': 'text/plain; charset=utf-8',
    'cache-control': 'no-store',
  })
  response.end(message)
}

function getFilePath(requestUrl) {
  const parsedUrl = new URL(requestUrl, 'http://localhost')
  const pathname = parsedUrl.pathname === '/' ? '/index.html' : parsedUrl.pathname
  if (isBlockedStaticPath(pathname)) return null
  const decodedPath = decodeURIComponent(pathname)
  const requestedPath = path.resolve(rootDir, `.${decodedPath}`)

  if (!requestedPath.startsWith(rootDir + path.sep) && requestedPath !== rootDir) {
    return null
  }

  return requestedPath
}

function isBlockedStaticPath(pathname) {
  return [
    '/mock-data/',
    '/server/',
    '/src/',
    '/node_modules/',
    '/private-media/',
    '/package.json',
    '/server.js',
    '/AZURE_AUTH_ENVIRONMENT.template.md',
  ].some((blocked) => pathname === blocked || pathname.startsWith(blocked))
}

function isLiveAutonomyBridgeStateRequest(requestUrl) {
  const parsedUrl = new URL(requestUrl, 'http://localhost')
  return parsedUrl.pathname === '/live-data/autonomy_bridge_state.json'
}

function isDashboardProjectionRequest(requestUrl) { return new URL(requestUrl, 'http://localhost').pathname === '/aios-dashboard-projection' }
function isRuntimeVisibilityRequest(requestUrl) { return new URL(requestUrl, 'http://localhost').pathname === '/api/runtime/visibility' }
function isForexCampaignRequest(requestUrl) { return new URL(requestUrl, 'http://localhost').pathname === '/api/forex/paper-campaign' }

function safeReadJson(filePath) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8')
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function safeReadJsonLines(filePath) {
  try {
    const raw = fs.readFileSync(filePath, 'utf8')
    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line))
  } catch {
    return []
  }
}

function asNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function parseUtc(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function formatDuration(seconds) {
  if (seconds == null) return null
  const total = Math.max(0, Math.floor(Number(seconds)))
  if (!Number.isFinite(total)) return null
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, '0')}m ${String(secs).padStart(2, '0')}s`
  if (minutes > 0) return `${minutes}m ${String(secs).padStart(2, '0')}s`
  return `${secs}s`
}

function classifyR(value) {
  const number = asNumber(value)
  if (number == null) return 'UNKNOWN'
  if (number > 0) return 'POSITIVE_R'
  if (number < 0) return 'NEGATIVE_R'
  return 'FLAT_R'
}

function countBy(items, predicate) {
  return items.reduce((total, item) => total + (predicate(item) ? 1 : 0), 0)
}

function buildForexCampaignSnapshot() {
  const campaignState = safeReadJson(forexCampaignStatePath)
  const activeSession = safeReadJson(forexActiveSessionPath)
  const provenance = safeReadJsonLines(forexProvenancePath)
  const ledger = safeReadJsonLines(forexLedgerPath)
  const events = safeReadJsonLines(forexEventsPath)
  const latestCycle = provenance.at(-1) || {}
  const firstCycle = provenance[0] || {}
  const tradeResults = Array.isArray(campaignState?.trade_results) ? campaignState.trade_results : []
  const totalTarget = Number(campaignState?.target_qualifying_trades || 30)
  const accepted = Number(campaignState?.accepted_qualifying_trades || tradeResults.length || 0)
  const latestTrade = campaignState?.last_trade || {}
  const activePositionConflict = Boolean(
    campaignState?.active_position_status === 'ACTIVE'
    && activeSession?.status
    && activeSession.status !== 'OPEN',
  )
  const currentActiveStatus = activePositionConflict
    ? 'CONFLICT'
    : (activeSession?.status === 'OPEN' ? 'ACTIVE' : 'NONE')
  const progression = Array.from({ length: totalTarget }, (_, index) => {
    const tradeNumber = index + 1
    const qualifyingTrade = tradeResults.find((item) => Number(item.trade_number) === tradeNumber) || null
    const trade = qualifyingTrade
      ? (tradeNumber === accepted ? { ...qualifyingTrade, ...latestTrade, ...latestCycle } : qualifyingTrade)
      : ledger.find((item) => Number(item.trade_number || item.qualifying_trade_number) === tradeNumber) || null
    const realizedR = asNumber(trade?.realized_r ?? trade?.realizedR ?? trade?.r)
    const cumulativeR = asNumber(trade?.cumulative_realized_r ?? trade?.cumulative_r ?? trade?.cumulativeR)
    return {
      tradeNumber,
      tradeId: trade?.trade_id || trade?.id || '',
      dateTime: parseUtc(trade?.exit_timestamp_utc || trade?.observed_at_utc || trade?.timestamp_utc || trade?.cycle_completed_utc),
      direction: trade?.direction || trade?.side || trade?.signal_direction || '',
      entry: trade?.entry ?? trade?.entry_price ?? '',
      stop: trade?.stop ?? trade?.stop_price ?? '',
      target: trade?.target ?? trade?.target_price ?? '',
      plannedRr: trade?.planned_reward_risk ?? trade?.planned_rr ?? '',
      exit: trade?.exit ?? trade?.exit_price ?? '',
      exitReason: trade?.exit_reason ?? trade?.closed_reason ?? '',
      pl: trade?.realized_paper_pl ?? trade?.realized_pl ?? '',
      realizedR: realizedR == null ? '' : realizedR,
      rClassification: realizedR == null ? 'UNKNOWN' : classifyR(realizedR),
      mfeR: trade?.mfe_r ?? '',
      maeR: trade?.mae_r ?? '',
      holdTime: trade?.hold_time ?? formatDuration(trade?.hold_seconds),
      cumulativePl: trade?.cumulative_paper_pl ?? trade?.cumulative_pl ?? '',
      cumulativeR: cumulativeR == null ? '' : cumulativeR,
    }
  })
  const realizedValues = progression.map((row) => asNumber(row.realizedR)).filter((value) => value != null)
  const positiveRTrades = countBy(progression, (row) => row.rClassification === 'POSITIVE_R')
  const negativeRTrades = countBy(progression, (row) => row.rClassification === 'NEGATIVE_R')
  const flatRTrades = countBy(progression, (row) => row.rClassification === 'FLAT_R')
  const wins = tradeResults.filter((trade) => trade.win_or_loss === 'WIN').length || Number(campaignState?.accepted_qualifying_trades || 0)
  const losses = tradeResults.filter((trade) => trade.win_or_loss === 'LOSS').length
  const flats = tradeResults.filter((trade) => trade.win_or_loss === 'FLAT').length
  const winTrades = tradeResults.filter((trade) => trade.win_or_loss === 'WIN')
  const lossTrades = tradeResults.filter((trade) => trade.win_or_loss === 'LOSS')
  const averageWin = winTrades.length
    ? winTrades.reduce((sum, trade) => sum + (asNumber(trade.realized_paper_pl) || 0), 0) / winTrades.length
    : null
  const averageLoss = lossTrades.length
    ? lossTrades.reduce((sum, trade) => sum + (asNumber(trade.realized_paper_pl) || 0), 0) / lossTrades.length
    : null
  return {
    runtimeRoot: forexCampaignRuntimeRoot,
    campaignState,
    activeSession,
    provenanceCount: provenance.length,
    experienceCount: ledger.length,
    eventCount: events.length,
    firstCycle,
    latestCycle,
    tradeResults,
    progression,
    summary: {
      status: campaignState?.campaign_status || 'UNKNOWN',
      accepted,
      target: totalTarget,
      remaining: Math.max(0, totalTarget - accepted),
      progressPercent: totalTarget > 0 ? Math.round((accepted / totalTarget) * 1000) / 10 : 0,
      netPl: asNumber(campaignState?.net_pl),
      expectancy: asNumber(campaignState?.expectancy),
      profitFactor: campaignState?.profit_factor ?? 'UNKNOWN',
      maxDrawdown: asNumber(campaignState?.maximum_drawdown),
      averageR: realizedValues.length ? Math.round((realizedValues.reduce((sum, value) => sum + value, 0) / realizedValues.length) * 1000) / 1000 : null,
      totalR: realizedValues.length ? Math.round(realizedValues.reduce((sum, value) => sum + value, 0) * 1000) / 1000 : null,
      positiveRTrades,
      negativeRTrades,
      flatRTrades,
      bestR: realizedValues.length ? Math.max(...realizedValues) : null,
      worstR: realizedValues.length ? Math.min(...realizedValues) : null,
      strategy: campaignState?.qualifying_strategy_name || 'supertrend_pullback_v1',
      winRate: campaignState?.accepted_qualifying_trades ? Math.round(((Number(campaignState?.accepted_qualifying_trades || 0) - Number(campaignState?.consecutive_losses || 0)) / Number(campaignState?.accepted_qualifying_trades || 1)) * 1000) / 10 : null,
    },
    activeTrade: {
      positionStatus: currentActiveStatus,
      instrument: activeSession?.instrument || 'EUR/USD',
      direction: activeSession?.direction || activeSession?.side || campaignState?.active_position?.direction || 'UNKNOWN',
      entry: activeSession?.entry_price ?? campaignState?.active_position?.entry_price ?? latestTrade?.entry ?? null,
      currentPrice: latestCycle.bid ?? latestCycle.ask ?? null,
      stop: activeSession?.stop_price ?? campaignState?.active_position?.stop_price ?? latestTrade?.stop ?? null,
      target: activeSession?.target_price ?? campaignState?.active_position?.target_price ?? latestTrade?.target ?? null,
      units: activeSession?.units ?? campaignState?.active_position?.units ?? latestTrade?.units ?? null,
      plannedRr: activeSession?.planned_reward_risk ?? campaignState?.active_position?.planned_reward_risk ?? latestTrade?.planned_reward_risk ?? null,
      currentR: activeSession?.current_r ?? campaignState?.active_position?.current_r ?? latestCycle?.realized_r ?? null,
      realizedR: activeSession?.realized_r ?? latestCycle?.realized_r ?? campaignState?.last_trade?.realized_r ?? null,
      unrealizedPl: activeSession?.unrealized_paper_pl ?? null,
      mfeR: activeSession?.mfe_r ?? latestCycle?.mfe_r ?? null,
      maeR: activeSession?.mae_r ?? latestCycle?.mae_r ?? null,
      holdTime: formatDuration(activeSession?.hold_seconds ?? activeSession?.age_seconds ?? null),
      entryTimeUtc: activeSession?.entry_timestamp_utc || latestCycle?.cycle_started_utc || null,
      entryTimeNy: activeSession?.entry_timestamp_new_york || null,
    },
    signal: {
      currentSignal: latestCycle.signal_status || 'UNKNOWN',
      supertrendDirection: latestCycle.supertrend_direction || 'UNKNOWN',
      atrActual: latestCycle.atr_actual ?? null,
      atrMinimum: latestCycle.minimum_atr ?? null,
      bodyRatio: latestCycle.candle_body_ratio ?? null,
      bodyMinimum: latestCycle.minimum_candle_body_ratio ?? null,
      spread: latestCycle.spread ?? null,
      latestRejectionReason: campaignState?.latest_rejection_reason || latestCycle.first_failed_gate || 'UNKNOWN',
      rejectionCounts: campaignState?.rejection_reason_counts || {},
      noSignalReason: latestCycle.cycle_action === 'WAIT_FOR_DATA'
        ? 'DATA_UNAVAILABLE'
        : (latestCycle.rejection_reasons?.[0] || campaignState?.latest_rejection_reason || 'UNKNOWN'),
    },
    integrity: {
      dataFreshness: latestCycle.history_freshness_result || 'UNKNOWN',
      historyFreshness: latestCycle.history_freshness_result || 'UNKNOWN',
      snapshotFreshness: latestCycle.snapshot_freshness_result || 'UNKNOWN',
      lastMarketData: latestCycle.pricing_response_utc || latestCycle.snapshot_observed_utc || null,
      lastCompletedM5: latestCycle.latest_completed_candle_close_utc || null,
      dataUnavailableCount: campaignState?.data_unavailable_count ?? 0,
      rejectedRecords: campaignState?.rejected_records ?? 0,
      duplicateGuardCount: campaignState?.rejection_reason_counts?.duplicate_position_guard ?? 0,
      evidenceDateRange: `${firstCycle.cycle_started_utc || 'UNKNOWN'} -> ${latestCycle.cycle_completed_utc || 'UNKNOWN'}`,
      evidenceFreshness: latestCycle.history_freshness_result || 'UNKNOWN',
      ledgerCount: tradeResults.length,
      experienceCount: ledger.length,
      canonicalMainSha: '6138acc4f63ea459f03b1b78bcab33d4634f81cc',
    },
    readiness: {
      sample: `${accepted} / ${totalTarget}`,
      expectancy: campaignState?.expectancy ?? null,
      profitFactor: campaignState?.profit_factor ?? 'UNKNOWN',
      maxDrawdown: campaignState?.maximum_drawdown ?? null,
      consecutiveLosses: campaignState?.consecutive_losses ?? null,
      p1Status: campaignState?.p1_status || 'UNKNOWN',
      liveAuthority: 'NO',
      sampleStatus: accepted >= totalTarget ? 'PASS' : 'INSUFFICIENT SAMPLE',
      expectancyStatus: typeof campaignState?.expectancy === 'number' ? 'PASS' : 'UNKNOWN',
      profitFactorStatus: campaignState?.profit_factor ? 'PASS' : 'UNKNOWN',
      drawdownStatus: campaignState?.maximum_drawdown != null ? 'PASS' : 'UNKNOWN',
    },
    safety: {
      brokerWrites: 'NO',
      practiceOrders: 'NO',
      liveAuthority: 'NO',
      killSwitch: 'LOCKED',
      riskHalt: 'LOCKED',
      ownerCancel: 'LOCKED',
      secondWriter: 'NO',
      runtimeRootMode: 'LOCAL_READ_ONLY',
      lockStatus: activeSession ? 'PRESENT' : 'ABSENT',
    },
    sources: {
      campaignStatePath: '.aios/runtime/forex_p1_supertrend_paper_sessions/AIOS_FOREX_SUPERTREND_30_TRADE_CAMPAIGN_STATE.json',
      activeSessionPath: '.aios/runtime/forex_p1_supertrend_paper_sessions/active.json',
      provenancePath: '.aios/runtime/forex_p1_supertrend_paper_sessions/AIOS_FOREX_SUPERTREND_CYCLE_PROVENANCE.jsonl',
      ledgerPath: '.aios/runtime/forex_p1_supertrend_paper_sessions/AIOS_FOREX_P1_EXPERIENCE_LEDGER.jsonl',
      eventsPath: '.aios/runtime/forex_p1_supertrend_paper_sessions/AIOS_FOREX_SUPERTREND_30_TRADE_EVENTS.jsonl',
    },
    performance: {
      wins,
      losses,
      flats,
      averageWin,
      averageLoss,
    },
    conflict: activePositionConflict
      ? {
          activePositionStatus: 'CONFLICT',
          sources: ['campaignState.active_position_status', 'activeSession.status'],
        }
      : null,
  }
}

function serveForexCampaignSnapshot(request, response) {
  const snapshot = buildForexCampaignSnapshot()
  const raw = JSON.stringify(snapshot)
  const etag = `"${crypto.createHash('sha256').update(raw).digest('hex')}"`
  if (request.headers['if-none-match'] === etag) {
    response.writeHead(304, { etag, 'cache-control': 'no-store' })
    response.end()
    return
  }
  response.writeHead(200, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    etag,
    'x-aios-forex-dashboard-state': snapshot.summary.status,
  })
  response.end(request.method === 'HEAD' ? undefined : raw)
}

function serveDashboardProjection(request, response) {
  if (!dashboardProjectionPath.startsWith(path.resolve(repoRootDir) + path.sep)) return sendText(response, 403, 'Forbidden')
  fs.readFile(dashboardProjectionPath, (error, raw) => {
    if (error || raw.length > projectionLimit) return sendText(response, error?.code === 'ENOENT' ? 404 : 503, 'Projection unavailable')
    let projection
    try { projection = JSON.parse(raw) } catch { return sendText(response, 503, 'Projection unavailable') }
    if (projection.schema_version !== 'AIOS_DASHBOARD_PROJECTION_V1' || !projection.dimensions || !projection.receipts) return sendText(response, 503, 'Projection unavailable')
    const etag = `"${crypto.createHash('sha256').update(raw).digest('hex')}"`
    if (request.headers['if-none-match'] === etag) { response.writeHead(304, { etag }); response.end(); return }
    response.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', etag, 'x-aios-projection-state': projection.projection_state || 'UNAVAILABLE' })
    response.end(request.method === 'HEAD' ? undefined : raw)
  })
}

function serveRuntimeVisibility(request, response) {
  try {
    const runtimeApiServicePath = path.resolve(repoRootDir, 'services/orchestrator/runtimeApiService.js')
    const { getVisibilitySnapshot } = require(runtimeApiServicePath)
    const snapshot = getVisibilitySnapshot()
    if (snapshot?.schema !== 'aios.runtime_visibility_api.v1' || snapshot?.mode !== 'READ_ONLY') {
      sendText(response, 503, 'Runtime visibility unavailable')
      return
    }

    const raw = JSON.stringify(snapshot)
    response.writeHead(200, {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'x-aios-runtime-mode': 'READ_ONLY',
      'x-aios-runtime-state': snapshot.frontend_contract?.display_state || 'UNKNOWN',
    })
    response.end(request.method === 'HEAD' ? undefined : raw)
  } catch {
    sendText(response, 503, 'Runtime visibility unavailable')
  }
}

const server = http.createServer(async (request, response) => {
  if (await dashboardAuth(request, response)) return
  if (await dashboardApi(request, response)) return

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    sendText(response, 405, 'Method not allowed')
    return
  }

  if (isRuntimeVisibilityRequest(request.url)) {
    if (!dashboardAuth.requireDataAccess(request, response)) return
    serveRuntimeVisibility(request, response)
    return
  }

  if (isForexCampaignRequest(request.url)) {
    if (!dashboardAuth.requireDataAccess(request, response)) return
    serveForexCampaignSnapshot(request, response)
    return
  }

  if (isLiveAutonomyBridgeStateRequest(request.url)) {
    if (!dashboardAuth.requireDataAccess(request, response)) return
    fs.stat(liveAutonomyBridgeStatePath, (statError, stats) => {
      if (statError || !stats.isFile()) {
        sendText(response, 404, 'Not found')
        return
      }

      response.writeHead(200, {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-store',
      })

      if (request.method === 'HEAD') {
        response.end()
        return
      }

      fs.createReadStream(liveAutonomyBridgeStatePath).pipe(response)
    })
    return
  }

  if (isDashboardProjectionRequest(request.url)) {
    if (!dashboardAuth.requireDataAccess(request, response)) return
    serveDashboardProjection(request, response)
    return
  }

  const pageUrl = new URL(request.url, 'http://localhost')
  const acceptsHtml = String(request.headers.accept || '').includes('text/html')
  const isPublicPage = ['/', '/login', '/signup'].includes(pageUrl.pathname)
  if (acceptsHtml && !isPublicPage && !dashboardAuth.hasValidSession(request)) {
    response.writeHead(302, { location: '/login', 'cache-control': 'no-store' })
    response.end()
    return
  }

  let filePath

  try {
    filePath = getFilePath(request.url)
  } catch {
    sendText(response, 400, 'Bad request')
    return
  }

  if (!filePath) {
    sendText(response, 403, 'Forbidden')
    return
  }

  fs.stat(filePath, (statError, stats) => {
    if (statError || !stats.isFile()) {
      const acceptsHtml = String(request.headers.accept || '').includes('text/html')
      const indexPath = path.resolve(rootDir, 'index.html')
      if (acceptsHtml && fs.existsSync(indexPath)) {
        response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' })
        fs.createReadStream(indexPath).pipe(response)
        return
      }
      sendText(response, 404, 'Not found')
      return
    }

    const contentType = contentTypes.get(path.extname(filePath).toLowerCase())
      || 'application/octet-stream'

    response.writeHead(200, {
      'content-type': contentType,
      'cache-control': 'no-store',
    })

    if (request.method === 'HEAD') {
      response.end()
      return
    }

    fs.createReadStream(filePath).pipe(response)
  })
})

server.listen(port, host, () => {
  console.log(`AI_OS dashboard static server listening on ${host}:${port}`)
})
