const API_ROOT = '/api/v1'

async function request(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers: { 'content-type': 'application/json', ...(options.headers ?? {}) },
  })
  const payload = await response.json()
  if (!response.ok) throw new Error(payload?.data?.reason ?? `Dashboard API returned ${response.status}.`)
  return payload
}

async function readOnlyRequest(path) {
  const response = await fetch(path, { method: 'GET', headers: { accept: 'application/json' } })
  if (!response.ok) throw new Error(`${path} returned ${response.status}.`)
  return response.json()
}

export const dashboardApi = Object.freeze({
  health: () => request('/health'), capabilities: () => request('/capabilities'), snapshot: () => request('/dashboard/snapshot'),
  marketDrivers: () => request('/market-drivers'), brokerStatus: () => request('/broker/status'),
  maintenanceStatus: () => request('/maintenance/status'), about: () => request('/about'), gallery: () => request('/about/gallery'),
  validateStrategyDraft: (draft) => request('/strategy-drafts/validate', { method: 'POST', body: JSON.stringify(draft) }),
  runtimeVisibility: () => readOnlyRequest('/api/runtime/visibility'),
  forexCampaign: () => readOnlyRequest('/api/forex/paper-campaign'),
  projection: () => readOnlyRequest('/aios-dashboard-projection'),
})
