export function formatSseEvent(type, payload) {
  return `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`
}

export function createDashboardEventStream({ snapshot, heartbeatMs = 15000 }) {
  return function serveEvents(request, response) {
    response.writeHead(200, {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-store',
      connection: 'keep-alive',
      'x-accel-buffering': 'no',
    })
    const initial = snapshot()
    response.write(formatSseEvent('snapshot', {
      timestamp: new Date().toISOString(), source: initial.source, payload: initial,
    }))
    response.write(formatSseEvent('status_change', {
      timestamp: new Date().toISOString(), source: initial.source, status: 'STREAM_CONNECTED',
    }))
    const heartbeatTimer = setInterval(() => {
      response.write(formatSseEvent('heartbeat', {
        timestamp: new Date().toISOString(), source: initial.source,
      }))
    }, heartbeatMs)
    const demonstrationValues = [-42.15, -36.8, -48.2, -39.4]
    let sequence = 0
    const metricTimer = setInterval(() => {
      sequence = (sequence + 1) % demonstrationValues.length
      response.write(formatSseEvent('metric_change', {
        timestamp: new Date().toISOString(), source: initial.source, metric: 'unrealized_pnl', value: demonstrationValues[sequence], sequence,
      }))
    }, 30000)
    request.on('close', () => { clearInterval(heartbeatTimer); clearInterval(metricTimer) })
  }
}
