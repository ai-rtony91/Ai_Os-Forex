export function connectDashboardEvents({ onEvent, onState }) {
  let eventSource
  let retryTimer
  let attempts = 0
  let stopped = false
  const connect = () => {
    if (stopped) return
    onState?.('CONNECTING')
    eventSource = new EventSource('/api/v1/dashboard/events')
    const receive = (event) => {
      attempts = 0
      onState?.('CONNECTED')
      try { onEvent?.(event.type, JSON.parse(event.data)) } catch { onState?.('INVALID EVENT') }
    }
    ;['snapshot', 'metric_change', 'status_change', 'heartbeat'].forEach((type) => eventSource.addEventListener(type, receive))
    eventSource.onerror = () => {
      eventSource.close()
      onState?.('RECONNECTING')
      const wait = Math.min(1000 * (2 ** attempts), 15000)
      attempts = Math.min(attempts + 1, 4)
      retryTimer = window.setTimeout(connect, wait)
    }
  }
  connect()
  return () => { stopped = true; window.clearTimeout(retryTimer); eventSource?.close(); onState?.('DISCONNECTED') }
}
