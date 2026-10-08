import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
const safe = (value, fallback = 'NO EVIDENCE') => value === null || value === undefined || value === '' ? fallback : String(value)
const dataOf = (value) => value?.data ?? value?.payload ?? value ?? {}
export default function PostMortemPage({ state }) {
  const projection = dataOf(state.projection)
  const reviews = Array.isArray(projection.post_mortems) ? projection.post_mortems : []
  const item = reviews[0] ?? {}
  const researchReviews = state.researchHistory?.data?.rows ?? []
  return <section className="milestonePage"><PageHeader eyebrow="RULE REVIEW" title="Post-Mortem" description="Read-only trade and rejection review backed by available receipts." />
    <div className="pageTabs" role="tablist">{['Wins', 'Losses', 'Breakeven', 'Rejected', 'All'].map((tab, index) => <button key={tab} type="button" role="tab" aria-selected={index === 4}>{tab}</button>)}</div>
    <div className="filterGrid"><label>Date<input type="date" /></label><label>Pair<select><option>All pairs</option></select></label><label>Direction<select><option>All directions</option></select></label><label>Strategy<select><option>All strategies</option></select></label></div>
    <GlassPanel family="research"><div className="windowTitle"><b>SAVED RESEARCH ROUTING</b><small>READ ONLY</small></div><p>These links join saved acceptance, post-mortem and Hot/Cold records. They do not prove an edge.</p>
      {researchReviews.length ? researchReviews.map((row, index) => <dl className="detailFacts" key={row.receipt_id ?? index}>
        <div><dt>Candidate</dt><dd>{safe(row.candidate_id)}</dd></div><div><dt>Route</dt><dd>{safe(row.route)}</dd></div>
        <div><dt>Post-mortem linked</dt><dd>{row.postmortem_linked ? 'YES' : 'NO'}</dd></div>
        <div><dt>Closed scope</dt><dd>{safe(row.rejection_scope)}</dd></div><div><dt>Proof state</dt><dd>{safe(row.proof_state)}</dd></div>
        <div><dt>Receipt</dt><dd>{safe(row.receipt_id)}</dd></div>
      </dl>) : <p>NO CONNECTED RESEARCH REVIEW</p>}</GlassPanel>
    <GlassPanel family="research"><div className="windowTitle"><span>🧠</span><b>POST-MORTEM DETAIL</b><small>{reviews.length ? 'SAVED RECORD' : 'NO EVIDENCE'}</small></div><dl className="detailFacts"><div><dt>Trade result</dt><dd>{safe(item.result)}</dd></div><div><dt>Pair / direction</dt><dd>{safe(item.pair)} / {safe(item.direction)}</dd></div><div><dt>Entry / exit</dt><dd>{safe(item.entry)} / {safe(item.exit)}</dd></div><div><dt>R result</dt><dd>{safe(item.r_result)}</dd></div><div><dt>Strategy</dt><dd>{safe(item.strategy)}</dd></div><div><dt>Decision evidence</dt><dd>{safe(item.decision_evidence)}</dd></div><div><dt>Reason</dt><dd>{safe(item.reason)}</dd></div><div><dt>Market conditions</dt><dd>{safe(item.market_conditions)}</dd></div><div><dt>Rule compliance</dt><dd>{safe(item.rule_compliance)}</dd></div><div><dt>Risk compliance</dt><dd>{safe(item.risk_compliance)}</dd></div><div><dt>Lessons</dt><dd>{safe(item.lessons)}</dd></div><div><dt>Receipt / screenshot</dt><dd>{safe(item.receipt_reference)}</dd></div></dl></GlassPanel>
  </section>
}
