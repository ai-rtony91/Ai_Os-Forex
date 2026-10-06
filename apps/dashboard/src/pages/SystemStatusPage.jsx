import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
const safe = (value, fallback = 'UNKNOWN') => value === null || value === undefined || value === '' ? fallback : String(value)
const dataOf = (value) => value?.data ?? value?.payload ?? value ?? {}
export default function SystemStatusPage({ state }) {
  const visibility = dataOf(state.runtimeVisibility)
  const projection = dataOf(state.projection)
  const research = state.researchStatus?.data ?? {}
  const researchItems = [
    ['Live worker link', research.live_worker_state ?? 'NOT CONNECTED'],
    ['Owner-reported active market workers', research.live_worker_count],
    ['Builder worker state', research.builder_worker_state],
    ['Builder worker count', research.builder_worker_count],
    ['Current phase', research.current_phase],
    ['Current job', research.current_job],
    ['Queue size observed by owner', research.queue_size],
    ['UI research fetch time (UTC)', state.researchFetchedAt],
    ['Worker heartbeat (UTC)', research.worker_heartbeat_at],
    ['Last useful progress (UTC)', research.useful_progress_at],
    ['Observation metadata saved (UTC)', research.observation_saved_at],
    ['Last accepted result observed (UTC)', research.last_accepted_at],
    ['Last saved worker state', research.saved_worker_state],
    ['Last saved research update (UTC)', research.last_saved_at],
    ['Receipt file updated (UTC)', research.last_receipt_file_update],
    ['Saved data freshness', state.researchStatus?.freshness],
    ['Accepted market jobs', research.accepted_market_units],
    ['Settings counted in accepted jobs', research.accepted_unit_configuration_exposures],
    ['Cost checks in accepted jobs', research.accepted_unit_scenario_calls],
    ['Real scout configurations', research.real_scout_configurations],
    ['Static rejected designs', research.static_rejected_specs],
    ['Blocked designs', research.blocked_specs],
    ['Distinct trade sequences', research.distinct_trade_sequences],
    ['Independent proof candidates', research.independent_proof_candidates],
    ['Cold exact results', research.cold_exact_results],
    ['Warm recorded results', research.warm_recorded_results],
    ['Hot recorded results', research.hot_recorded_results],
    ['Other recorded results', research.other_recorded_results],
    ['Campaign settings committed', research.campaign_committed_exposures],
    ['Campaign settings remaining', research.campaign_remaining_exposures],
    ['Past call count: lower bound', research.campaign_call_lower_bound],
    ['Past call count: upper bound', research.campaign_call_upper_bound],
    ['Warehouse designs (not market tests)', research.warehouse_designs],
    ['Shared intelligence source state', research.intelligence_source_health],
    ['Supertrend study state', research.supertrend_experiment_state],
    ['Supertrend designs (not market tests)', research.supertrend_inventory_designs],
    ['Supertrend synthetic cost checks', research.supertrend_synthetic_cost_checks],
    ['Synthetic cost checks (not market tests)', research.synthetic_checks],
    ['Verified edges', research.verified_edge_count],
    ['Last saved stop reason', research.saved_stop_class],
  ]
  const items = [
    ['Runtime health', visibility.status], ['Dataset state', projection.dataset_state], ['Collector state', projection.collector_state],
    ['Backtest state', projection.backtest_state], ['Strategy research', projection.strategy_research_state], ['PAPER state', projection.paper_state],
    ['LIVE state', 'BLOCKED'], ['Lock state', visibility.lock_status ?? visibility.runtime_lock?.status], ['Data freshness', state.stale ? 'STALE' : state.envelope?.freshness],
    ['Service status', state.connection], ['Test status', projection.test_status], ['Current blockers', projection.blockers],
    ['Last verified update', state.lastEventAt ?? state.envelope?.as_of],
  ]
  return <section className="milestonePage"><PageHeader eyebrow="READ-ONLY TECHNICAL VIEW" title="System Status" description="Current runtime, evidence, lock, and safety state." />
    <GlassPanel><div className="windowTitle"><b>FOREX RESEARCH PROGRESS</b><small>READ ONLY</small></div>
      <p>{research.label ?? 'RESEARCH RECORDS UNAVAILABLE'}</p>
      <p>A saved result shows past work. It does not prove a worker is running now. Designed bait, sample tests, market tests, and proven edges are different counts.</p>
      <p>Live worker tracking: <strong>{research.live_worker_state ?? 'NOT CONNECTED'}</strong>. An unknown count is not zero.</p>
      <p>Current observations come from the existing research owner when it publishes a fresh, code-checked record. They are owner reports, not an independent process check. The Goal and builder need their own observations.</p>
      <p>News and Supertrend study fields show saved engineering evidence. Offline tests do not establish a live news feed, a market grant, or a proven edge.</p>
    </GlassPanel>
    <div className="statusMatrix">{researchItems.map(([label, value]) => <GlassPanel key={label} family="neutral"><small>{label}</small><strong>{safe(value, 'UNKNOWN')}</strong></GlassPanel>)}</div>
    <div className="statusMatrix">{items.map(([label, value]) => <GlassPanel key={label} family={label === 'LIVE state' ? 'critical' : 'neutral'}><small>{label}</small><strong>{safe(value)}</strong></GlassPanel>)}</div>
    <GlassPanel><div className="windowTitle"><span>▤</span><b>TECHNICAL DETAILS</b><small>READ ONLY</small></div><pre className="technicalReadout">{JSON.stringify({ connection: state.connection, stale: state.stale, errors: state.supportingErrors }, null, 2)}</pre></GlassPanel>
  </section>
}
