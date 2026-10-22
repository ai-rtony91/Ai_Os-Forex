export default function GlobalStatusBar({ envelope, connection, stale, runtimeVisibility }) {
  const runtime = envelope?.source === 'runtime'
  const data = runtime ? (envelope?.data ?? {}) : {}
  const clock = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'UTC', hour12: false }).format(new Date())
  const items = [
    ['TIME', `${clock} UTC`],
    ['RUNTIME', runtimeVisibility?.status ?? connection ?? 'UNAVAILABLE'],
    ['MODE', runtime ? envelope?.mode : 'NO EVIDENCE'],
    ['DATA', stale ? 'STALE' : (runtime ? envelope?.freshness : 'UNAVAILABLE')],
    ['SAFETY', data.risk_status ?? 'BLOCKED'],
    ['LOCK', runtimeVisibility?.lock_status ?? runtimeVisibility?.runtime_lock?.status ?? 'UNKNOWN'],
  ]
  return <div className="globalStatus topRuntimeStrip" role="status" aria-label="Global system status">{items.map(([label, value]) => <span key={label} data-state={String(value).toLowerCase()}><small>{label}</small><b>{String(value)}</b></span>)}</div>
}
