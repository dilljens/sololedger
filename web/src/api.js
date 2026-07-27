/**
 * SoloLedger API Client for Vue.js
 * Wraps the existing FastAPI endpoints with auth and error handling.
 */

const API_BASE = '/api/v1'

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
  const token = localStorage.getItem('auth_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    })

    const data = await response.json()

    if (!response.ok) {
      throw new ApiError(
        data.error || `HTTP ${response.status}`,
        response.status,
        data
      )
    }

    return data
  } catch (err) {
    if (err instanceof ApiError) throw err
    throw new ApiError(err.message, 0, null)
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

export function isAuthenticated() {
  return !!localStorage.getItem('auth_token')
}

export function getAuthToken() {
  return localStorage.getItem('auth_token')
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem('auth_token', token)
  } else {
    localStorage.removeItem('auth_token')
  }
}

export function clearAuth() {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('user_email')
}
