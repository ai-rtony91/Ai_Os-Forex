import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
const safe = (value, fallback = 'UNAVAILABLE') => value === null || value === undefined || value === '' ? fallback : String(value)
const dataOf = (value) => value?.data ?? value?.payload ?? value ?? {}
export default function PositionsPage({ state }) {
  const projection = dataOf(state.projection)
  const positions = Array.isArray(projection.positions) ? projection.positions : []
  const current = projection.position ?? positions.find((item) => item.state === 'ACTIVE') ?? {}
  return <section className="milestonePage"><PageHeader eyebrow="READ-ONLY EVIDENCE" title="Positions" description="Position evidence only. There are no order controls." />
    <div className="pageTabs" role="tablist">{['Active', 'Closed', 'Rejected', 'All'].map((tab, index) => <button key={tab} type="button" role="tab" aria-selected={index === 3}>{tab}</button>)}</div>
    <div className="filterGrid compactFilters"><label>Pair<select><option>All pairs</option></select></label><label>Date<input type="date" /></label></div>
    <div className="twoPane"><GlassPanel family="market"><div className="windowTitle"><span>💼</span><b>CURRENT POSITION</b><small>READ ONLY</small></div><strong className="stateHero">{safe(current.state, 'NO POSITION EVIDENCE')}</strong><dl className="detailFacts"><div><dt>Pair</dt><dd>{safe(current.pair)}</dd></div><div><dt>Direction</dt><dd>{safe(current.direction)}</dd></div><div><dt>Entry</dt><dd>{safe(current.entry)}</dd></div><div><dt>Stop loss</dt><dd>{safe(current.stop_loss)}</dd></div><div><dt>Take profit</dt><dd>{safe(current.take_profit)}</dd></div><div><dt>Units</dt><dd>{safe(current.units)}</dd></div><div><dt>R:R</dt><dd>{safe(current.risk_reward)}</dd></div><div><dt>Age</dt><dd>{safe(current.age)}</dd></div><div><dt>Current R</dt><dd>{safe(current.current_r)}</dd></div><div><dt>P/L class</dt><dd>{safe(current.pnl_classification, 'NO EVIDENCE')}</dd></div></dl></GlassPanel>
    <GlassPanel><div className="windowTitle"><span>▤</span><b>POSITION HISTORY</b><small>{positions.length ? `${positions.length} RECORDS` : 'NO EVIDENCE'}</small></div>{positions.length ? <div className="tableScroll"><table><thead><tr><th>Pair</th><th>Direction</th><th>State</th><th>R</th></tr></thead><tbody>{positions.map((item, index) => <tr key={item.id ?? index}><td>{safe(item.pair)}</td><td>{safe(item.direction)}</td><td>{safe(item.state)}</td><td>{safe(item.current_r)}</td></tr>)}</tbody></table></div> : <div className="windowEmpty"><b>NO EVIDENCE</b><small>POSITION HISTORY IS UNAVAILABLE</small></div>}</GlassPanel></div>
  </section>
}
