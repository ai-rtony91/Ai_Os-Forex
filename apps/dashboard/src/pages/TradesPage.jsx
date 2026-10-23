import { useState } from 'react'
import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { formatCurrency } from '../utils/formatFinance.js'
const TABS = ['OPEN', 'CLOSED', 'WINNERS', 'LOSSES', 'REJECTED SIGNALS', 'RISK-BLOCKED', 'EXECUTION ERRORS']
const FIELDS = ['TIME','PAIR','↕','ENTRY','EXIT','R','P/L']
export default function TradesPage({ state }) {
  const [tab, setTab] = useState('OPEN')
  const runtime = state.envelope?.source === 'runtime'
  const data = runtime ? (state.envelope?.data ?? {}) : {}
  const rows = Array.isArray(data.trades) ? data.trades : []
  const filtered = rows.filter((trade) => tab === 'OPEN' ? trade.status === 'OPEN' : tab === 'CLOSED' ? trade.status === 'CLOSED' : tab === 'WINNERS' ? Number(trade.pnl) > 0 : tab === 'LOSSES' ? Number(trade.pnl) < 0 : trade.category === tab)
  return <><PageHeader title="Trade Journal" actions={<span className="readModelBadge">{runtime ? state.envelope.mode : 'NOT CONNECTED'}</span>} />
    <div className="tabBar" role="tablist">{TABS.map((item) => <button type="button" role="tab" key={item} aria-selected={tab === item} onClick={() => setTab(item)}>{item}</button>)}</div>
    <GlassPanel family={tab === 'EXECUTION ERRORS' ? 'critical' : 'market'} importance="important"><div className="windowTitle"><span>⇄</span><b>{tab}</b><small>READ ONLY</small></div>{filtered.length ? <div className="tableScroll"><table className="journalTable"><thead><tr>{FIELDS.map((field) => <th key={field}>{field}</th>)}</tr></thead><tbody>{filtered.map((trade, index) => <tr key={trade.id ?? `${trade.pair}-${index}`}><td>{trade.time ?? 'UNKNOWN'}</td><td><b>{trade.pair ?? 'UNKNOWN'}</b></td><td>{trade.direction ?? 'UNKNOWN'}</td><td>{trade.entry ?? 'NO DATA'}</td><td>{trade.exit ?? 'NO DATA'}</td><td>{trade.r ?? 'NO DATA'}</td><td className="moneyCell">{Number.isFinite(Number(trade.pnl)) ? formatCurrency(Number(trade.pnl)) : 'NO DATA'}</td></tr>)}</tbody></table></div> : <div className="windowEmpty"><b>{runtime ? 'NO QUALIFYING TRADES' : 'NOT CONNECTED'}</b><small>NO VERIFIED TRADE RECORDS</small></div>}</GlassPanel>
  </>
}
