import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
const TYPES = ['Strategy reports', 'Performance reports', 'Dataset reports', 'Validation receipts', 'Freeze receipts', 'PAPER evidence', 'Risk reports', 'Runtime reports']
export default function ReportsPage() {
  return <section className="milestonePage"><PageHeader eyebrow="EVIDENCE LIBRARY" title="Reports" description="Search and preview verified evidence. No report is invented when a source is unavailable." />
    <div className="filterGrid"><label>Search<input type="search" placeholder="Search report names" /></label><label>Date<input type="date" /></label><label>Pair<select><option>All pairs</option></select></label><label>Strategy<select><option>All strategies</option></select></label><label>Report type<select><option>All report types</option>{TYPES.map((type) => <option key={type}>{type}</option>)}</select></label></div>
    <div className="reportGrid">{TYPES.map((type) => <GlassPanel key={type}><div className="windowTitle"><span>▤</span><b>{type.toUpperCase()}</b></div><strong className="stateHero">NO EVIDENCE</strong><small>UNAVAILABLE FROM THE CURRENT READ-ONLY CONTRACT</small></GlassPanel>)}</div>
    <GlassPanel className="reportPreview"><div className="windowTitle"><span>⌕</span><b>READ-ONLY REPORT PREVIEW</b><small>NOT SELECTED</small></div><div className="windowEmpty"><b>NO REPORT SELECTED</b><small>SAFE EXPORT APPEARS ONLY WHEN SUPPORTED</small></div></GlassPanel>
  </section>
}
