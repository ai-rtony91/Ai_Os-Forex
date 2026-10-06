const EVENTS = [
  { type: 'data_stale', severity: 'review', timestamp: 'DEMONSTRATION', source: 'dashboard', freshness: 'UNKNOWN', text: 'Data freshness verification is required.', route: '/overview' },
  { type: 'configuration_draft', severity: 'info', timestamp: 'DEMONSTRATION', source: 'local guidance', freshness: 'UNKNOWN', text: 'A strategy draft may be prepared for review.', route: '/strategy-maintenance' },
]
export default function NotificationCenter({ open, onClose, navigate }) {
  if (!open) return null
  return <aside className="utilityDrawer" aria-label="Notification center"><header><div><small>NOTIFICATIONS</small><h2>Operational signals</h2></div><button type="button" onClick={onClose} aria-label="Close notifications">×</button></header>
    {EVENTS.map((event) => <button type="button" className="notificationItem" key={event.type} onClick={() => { navigate(event.route); onClose() }}><span className={`severity severity-${event.severity}`}>{event.severity}</span><b>{event.text}</b><small>{event.source} · {event.timestamp} · {event.freshness}</small></button>)}
  </aside>
}
