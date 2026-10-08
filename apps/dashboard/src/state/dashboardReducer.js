export const initialDashboardState = Object.freeze({ envelope: null, previousEnvelope: null, runtimeVisibility: null, researchStatus: null, researchHistory: null, researchFetchedAt: null, forexCampaign: null, projection: null, supportingErrors: {}, connection: 'CONNECTING', error: null, lastEventAt: null, stale: false })
export function dashboardReducer(state, action) {
  switch (action.type) {
    case 'SNAPSHOT': return { ...state, previousEnvelope: state.envelope, envelope: action.payload, error: null, lastEventAt: new Date().toISOString(), stale: false }
    case 'SUPPORTING_SNAPSHOT': return { ...state, ...action.payload, supportingErrors: action.errors ?? {}, researchFetchedAt: new Date().toISOString(), lastEventAt: new Date().toISOString() }
    case 'RESEARCH_STATUS': return { ...state, researchStatus: action.payload, researchFetchedAt: action.timestamp }
    case 'RESEARCH_OBSERVATION_EXPIRE': {
      const research = state.researchStatus?.data
      if (!research || !['ACTIVE_OWNER_REPORTED', 'STOPPED', 'WAITING_FOR_OWNER'].includes(research.live_worker_state)) return state
      const age = Date.parse(action.timestamp) - Date.parse(research.worker_heartbeat_at)
      if (Number.isFinite(age) && age >= 0 && age <= 30000) return state
      return { ...state, researchStatus: { ...state.researchStatus, data: { ...research, live_worker_state: 'STALE', live_worker_count: null } } }
    }
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
