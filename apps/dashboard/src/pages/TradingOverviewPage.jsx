import GlassPanel from '../components/GlassPanel.jsx'
import LiveMetric from '../components/LiveMetric.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { formatCurrency, formatPercent, formatValue } from '../utils/formatFinance.js'
import { provenanceFrom } from '../utils/dataProvenance.js'

const unavailable = (value, fallback = 'NO DATA') => value === null || value === undefined || value === '' || value === 'UNKNOWN' ? fallback : value

export function LegacyTradingOverviewPage({ state, navigate, settings, updateSetting }) {
  const envelope = state.envelope
  const runtime = envelope?.source === 'runtime'
  const data = runtime ? (envelope?.data ?? {}) : {}
  const metrics = data.metrics ?? {}
  const provenance = provenanceFrom(envelope, { currency: data.reporting_currency ?? 'USD' })
  const previousMetrics = state.previousEnvelope?.data?.metrics ?? {}
  const pairs = Array.isArray(data.pairs) ? data.pairs : []
  const periods = Array.isArray(data.periods) ? data.periods : []
  const trades = pairs.reduce((total, pair) => total + (Number.isFinite(Number(pair.trades)) ? Number(pair.trades) : 0), 0)
  const hasTradeCount = pairs.some((pair) => Number.isFinite(Number(pair.trades)))
  const activePositions = Number.isFinite(Number(metrics.active_positions)) ? Number(metrics.active_positions) : null
  const cards = [
    { icon: '💵', label: 'EQUITY', value: runtime ? formatCurrency(metrics.account_equity) : 'NO DATA', raw: metrics.account_equity, previous: previousMetrics.account_equity, emphasis: 'money' },
    { icon: '📈', label: 'PF', value: runtime ? formatValue(metrics.profit_factor) : 'NO EVIDENCE', raw: metrics.profit_factor, previous: previousMetrics.profit_factor },
    { icon: '📉', label: 'DD', value: runtime ? formatPercent(metrics.current_drawdown) : 'NO DATA', raw: metrics.current_drawdown, previous: previousMetrics.current_drawdown },
    { icon: '🎯', label: 'TRADES', value: runtime && hasTradeCount ? formatValue(trades) : 'NO EVIDENCE', raw: runtime && hasTradeCount ? trades : null },
  ]
  return <><PageHeader title="Overview" actions={<div className="launcherRow"><button type="button" onClick={() => navigate('/markets')}><i aria-hidden="true">⌁</i><span>Trading Lab</span></button><button type="button" onClick={() => navigate('/trades')}><i aria-hidden="true">⇄</i><span>Work Table</span></button><button type="button" onClick={() => navigate('/strategy-maintenance')}><i aria-hidden="true">◇</i><span>Advanced</span></button></div>} />
    <div className="metricGrid heroMetrics">{cards.map((card) => <LiveMetric key={card.label} icon={card.icon} label={card.label} value={card.value} rawValue={card.raw} previousValue={card.previous} provenance={runtime ? provenance : null} stale={state.stale} emphasis={card.emphasis} />)}</div>
    <div className="overviewGrid">
      <GlassPanel family="performance" className="accountWindow" importance="important"><div className="windowTitle"><span>💵</span><b>CAPITAL</b><small>{runtime ? envelope?.mode : 'NOT CONNECTED'}</small></div><strong className="moneyHero">{runtime ? formatCurrency(metrics.account_equity) : 'NO DATA'}</strong><div className="miniMetrics"><span><small>NET P/L</small><b>{runtime ? formatCurrency(metrics.realized_pnl_today) : 'NO DATA'}</b></span><span><small>UNREALIZED</small><b>{runtime ? formatCurrency(metrics.unrealized_pnl) : 'NO DATA'}</b></span></div></GlassPanel>
      <GlassPanel family="research" className="performanceWindow"><div className="windowTitle"><span>📈</span><b>PERFORMANCE</b><small>{runtime ? 'READ MODEL' : 'NO EVIDENCE'}</small></div><div className="numberCluster"><span><small>PF</small><b>{runtime ? unavailable(metrics.profit_factor, 'NO EVIDENCE') : 'NO EVIDENCE'}</b></span><span><small>WIN</small><b>{runtime ? formatPercent(metrics.win_rate_today) : 'NO DATA'}</b></span><span><small>NET R</small><b>{runtime ? unavailable(metrics.net_r, 'NO EVIDENCE') : 'NO EVIDENCE'}</b></span></div></GlassPanel>
      <GlassPanel family="market" className="systemWindow"><div className="windowTitle"><span>🌐</span><b>SYSTEM</b><small>{state.connection}</small></div><dl className="statusList"><div><dt>DATA</dt><dd>{state.stale ? 'STALE' : (runtime ? envelope?.freshness : 'NOT CONNECTED')}</dd></div><div><dt>MARKET</dt><dd>{unavailable(data.market_status)}</dd></div><div><dt>MODE</dt><dd>{runtime ? envelope?.mode : 'PREVIEW'}</dd></div></dl></GlassPanel>
      <GlassPanel family="neutral" className="campaignWindow"><div className="windowTitle"><span>↕</span><b>CAMPAIGN</b><small>REAL EVIDENCE</small></div><div className="directionSplit"><span className="longDirection"><small>▲ LONG</small><b>{unavailable(data.long_state, 'NO EVIDENCE')}</b></span><span className="shortDirection"><small>▼ SHORT</small><b>{unavailable(data.short_state, 'NO EVIDENCE')}</b></span></div></GlassPanel>
      <GlassPanel family="market" className="chartWindow" importance="selected"><div className="chartToolbar"><div><small>MAIN MARKET</small><b>{settings.selectedMarketSymbol}</b></div><select aria-label="Overview chart timeframe" value={settings.selectedTimeframe} onChange={(event) => updateSetting('selectedTimeframe', event.target.value)}>{['1','5','15','60','240','D'].map((frame) => <option key={frame}>{frame}</option>)}</select></div><div className="marketViewport"><span className="marketCrosshair" aria-hidden="true" /><div className="windowEmpty"><b>{runtime ? 'NO VERIFIED SERIES' : 'MARKET FEED NOT CONNECTED'}</b><small>NO SYNTHETIC CHART</small><button type="button" className="windowLink" onClick={() => navigate('/markets')}>OPEN CURRENCY PAIRS</button></div></div></GlassPanel>
      <GlassPanel family="risk" className="riskWindow" importance="important"><div className="windowTitle"><span>🛡</span><b>RISK</b><small>{unavailable(data.risk_status, 'UNKNOWN')}</small></div><strong className="stateHero">{runtime ? unavailable(data.risk_status, 'UNKNOWN') : 'LIVE BLOCKED'}</strong><dl className="statusList"><div><dt>OPEN RISK</dt><dd>{runtime ? formatPercent(metrics.open_risk) : 'NO DATA'}</dd></div><div><dt>HALT</dt><dd>{unavailable(data.emergency_halt, 'UNKNOWN')}</dd></div></dl></GlassPanel>
      <GlassPanel family="market" className="pairsWindow"><div className="windowTitle"><span>🌍</span><b>CURRENCY PAIRS</b><button type="button" className="windowLink" onClick={() => navigate('/markets')}>OPEN</button></div>{pairs.length ? <div className="pairTiles">{pairs.slice(0, 8).map((pair) => <article key={pair.pair}><b>{pair.pair}</b><span>{unavailable(pair.state)}</span><strong>{pair.open_pnl === 'UNKNOWN' ? 'NO DATA' : formatCurrency(pair.open_pnl)}</strong></article>)}</div> : <div className="windowEmpty"><b>NOT CONNECTED</b><small>NO PAIR READ MODEL</small></div>}</GlassPanel>
      <GlassPanel family="critical" className="positionWindow"><div className="windowTitle"><span>◎</span><b>POSITION</b><small>READ ONLY</small></div>{runtime && activePositions === 0 ? <strong className="stateHero">NO POSITION</strong> : runtime && activePositions > 0 ? <><strong className="numberHero">{activePositions}</strong><small>DETAIL UNAVAILABLE</small></> : <strong className="stateHero">NO DATA</strong>}</GlassPanel>
      <GlassPanel family="research" className="validationWindow"><div className="windowTitle"><span>◇</span><b>VALIDATION</b><button type="button" className="windowLink" onClick={() => navigate('/strategy-maintenance')}>OPEN</button></div><strong className="stateHero">{unavailable(data.strategy_validation, 'VALIDATION PENDING')}</strong><div className="calibrationStrip"><label>R:R <input type="range" min="2" max="4.5" step=".5" defaultValue="3" aria-label="R to R display calibration" /><output>DISPLAY</output></label><label>PF <input type="range" min="1" max="2" step=".1" defaultValue="1.3" aria-label="Profit factor display calibration" /><output>DISPLAY</output></label></div></GlassPanel>
    </div>
    <div className="reviewGrid">
      <GlassPanel family="neutral"><div className="windowTitle"><span>⇄</span><b>TRADE JOURNAL</b><button type="button" className="windowLink" onClick={() => navigate('/trades')}>OPEN</button></div><strong className="stateHero">{runtime && hasTradeCount ? `${trades} RECORDS` : 'NO QUALIFYING TRADES'}</strong></GlassPanel>
      <GlassPanel family="performance"><div className="windowTitle"><span>⌁</span><b>PERFORMANCE REVIEW</b><button type="button" className="windowLink" onClick={() => navigate('/performance')}>OPEN</button></div>{periods.length ? <div className="periodStrip">{periods.slice(0, 3).map((period) => <span key={period.period}><small>{period.period}</small><b>{formatCurrency(period.value)}</b></span>)}</div> : <strong className="stateHero">NO VERIFIED SERIES</strong>}</GlassPanel>
      <GlassPanel family="research"><div className="windowTitle"><span>✓</span><b>STRATEGY VALIDATION</b><button type="button" className="windowLink" onClick={() => navigate('/strategy-maintenance')}>OPEN</button></div><strong className="stateHero">{unavailable(data.strategy_validation, 'NO EVIDENCE')}</strong></GlassPanel>
    </div>
  </>
}

function evidence(value, fallback = 'NO EVIDENCE') {
  return value === null || value === undefined || value === '' ? fallback : String(value)
}

function payload(value) {
  return value?.data ?? value?.payload ?? value ?? {}
}

export default function TradingOverviewPage({ state, navigate, settings, updateSetting }) {
  const runtime = state.envelope?.source === 'runtime'
  const data = runtime ? (state.envelope?.data ?? {}) : {}
  const metrics = data.metrics ?? {}
  const visibility = payload(state.runtimeVisibility)
  const campaign = payload(state.forexCampaign)
  const projection = payload(state.projection)
  const mode = runtime ? evidence(state.envelope?.mode, 'UNKNOWN') : 'NO EVIDENCE'
  const cards = [
    ['🚀', 'STATUS', evidence(visibility.status, evidence(state.connection, 'UNAVAILABLE')), 'Current runtime evidence'],
    ['🎯', 'PROGRESS', evidence(campaign.progress ?? campaign.qualifying_trades), 'Qualifying paper evidence'],
    ['🌐', 'MARKET', state.stale ? 'STALE' : evidence(data.market_status, 'UNAVAILABLE'), 'Read-only market freshness'],
    ['▤', 'MODE', mode === 'LIVE' ? 'LIVE — BLOCKED' : mode, mode === 'PAPER' ? 'SIMULATION ONLY' : 'Verified operating mode'],
    ['🛡', 'SAFETY', evidence(data.risk_status, 'BLOCKED'), 'No order controls'],
  ]
  const decision = projection.latest_decision ?? data.latest_decision ?? {}
  const position = projection.position ?? data.position ?? {}
  const paperPnl = campaign.net_pnl ?? campaign.pnl ?? metrics.realized_pnl_today
  const rejections = Array.isArray(projection.rejections) ? projection.rejections : []
  return <section className="milestonePage overviewPage">
    <PageHeader eyebrow="MILESTONE DASHBOARD" title="Overview" description="Verified operating evidence. PAPER means pretend-money testing." />
    <div className="statusCardGrid">{cards.map(([icon, label, value, detail]) => <LiveMetric key={label} icon={icon} label={label} value={value} detail={detail} stale={state.stale} />)}</div>
    <div className="commandGrid">
      <GlassPanel family="market" className="supertrendWindow"><div className="windowTitle"><span>📈</span><b>SUPER TREND ({settings.selectedTimeframe})</b><small>READ ONLY</small></div><div className="marketViewport milestoneChart"><div className="chartTrace" aria-hidden="true" /><div className="windowEmpty"><b>{runtime ? 'NO VERIFIED CHART SERIES' : 'DATA UNAVAILABLE'}</b><small>NO SYNTHETIC PRICES</small></div></div><div className="chartFooter"><label>PAIR<select value={settings.selectedMarketSymbol} onChange={(event) => updateSetting('selectedMarketSymbol', event.target.value)}><option>EUR_USD</option><option>GBP_USD</option><option>USD_JPY</option></select></label><label>GRANULARITY<select value={settings.selectedTimeframe} onChange={(event) => updateSetting('selectedTimeframe', event.target.value)}><option>M1</option><option>M2</option><option>M4</option><option>M5</option><option>S5</option><option>S10</option><option>S15</option><option>S30</option></select></label></div></GlassPanel>
      <GlassPanel family="research" className="decisionWindow"><div className="windowTitle"><span>🎯</span><b>LATEST DECISION</b><button className="windowLink" type="button" onClick={() => navigate('/decisions')}>OPEN</button></div><strong className="decisionGlyph">{decision.result === 'ACCEPTED' ? '✓' : '—'}</strong><h2>{evidence(decision.result, 'NO EVIDENCE')}</h2><small>{evidence(decision.timestamp ?? decision.time, 'NOT RUN')}</small></GlassPanel>
      <GlassPanel family="market" className="positionWindow"><div className="windowTitle"><span>💼</span><b>POSITION</b><button className="windowLink" type="button" onClick={() => navigate('/positions')}>OPEN</button></div><strong className="stateHero">{evidence(position.state, 'NO POSITION EVIDENCE')}</strong><dl className="threeFacts"><div><dt>PAIR</dt><dd>{evidence(position.pair, 'UNAVAILABLE')}</dd></div><div><dt>DIRECTION</dt><dd>{evidence(position.direction, 'UNAVAILABLE')}</dd></div><div><dt>R</dt><dd>{evidence(position.current_r, 'UNAVAILABLE')}</dd></div></dl></GlassPanel>
      <GlassPanel family="performance" className="paperWindow"><div className="windowTitle"><span>💰</span><b>PAPER P/L</b><small>SIMULATION ONLY</small></div><strong className="moneyHero">{runtime && paperPnl !== undefined ? formatCurrency(paperPnl) : 'NO EVIDENCE'}</strong><p>Pretend-money evidence. This is not income.</p></GlassPanel>
      <GlassPanel family="research" className="rejectionWindow"><div className="windowTitle"><span>▤</span><b>REJECTION STATS</b><small>READ ONLY</small></div>{rejections.length ? <ul className="evidenceList">{rejections.slice(0, 5).map((item) => <li key={item.reason ?? item.label}><span>{evidence(item.reason ?? item.label)}</span><b>{evidence(item.count)}</b></li>)}</ul> : <div className="windowEmpty"><b>NO EVIDENCE</b><small>REJECTION DATA UNAVAILABLE</small></div>}</GlassPanel>
      <GlassPanel className="updateWindow"><div className="windowTitle"><span>◷</span><b>LAST UPDATE</b></div><strong className="stateHero">{evidence(state.lastEventAt ?? state.envelope?.as_of, 'NOT RUN')}</strong><small>{state.stale ? 'STALE DATA' : 'FRESHNESS CHECK ACTIVE'}</small></GlassPanel>
      <GlassPanel family="critical" className="lockWindow"><div className="windowTitle"><span>🔒</span><b>RUNTIME LOCK</b></div><strong className="stateHero">{evidence(visibility.lock_status ?? visibility.runtime_lock?.status, 'UNKNOWN')}</strong><p>Broker and order controls remain blocked.</p></GlassPanel>
    </div>
  </section>
}
