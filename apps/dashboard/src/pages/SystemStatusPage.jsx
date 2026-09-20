import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
const safe = (value, fallback = 'UNKNOWN') => value === null || value === undefined || value === '' ? fallback : String(value)
const dataOf = (value) => value?.data ?? value?.payload ?? value ?? {}
export default function SystemStatusPage({ state }) {
  const visibility = dataOf(state.runtimeVisibility)
  const projection = dataOf(state.projection)
  const items = [
    ['Runtime health', visibility.status], ['Dataset state', projection.dataset_state], ['Collector state', projection.collector_state],
    ['Backtest state', projection.backtest_state], ['Strategy research', projection.strategy_research_state], ['PAPER state', projection.paper_state],
    ['LIVE state', 'BLOCKED'], ['Lock state', visibility.lock_status ?? visibility.runtime_lock?.status], ['Data freshness', state.stale ? 'STALE' : state.envelope?.freshness],
    ['Service status', state.connection], ['Test status', projection.test_status], ['Current blockers', projection.blockers],
    ['Last verified update', state.lastEventAt ?? state.envelope?.as_of],
  ]
  return <section className="milestonePage"><PageHeader eyebrow="READ-ONLY TECHNICAL VIEW" title="System Status" description="Current runtime, evidence, lock, and safety state." />
    <div className="statusMatrix">{items.map(([label, value]) => <GlassPanel key={label} family={label === 'LIVE state' ? 'critical' : 'neutral'}><small>{label}</small><strong>{safe(value)}</strong></GlassPanel>)}</div>
    <GlassPanel><div className="windowTitle"><span>▤</span><b>TECHNICAL DETAILS</b><small>READ ONLY</small></div><pre className="technicalReadout">{JSON.stringify({ connection: state.connection, stale: state.stale, errors: state.supportingErrors }, null, 2)}</pre></GlassPanel>
  </section>
}
