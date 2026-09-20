export const initialDashboardState = Object.freeze({ envelope: null, previousEnvelope: null, runtimeVisibility: null, forexCampaign: null, projection: null, supportingErrors: {}, connection: 'CONNECTING', error: null, lastEventAt: null, stale: false })
export function dashboardReducer(state, action) {
  switch (action.type) {
    case 'SNAPSHOT': return { ...state, previousEnvelope: state.envelope, envelope: action.payload, error: null, lastEventAt: new Date().toISOString(), stale: false }
    case 'SUPPORTING_SNAPSHOT': return { ...state, ...action.payload, supportingErrors: action.errors ?? {}, lastEventAt: new Date().toISOString() }
    case 'CONNECTION': return { ...state, connection: action.payload }
    case 'METRIC_CHANGE': {
      if (!state.envelope?.data?.metrics || !action.payload?.metric) return state
      return { ...state, previousEnvelope: state.envelope, lastEventAt: action.payload.timestamp, stale: false, envelope: { ...state.envelope, as_of: action.payload.timestamp, data: { ...state.envelope.data, metrics: { ...state.envelope.data.metrics, [action.payload.metric]: action.payload.value } } } }
    }
    case 'ERROR': return { ...state, error: action.payload, connection: 'UNAVAILABLE' }
    case 'STALE': return { ...state, stale: true }
    default: return state
  }
}
