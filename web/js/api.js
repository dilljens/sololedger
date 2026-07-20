// SoloLedger API client — Google auth + LLM key support
const API_BASE = '/api/v1';

// ── Auth (Google session only) ────────────────────────────

function getSessionToken() {
  return localStorage.getItem('sololedger_session');
}

function setSessionToken(token) {
  if (token) localStorage.setItem('sololedger_session', token);
  else localStorage.removeItem('sololedger_session');
}

function getUserInfo() {
  const raw = localStorage.getItem('sololedger_user');
  return raw ? JSON.parse(raw) : null;
}

function setUserInfo(user) {
  if (user) localStorage.setItem('sololedger_user', JSON.stringify(user));
  else localStorage.removeItem('sololedger_user');
}

function getAuthToken() {
  return getSessionToken();
}

function isAuthenticated() {
  return !!getSessionToken();
}

function clearAuth() {
  setSessionToken(null);
  setUserInfo(null);
}

// ── LLM API Key (separate from auth) ─────────────────────

function getLlmApiKey() {
  return localStorage.getItem('sololedger_llm_key') || '';
}

function setLlmApiKey(key) {
  if (key) localStorage.setItem('sololedger_llm_key', key);
  else localStorage.removeItem('sololedger_llm_key');
}

function getLlmBackend() {
  return localStorage.getItem('sololedger_llm_backend') || 'openai';
}

function setLlmBackend(backend) {
  if (backend) localStorage.setItem('sololedger_llm_backend', backend);
  else localStorage.removeItem('sololedger_llm_backend');
}

function getLlmModel() {
  return localStorage.getItem('sololedger_llm_model') || 'gpt-4o-mini';
}

function setLlmModel(model) {
  if (model) localStorage.setItem('sololedger_llm_model', model);
  else localStorage.removeItem('sololedger_llm_model');
}

function getLlmConfig() {
  return {
    api_key: getLlmApiKey(),
    backend: getLlmBackend(),
    model: getLlmModel(),
  };
}

// ── Core fetch ────────────────────────────────────────────

const FETCH_TIMEOUT = 30000; // 30s

async function apiFetch(path, options = {}) {
  const token = getAuthToken();
  const headers = { ...options.headers };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Add timeout via AbortController (unless caller provided their own signal)
  let controller = null;
  if (!options.signal) {
    controller = new AbortController();
    setTimeout(() => controller.abort(new DOMException('Request timed out', 'TimeoutError')), FETCH_TIMEOUT);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    signal: options.signal || (controller ? controller.signal : undefined),
  });
  return res;
}

async function apiGet(path) {
  const res = await apiFetch(path);
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      throw new Error('Authentication required');
    }
    throw new Error(`API error: ${res.status}`);
  }
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'API error');
  return json.data;
}

async function apiPost(path, body) {
  const res = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      throw new Error('Authentication required');
    }
    throw new Error(`API error: ${res.status}`);
  }
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'API error');
  return json.data;
}

// ── Public status (no auth needed) ────────────────────────

async function apiGetPublicStatus() {
  try {
    const res = await fetch(`${API_BASE}/public/status`);
    if (!res.ok) return { needsSetup: true, hasAuth: false, auth_methods: {} };
    const json = await res.json();
    if (json.success) return json.data;
    return { needsSetup: true, hasAuth: false, auth_methods: {} };
  } catch {
    return { needsSetup: true, hasAuth: false, auth_methods: {} };
  }
}

// ── Auth helpers ──────────────────────────────────────────

async function apiSignIn(email, password) {
  const res = await fetch(`${API_BASE}/auth/signin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Sign in failed');
  return json.data;
}

async function apiSignUp(email, password, name) {
  const res = await fetch(`${API_BASE}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Sign up failed');
  return json.data;
}

async function apiSignInWithGoogle(credential) {
  const res = await fetch(`${API_BASE}/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Google sign-in failed');
  return json.data;
}

async function apiGetAuthMe() {
  const token = getAuthToken();
  if (!token) return null;
  const res = await apiFetch('/auth/me');
  if (!res.ok) return null;
  const json = await res.json();
  if (!json.success) return null;
  return json.data;
}

async function apiLogout() {
  try {
    await apiPost('/auth/logout', {});
  } catch { /* ignore */ }
  clearAuth();
}

// ── LLM config ────────────────────────────────────────────

async function apiSaveLlmConfig(config) {
  return await apiPost('/settings/llm', config);
}

async function apiGetLlmConfig() {
  try {
    const res = await apiFetch('/settings/llm');
    if (!res.ok) return null;
    const json = await res.json();
    if (json.success) return json.data;
    return null;
  } catch {
    return null;
  }
}

// ── Security / formatting helpers ─────────────────────────

/** Escape a string for safe insertion into innerHTML. */
function escapeHtml(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function fmt(n) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function money(n) {
  const abs = Math.abs(n);
  return (n < 0 ? '-$' : '$') + fmt(abs);
}
