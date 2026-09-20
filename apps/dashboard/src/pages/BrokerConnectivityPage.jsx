import { useEffect, useState } from 'react'
import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
import { dashboardApi } from '../services/dashboardApi.js'
export default function BrokerConnectivityPage() {
  const [status, setStatus] = useState({})
  useEffect(() => { dashboardApi.brokerStatus().then((envelope) => setStatus(envelope.data)).catch(() => setStatus({ connection_state: 'NOT CONNECTED' })) }, [])
  return <><PageHeader title="Broker & Connectivity" description="Sanitized operational state only. No account identifier, credential input, order control, or raw broker response." actions={<span className="haltBadge">LIVE BLOCKED</span>} /><GlassPanel family="risk"><dl className="detailGrid">{Object.entries(status).map(([key, value]) => <div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{value}</dd></div>)}</dl></GlassPanel><GlassPanel family="neutral"><h2>Credential boundary</h2><p>RUNTIME ONLY means credentials, if separately configured for an approved process, remain outside this browser and are never displayed here. This preview does not inspect them.</p></GlassPanel></>
}
