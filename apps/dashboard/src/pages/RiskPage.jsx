import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
const safe = (value, fallback = 'UNKNOWN') => value === null || value === undefined || value === '' ? fallback : String(value)
export default function RiskPage({ state }) {
  const runtime = state.envelope?.source === 'runtime'
  const data = runtime ? (state.envelope?.data ?? {}) : {}
  const metrics = data.metrics ?? {}
  const risks = [
    ['Current drawdown', metrics.current_drawdown], ['Maximum allowed drawdown', data.maximum_drawdown], ['Daily loss state', data.daily_loss_state],
    ['Consecutive losses', data.consecutive_losses], ['Position-risk limit', data.position_risk_limit], ['R:R requirement', data.risk_reward_requirement],
    ['Spread filter', data.spread_filter], ['Slippage assumption', data.slippage_assumption], ['Kill switch', data.emergency_halt],
    ['Broker lock', data.broker_lock], ['Capital ceiling', data.capital_ceiling], ['Existing capital limit', '$50 CEILING'],
  ]
  return <section className="milestonePage"><PageHeader eyebrow="CAPITAL PROTECTION" title="Risk" description="Real-money actions remain blocked. The $50 value is a ceiling, not an account balance." />
    <div className="riskMetricGrid">{risks.map(([label, value]) => <GlassPanel key={label} family={label.includes('lock') || label.includes('Kill') ? 'critical' : 'risk'}><small>{label}</small><strong>{safe(value)}</strong></GlassPanel>)}</div>
    <div className="twoPane"><GlassPanel><div className="windowTitle"><span>⚙</span><b>RESEARCH DISPLAY CONTROLS</b><small>DISABLED FOR TRADING</small></div><label className="displayControl">Risk view<input disabled type="range" min="0" max="100" defaultValue="0" /><output>DISPLAY ONLY</output></label><label className="displayControl">Cost stress view<input disabled type="number" value="0" readOnly /><output>DISPLAY ONLY</output></label></GlassPanel><GlassPanel family="critical"><div className="windowTitle"><span>🛡</span><b>RISK-EVENT HISTORY</b></div><div className="windowEmpty"><b>NO EVIDENCE</b><small>NO VERIFIED RISK EVENT FEED</small></div></GlassPanel></div>
  </section>
}
