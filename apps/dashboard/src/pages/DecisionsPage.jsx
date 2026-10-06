import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'

const safe = (value, fallback = 'NO EVIDENCE') => value === null || value === undefined || value === '' ? fallback : String(value)
const dataOf = (value) => value?.data ?? value?.payload ?? value ?? {}

export default function DecisionsPage({ state }) {
  const projection = dataOf(state.projection)
  const decisions = Array.isArray(projection.decisions) ? projection.decisions : []
  const latest = projection.latest_decision ?? decisions[0] ?? {}
  return <section className="milestonePage"><PageHeader eyebrow="READ-ONLY EVIDENCE" title="Decisions" description="Why AIOS accepted, rejected, or waited on a signal." />
    <div className="pageTabs" role="tablist">{['Accepted', 'Rejected', 'Waiting', 'All'].map((tab, index) => <button key={tab} type="button" role="tab" aria-selected={index === 3}>{tab}</button>)}</div>
    <div className="filterGrid"><label>Pair<select><option>All pairs</option></select></label><label>Direction<select><option>All directions</option></select></label><label>Strategy<select><option>All strategies</option></select></label><label>Result<select><option>All results</option></select></label><label>Date<input type="date" /></label></div>
    <div className="twoPane"><GlassPanel family="research"><div className="windowTitle"><span>🎯</span><b>LATEST DECISION</b><small>{safe(latest.timestamp, 'NOT RUN')}</small></div><strong className="stateHero">{safe(latest.result)}</strong><dl className="detailFacts"><div><dt>Signal</dt><dd>{safe(latest.direction)}</dd></div><div><dt>Pair</dt><dd>{safe(latest.pair)}</dd></div><div><dt>Granularity</dt><dd>{safe(latest.granularity)}</dd></div><div><dt>Strategy</dt><dd>{safe(latest.strategy)}</dd></div><div><dt>Requirements passed</dt><dd>{safe(latest.passed_conditions)}</dd></div><div><dt>Requirements failed</dt><dd>{safe(latest.failed_conditions)}</dd></div><div><dt>Rejection reason</dt><dd>{safe(latest.reason)}</dd></div><div><dt>Data freshness</dt><dd>{state.stale ? 'STALE' : 'UNKNOWN'}</dd></div></dl></GlassPanel>
    <GlassPanel><div className="windowTitle"><span>▤</span><b>DECISION HISTORY</b><small>{decisions.length ? `${decisions.length} RECORDS` : 'NO EVIDENCE'}</small></div>{decisions.length ? <div className="tableScroll"><table><thead><tr><th>Time</th><th>Pair</th><th>Direction</th><th>Result</th></tr></thead><tbody>{decisions.map((item, index) => <tr key={item.id ?? index}><td>{safe(item.timestamp)}</td><td>{safe(item.pair)}</td><td>{safe(item.direction)}</td><td><button className="detailButton" type="button">View {safe(item.result)}</button></td></tr>)}</tbody></table></div> : <div className="windowEmpty"><b>NO EVIDENCE</b><small>DECISION HISTORY IS UNAVAILABLE</small></div>}</GlassPanel></div>
  </section>
}
