const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = payload?.detail || payload?.message || payload || `Request failed: ${response.status}`
    throw new Error(Array.isArray(detail) ? JSON.stringify(detail) : detail)
  }
  return payload
}

export function fetchSummary(params = {}) {
  const search = new URLSearchParams()
  if (params.current_window_minutes) search.set('current_window_minutes', String(params.current_window_minutes))
  if (params.baseline_window_minutes) search.set('baseline_window_minutes', String(params.baseline_window_minutes))
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request(`/api/customers/summary${suffix}`)
}

export function sendChat(customerId, message) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
      customer_id: customerId,
      message,
    }),
  })
}

export function fetchAlerts(customerId, params = {}) {
  const search = new URLSearchParams()
  if (params.current_window_minutes) search.set('current_window_minutes', String(params.current_window_minutes))
  if (params.baseline_window_minutes) search.set('baseline_window_minutes', String(params.baseline_window_minutes))
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request(`/api/customers/${encodeURIComponent(customerId)}/alerts${suffix}`)
}

export function triggerSpike(customerId, multiplier = 5, remainingCalls = 5) {
  return request(`/api/simulate_spike?customer_id=${encodeURIComponent(customerId)}&multiplier=${multiplier}&remaining_calls=${remainingCalls}`)
}
