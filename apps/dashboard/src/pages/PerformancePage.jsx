import { useState } from 'react'
import GlassPanel from '../components/GlassPanel.jsx'
import LiveMetric from '../components/LiveMetric.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { formatCurrency, formatPercent } from '../utils/formatFinance.js'
const PERIODS = ['TODAY', 'WEEK', 'MONTH', 'YEAR TO DATE', 'ALL TIME']; const MODES = ['BACKTEST', 'REPLAY', 'PAPER', 'PRACTICE', 'LIVE_BLOCKED']
export default function PerformancePage({ state }) {
  const [period, setPeriod] = useState('MONTH'); const [mode, setMode] = useState('PAPER')
  const runtime = state.envelope?.source === 'runtime'
  const data = runtime ? (state.envelope?.data ?? {}) : {}
  const sourceMetrics = data.metrics ?? {}
  const pairs = Array.isArray(data.pairs) ? data.pairs : []
  const tradeCount = pairs.some((pair) => Number.isFinite(Number(pair.trades))) ? pairs.reduce((sum, pair) => sum + Number(pair.trades ?? 0), 0) : null
  const metrics = [['NET P/L', sourceMetrics.realized_pnl_today],['EXPECTANCY',sourceMetrics.expectancy],['PF',sourceMetrics.profit_factor],['WIN',sourceMetrics.win_rate_today],['DD',sourceMetrics.current_drawdown],['NET R',sourceMetrics.net_r],['TRADES',tradeCount]]
  const displayMetric = (label, value) => {
    if (!runtime || value === null || value === undefined || value === 'UNKNOWN') return 'NO EVIDENCE'
    if (label === 'NET P/L') return formatCurrency(value)
    if (label === 'WIN' || label === 'DD') return formatPercent(value)
    if (label === 'NET R' && Number.isFinite(Number(value))) return `${Number(value) >= 0 ? '+' : ''}${value}R`
    return String(value)
  }
  const series = Array.isArray(data.performance_series) ? data.performance_series.filter((value) => Number.isFinite(Number(value))).map(Number) : []
  const points = series.length > 1 ? series.map((value, index) => { const min = Math.min(...series); const max = Math.max(...series); const spread = max - min || 1; return `${(index / (series.length - 1)) * 100},${34 - ((value - min) / spread) * 30}` }).join(' ') : ''
  return <><PageHeader title="Performance Review" actions={<span className="readModelBadge">{runtime ? `${mode} · ${period}` : 'NO VERIFIED SERIES'}</span>} />
    <div className="filterRow"><div>{PERIODS.map((item) => <button type="button" key={item} aria-pressed={period === item} onClick={() => setPeriod(item)}>{item}</button>)}</div><select value={mode} onChange={(e) => setMode(e.target.value)}>{MODES.map((item) => <option key={item}>{item}</option>)}</select></div>
    <div className="metricGrid compact reviewMetrics">{metrics.map(([label, value]) => <LiveMetric key={label} label={label} value={displayMetric(label, value)} rawValue={value} emphasis={label.includes('P/L') ? 'money' : 'number'} />)}</div>
    <div className="twoColumn"><GlassPanel family="performance" importance="selected"><div className="windowTitle"><span>⌁</span><b>VERIFIED SERIES</b><small>{series.length ? `${series.length} POINTS` : 'NO EVIDENCE'}</small></div>{series.length > 1 ? <svg className="trendChart" viewBox="0 0 100 38" preserveAspectRatio="none" aria-label="Verified performance series"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke" /></svg> : <div className="windowEmpty"><b>NO VERIFIED SERIES</b><small>CHART WITHHELD</small></div>}</GlassPanel><GlassPanel family="risk"><div className="windowTitle"><span>📉</span><b>DRAWDOWN</b><small>RUNTIME ONLY</small></div><strong className="numberHero">{displayMetric('DD', sourceMetrics.current_drawdown)}</strong></GlassPanel></div>
    <GlassPanel family="market" className="tablePanel"><div className="windowTitle"><span>🌍</span><b>PAIR CONTRIBUTION</b><small>{pairs.length ? 'RUNTIME' : 'NO EVIDENCE'}</small></div>{pairs.length ? <div className="tableScroll"><table><thead><tr><th>PAIR</th><th>NET R</th><th>PF</th><th>WIN</th><th>TRADES</th></tr></thead><tbody>{pairs.map((pair) => <tr key={pair.pair}><td><b>{pair.pair}</b></td><td>{pair.net_r ?? 'NO DATA'}</td><td>{pair.profit_factor ?? 'NO DATA'}</td><td>{pair.win_rate ?? 'NO DATA'}</td><td>{pair.trades ?? 'NO DATA'}</td></tr>)}</tbody></table></div> : <div className="windowEmpty"><b>NO EVIDENCE</b><small>NO PAIR SERIES</small></div>}</GlassPanel>
  </>
}
