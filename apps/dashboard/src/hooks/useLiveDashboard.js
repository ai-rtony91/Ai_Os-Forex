import { useEffect, useReducer, useRef } from 'react'
import { dashboardApi } from '../services/dashboardApi.js'
import { connectDashboardEvents } from '../services/dashboardEvents.js'
import { dashboardReducer, initialDashboardState } from '../state/dashboardReducer.js'

export function useLiveDashboard(staleAfterMs = 45000, refreshMs = 30000) {
  const [state, dispatch] = useReducer(dashboardReducer, initialDashboardState)
  const lastEventAt = useRef(null)
  useEffect(() => {
    let active = true
    let supportingBusy = false
    const loadSupporting = async () => {
      if (supportingBusy) return
      supportingBusy = true
      const requests = [
        ['runtimeVisibility', dashboardApi.runtimeVisibility()],
        ['forexCampaign', dashboardApi.forexCampaign()],
        ['projection', dashboardApi.projection()],
        ['researchStatus', dashboardApi.researchStatus()],
        ['researchHistory', dashboardApi.researchHistory()],
      ]
      const settled = await Promise.allSettled(requests.map(([, request]) => request))
      supportingBusy = false
      if (!active) return
      const payload = {}
      const errors = {}
      settled.forEach((result, index) => {
        const key = requests[index][0]
        if (result.status === 'fulfilled') payload[key] = result.value
        else { errors[key] = result.reason?.message ?? 'UNAVAILABLE'; if (['researchStatus', 'researchHistory'].includes(key)) payload[key] = null }
      })
      dispatch({ type: 'SUPPORTING_SNAPSHOT', payload, errors })
    }
    dashboardApi.snapshot().then((payload) => active && dispatch({ type: 'SNAPSHOT', payload })).catch((error) => active && dispatch({ type: 'ERROR', payload: error.message }))
    loadSupporting()
    const refreshTimer = window.setInterval(loadSupporting, Math.max(10000, Number(refreshMs) || 30000))
    const disconnect = connectDashboardEvents({
      onState: (value) => active && dispatch({ type: 'CONNECTION', payload: value }),
      onEvent: (type, event) => { if (!active) return; lastEventAt.current = event.timestamp ?? new Date().toISOString(); if (type === 'snapshot' && event.payload) dispatch({ type: 'SNAPSHOT', payload: event.payload }); if (type === 'metric_change') dispatch({ type: 'METRIC_CHANGE', payload: event }); if (type === 'research_status' && event.payload) dispatch({ type: 'RESEARCH_STATUS', payload: event.payload, timestamp: event.timestamp }) },
    })
    const staleTimer = window.setInterval(() => {
      dispatch({ type: 'RESEARCH_OBSERVATION_EXPIRE', timestamp: new Date().toISOString() })
      if (lastEventAt.current && Date.now() - Date.parse(lastEventAt.current) > staleAfterMs) dispatch({ type: 'STALE' })
    }, 5000)
    return () => { active = false; disconnect(); window.clearInterval(staleTimer); window.clearInterval(refreshTimer) }
  }, [staleAfterMs, refreshMs])
  return state
}
