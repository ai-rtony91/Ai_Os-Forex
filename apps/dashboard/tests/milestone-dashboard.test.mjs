import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const read = (relative) => readFile(path.join(root, relative), 'utf8')
const requiredRoutes = ['/overview', '/decisions', '/positions', '/risk', '/reports', '/post-mortem', '/settings', '/system-status']
const requiredPages = ['TradingOverviewPage', 'DecisionsPage', 'PositionsPage', 'RiskPage', 'ReportsPage', 'PostMortemPage', 'SettingsPage', 'SystemStatusPage']

test('canonical router exposes one route for every major page', async () => {
  const [router, shell, nav] = await Promise.all([read('src/app/AiosRouter.jsx'), read('src/app/AiosAppShell.jsx'), read('src/components/NavigationRail.jsx')])
  for (const route of requiredRoutes) {
    assert.match(router, new RegExp(route.replace('/', '\\/')))
    assert.match(shell, new RegExp(route.replace('/', '\\/')))
    assert.match(nav, new RegExp(route.replace('/', '\\/')))
  }
  for (const page of requiredPages) assert.match(shell, new RegExp(page))
  assert.doesNotMatch(router, /\/markets|\/trades|\/performance/)
})

test('Dashboard #5 structure keeps the navigation, status cards, command windows, action rail, and safety strip', async () => {
  const [overview, shell, rail, css] = await Promise.all([read('src/pages/TradingOverviewPage.jsx'), read('src/app/AiosAppShell.jsx'), read('src/components/BottomActionRail.jsx'), read('src/app/AiosAppShell.css')])
  for (const marker of ['STATUS', 'PROGRESS', 'MARKET', 'MODE', 'SAFETY', 'SUPER TREND', 'LATEST DECISION', 'POSITION', 'PAPER P/L', 'REJECTION STATS', 'LAST UPDATE', 'RUNTIME LOCK']) assert.match(overview, new RegExp(marker.replace('/', '\\/')))
  for (const action of ['Start', 'Stop', 'Restart', 'Logs', 'Reports', 'Post-Mortem', 'Settings', 'Help']) assert.match(rail, new RegExp(action))
  assert.match(shell, /BottomActionRail/)
  assert.match(css, /commandGrid/)
  assert.match(css, /bottomActionRail/)
  assert.match(css, /safetyStrip/)
})

test('unsafe runtime actions are disabled and no order-entry control is present', async () => {
  const [rail, positions, risk] = await Promise.all([read('src/components/BottomActionRail.jsx'), read('src/pages/PositionsPage.jsx'), read('src/pages/RiskPage.jsx')])
  assert.match(rail, /disabled=\{!target\}/)
  assert.match(rail, /EXECUTION OFF/)
  assert.match(rail, /BROKER LOCKED/)
  assert.match(rail, /NO ORDER CONTROL/)
  assert.doesNotMatch(positions, /Place order|Submit order|Buy now|Sell now/i)
  assert.match(risk, /disabled type="range"/)
})

test('supporting interfaces are GET-only and preserve the existing dashboard stream', async () => {
  const [api, hook] = await Promise.all([read('src/services/dashboardApi.js'), read('src/hooks/useLiveDashboard.js')])
  for (const endpoint of ['/api/runtime/visibility', '/api/forex/paper-campaign', '/aios-dashboard-projection']) assert.match(api, new RegExp(endpoint.replaceAll('/', '\\/')))
  assert.match(api, /method: 'GET'/)
  assert.match(hook, /connectDashboardEvents/)
  assert.match(hook, /Promise\.allSettled/)
  assert.match(hook, /SUPPORTING_SNAPSHOT/)
})

test('unavailable and paper evidence remain honestly labelled', async () => {
  const files = await Promise.all(['src/pages/TradingOverviewPage.jsx', 'src/pages/DecisionsPage.jsx', 'src/pages/PositionsPage.jsx', 'src/pages/ReportsPage.jsx', 'src/pages/SystemStatusPage.jsx'].map(read))
  const joined = files.join('\n')
  assert.match(joined, /NO EVIDENCE/)
  assert.match(joined, /UNAVAILABLE/)
  assert.match(joined, /SIMULATION ONLY/)
  assert.match(joined, /BLOCKED/)
  for (const invented of ['+18.42', '1.08125', '1.07840', '1.08680', '45231']) assert.equal(joined.includes(invented), false)
})

test('responsive and accessible styles guard mobile overflow and keyboard focus', async () => {
  const css = await read('src/app/AiosAppShell.css')
  assert.match(css, /@media\(max-width:760px\)/)
  assert.match(css, /@media\(max-width:430px\)/)
  assert.match(css, /overflow-x:auto/)
  assert.match(css, /focus-visible/)
  assert.match(css, /prefers-reduced-motion/)
  assert.match(css, /navigationRail\{inset:auto;top:0;flex-direction:row/)
  assert.match(css, /grid-template-areas:"chart chart decision position position position" "paper paper reject reject update lock"/)
  assert.match(css, /grid-template-columns:repeat\(4,minmax\(0,1fr\)\);grid-template-rows:repeat\(2,54px\)/)
  assert.match(css, /statusCardGrid,.riskMetricGrid,.statusMatrix,.reportGrid,.filterGrid,.compactFilters\{grid-template-columns:1fr\}/)
  assert.match(css, /pageTabs\{flex-wrap:wrap;overflow:visible\}/)
})

test('all page contracts are present', async () => {
  const contracts = {
    'src/pages/DecisionsPage.jsx': ['Accepted', 'Rejected', 'Waiting', 'Decision history', 'Rejection reason'],
    'src/pages/PositionsPage.jsx': ['Active', 'Closed', 'Take profit', 'Position history'],
    'src/pages/RiskPage.jsx': ['Maximum allowed drawdown', 'Daily loss state', '$50 CEILING', 'Kill switch'],
    'src/pages/ReportsPage.jsx': ['Validation receipts', 'Freeze receipts', 'PAPER evidence', 'READ-ONLY REPORT PREVIEW'],
    'src/pages/PostMortemPage.jsx': ['Wins', 'Losses', 'Rule compliance', 'Lessons'],
    'src/pages/SettingsPage.jsx': ['Refresh interval', 'Time zone', 'Text size', 'NO CREDENTIALS'],
    'src/pages/SystemStatusPage.jsx': ['Dataset state', 'Collector state', 'Backtest state', 'LIVE state'],
  }
  for (const [file, labels] of Object.entries(contracts)) {
    const source = await read(file)
    for (const label of labels) assert.match(source, new RegExp(label.replace('$', '\\$'), 'i'))
  }
})
