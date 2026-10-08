const API_ROOT = '/api/v1'

async function fetchJson(url, options = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch(url, { ...options, signal: controller.signal })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload?.data?.reason ?? `Dashboard API returned ${response.status}.`)
    return payload
  } finally { clearTimeout(timer) }
}

async function request(path, options = {}) {
  return fetchJson(`${API_ROOT}${path}`, { ...options, headers: { 'content-type': 'application/json', ...(options.headers ?? {}) } })
}

async function readOnlyRequest(path) {
  return fetchJson(path, { method: 'GET', headers: { accept: 'application/json' } })
}

export const dashboardApi = Object.freeze({
  health: () => request('/health'), capabilities: () => request('/capabilities'), snapshot: () => request('/dashboard/snapshot'),
  marketDrivers: () => request('/market-drivers'), brokerStatus: () => request('/broker/status'),
  maintenanceStatus: () => request('/maintenance/status'), about: () => request('/about'), gallery: () => request('/about/gallery'),
  validateStrategyDraft: (draft) => request('/strategy-drafts/validate', { method: 'POST', body: JSON.stringify(draft) }),
  researchStatus: () => request('/research/status'),
  researchHistory: () => request('/research/history'),
  runtimeVisibility: () => readOnlyRequest('/api/runtime/visibility'),
  forexCampaign: () => readOnlyRequest('/api/forex/paper-campaign'),
  projection: () => readOnlyRequest('/aios-dashboard-projection'),
})
