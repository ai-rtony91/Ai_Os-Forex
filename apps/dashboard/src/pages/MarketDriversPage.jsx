import { useEffect, useState } from 'react'
import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { dashboardApi } from '../services/dashboardApi.js'
export default function MarketDriversPage() {
  const [envelope, setEnvelope] = useState(null)
  useEffect(() => { dashboardApi.marketDrivers().then(setEnvelope).catch(() => setEnvelope({ data: { drivers: [] } })) }, [])
  const drivers = envelope?.data?.drivers ?? []
  return <><PageHeader title="Likely Market Drivers" description="Hypothesis-oriented context. Events are never presented as definitive causes of profitable trades." actions={<span className="demoBadge">LICENSED SOURCE: NOT CONFIGURED</span>} />{drivers.length ? <div className="driverGrid">{drivers.map((driver) => <GlassPanel family="research" key={driver.pair}><div className="panelHeading"><div><small>{driver.confidence} CONFIDENCE · DEMONSTRATION</small><h2>{driver.pair}</h2></div><span>{driver.trade_result}</span></div><dl className="detailGrid">{Object.entries(driver).filter(([key]) => !['pair','confidence','source_links'].includes(key)).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{Array.isArray(value) ? value.join(' · ') : value}</dd></div>)}</dl><p>Source links: UNAVAILABLE</p></GlassPanel>)}</div> : <div className="emptyState">No approved market-driver source is configured.</div>}</>
}
