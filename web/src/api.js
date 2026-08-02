/**
 * SoloLedger API Client for Vue.js
 * Wraps the existing FastAPI endpoints with auth and error handling.
 */

const API_BASE = '/api/v1'
const REQUEST_TIMEOUT = 30000 // 30s

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const headers = { ...options.headers }

  // Don't set Content-Type for FormData (browser sets it with boundary)
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  // Add auth token if available
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT)

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    })

    // Read the body as text first so non-JSON error bodies don't crash
    // the JSON.parse with "Unexpected token".
    const text = await response.text()
    let data = null
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        data = text
      }
    }

    if (!response.ok) {
      let message
      if (data && typeof data === 'object') {
        message = data.error || data.detail || `HTTP ${response.status}`
      } else if (typeof data === 'string' && data) {
        message = data
      } else {
        message = `HTTP ${response.status}`
      }
      throw new ApiError(message, response.status, data)
    }

    return data
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err.name === 'AbortError') throw new ApiError('Request timed out', 0, null)
    throw new ApiError(err.message, 0, null)
  } finally {
    clearTimeout(timeout)
  }
}

export async function apiGet(path) {
  const res = await request(path)
  return res.data
}

export async function apiPost(path, body) {
  const res = await request(path, {
    method: 'POST',
    body: body instanceof FormData ? body : JSON.stringify(body),
  })
  return res.data
}

export async function apiPut(path, body) {
  const res = await request(path, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return res.data
}

export async function apiDelete(path) {
  const res = await request(path, { method: 'DELETE' })
  return res.data
}

export async function apiUpload(path, file, extraFields = {}) {
  const formData = new FormData()
  formData.append('file', file)
  for (const [key, value] of Object.entries(extraFields)) {
    formData.append(key, value)
  }
  return apiPost(path, formData)
}

// ── Auth helpers ────────────────────────────────────────────────────
// The classic UI (web/js) stores the session under `sololedger_session`;
// this UI used `auth_token`. Read/write BOTH keys so switching UIs keeps
// the session (the backend session is shared; only the client key differs).

export function isAuthenticated() {
  return !!getAuthToken()
}

export function getAuthToken() {
  return localStorage.getItem('auth_token') || localStorage.getItem('sololedger_session')
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem('auth_token', token)
    localStorage.setItem('sololedger_session', token)
  } else {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('sololedger_session')
  }
}

export function clearAuth() {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('sololedger_session')
  localStorage.removeItem('user_email')
}
