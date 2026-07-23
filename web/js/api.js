// SoloLedger API client — Google auth + LLM key support
export const API_BASE = '/api/v1';

const FETCH_TIMEOUT = 30000; // 30s

// ── Auth (Google session only) ────────────────────────────

export function getSessionToken() {
  return localStorage.getItem('sololedger_session');
}

export function setSessionToken(token) {
  if (token) localStorage.setItem('sololedger_session', token);
  else localStorage.removeItem('sololedger_session');
}

export function getUserInfo() {
  const raw = localStorage.getItem('sololedger_user');
  return raw ? JSON.parse(raw) : null;
}

export function setUserInfo(user) {
  if (user) localStorage.setItem('sololedger_user', JSON.stringify(user));
  else localStorage.removeItem('sololedger_user');
}

export function getAuthToken() {
  return getSessionToken();
}

export function isAuthenticated() {
  return !!getSessionToken();
}

export function clearAuth() {
  setSessionToken(null);
  setUserInfo(null);
}

// ── LLM API Key (separate from auth) ─────────────────────

export function getLlmApiKey() {
  return localStorage.getItem('sololedger_llm_key') || '';
}

export function setLlmApiKey(key) {
  if (key) localStorage.setItem('sololedger_llm_key', key);
  else localStorage.removeItem('sololedger_llm_key');
}

export function getLlmBackend() {
  return localStorage.getItem('sololedger_llm_backend') || 'openai';
}

export function setLlmBackend(backend) {
  if (backend) localStorage.setItem('sololedger_llm_backend', backend);
  else localStorage.removeItem('sololedger_llm_backend');
}

export function getLlmModel() {
  return localStorage.getItem('sololedger_llm_model') || 'gpt-4o-mini';
}

export function setLlmModel(model) {
  if (model) localStorage.setItem('sololedger_llm_model', model);
  else localStorage.removeItem('sololedger_llm_model');
}

export function getLlmConfig() {
  return {
    api_key: getLlmApiKey(),
    backend: getLlmBackend(),
    model: getLlmModel(),
  };
}

// ── Core fetch ────────────────────────────────────────────

export async function apiFetch(path, options = {}) {
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

  // Show loading bar (skip for public/non-critical endpoints)
  const skipLoading = options.skipLoading || path.includes('/health');
  if (!skipLoading) showLoading();

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      signal: options.signal || (controller ? controller.signal : undefined),
    });
    return res;
  } finally {
    if (!skipLoading) hideLoading();
  }
}

export async function apiGet(path) {
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

export async function apiPost(path, body) {
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

export async function apiGetPublicStatus() {
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

export async function apiSignIn(email, password) {
  const res = await fetch(`${API_BASE}/auth/signin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Sign in failed');
  return json.data;
}

export async function apiSignUp(email, password, name) {
  const res = await fetch(`${API_BASE}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Sign up failed');
  return json.data;
}

export async function apiSignInWithGoogle(credential) {
  const res = await fetch(`${API_BASE}/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Google sign-in failed');
  return json.data;
}

export async function apiGetAuthMe() {
  const token = getAuthToken();
  if (!token) return null;
  const res = await apiFetch('/auth/me');
  if (!res.ok) return null;
  const json = await res.json();
  if (!json.success) return null;
  return json.data;
}

export async function apiLogout() {
  try {
    await apiPost('/auth/logout', {});
  } catch { /* ignore */ }
  clearAuth();
}

// ── LLM config ────────────────────────────────────────────

export async function apiSaveLlmConfig(config) {
  return await apiPost('/settings/llm', config);
}

export async function apiGetLlmConfig() {
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

// ── Loading Bar ───────────────────────────────────────────

let loadingTimer = null;

export function showLoading() {
  const bar = document.getElementById('loading-bar');
  if (!bar) return;
  clearTimeout(loadingTimer);
  bar.className = 'loading-bar active';
}

export function hideLoading() {
  const bar = document.getElementById('loading-bar');
  if (!bar) return;
  clearTimeout(loadingTimer);
  bar.className = 'loading-bar done';
  loadingTimer = setTimeout(() => {
    bar.className = 'loading-bar fade-out';
    setTimeout(() => { bar.className = 'loading-bar'; }, 300);
  }, 150);
}

// ── Security / formatting helpers ─────────────────────────

/** Escape a string for safe insertion into innerHTML. */
export function escapeHtml(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

export function fmt(n) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function money(n) {
  const abs = Math.abs(n);
  return (n < 0 ? '-$' : '$') + fmt(abs);
}

export function showToast(msg, type = 'info') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    container.setAttribute('role', 'status');
    container.setAttribute('aria-live', 'polite');
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const label = document.createElement('span');
  label.textContent = msg;

  const close = document.createElement('button');
  close.className = 'toast-close';
  close.textContent = '✕';
  close.setAttribute('aria-label', 'Dismiss notification');
  close.onclick = () => { toast.remove(); };

  toast.appendChild(label);
  toast.appendChild(close);
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

export function showConfirm(title, message, options = {}) {
  const { confirmText = 'Confirm', cancelText = 'Cancel', danger = false } = options;
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';

    const modal = document.createElement('div');
    modal.className = 'confirm-modal';

    modal.innerHTML = `
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(message)}</p>
      <div class="confirm-actions">
        <button class="btn btn-outline" id="confirm-cancel">${escapeHtml(cancelText)}</button>
        <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" id="confirm-ok">${escapeHtml(confirmText)}</button>
      </div>`;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const close = (result) => {
      overlay.remove();
      resolve(result);
    };

    overlay.querySelector('#confirm-cancel').onclick = () => close(false);
    overlay.querySelector('#confirm-ok').onclick = () => close(true);
    overlay.onclick = (e) => { if (e.target === overlay) close(false); };
    overlay.querySelector('#confirm-ok').focus();
  });
}

// ── Dark mode ────────────────────────────────────────────

export function getTheme() {
  return localStorage.getItem('sololedger_theme') || 'system';
}

export function setTheme(theme) {
  localStorage.setItem('sololedger_theme', theme);
  applyTheme(theme);
}

function applyTheme(theme) {
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = theme === 'dark' || (theme === 'system' && prefersDark);
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  const toggle = document.getElementById('theme-toggle-icon');
  if (toggle) toggle.textContent = isDark ? '☀️' : '🌙';
}

window.toggleTheme = toggleTheme;

// Initialize theme on load
(function initTheme() {
  const saved = getTheme();
  applyTheme(saved);
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (getTheme() === 'system') applyTheme('system');
  });
})();

// ── File download helper ─────────────────────────────────

export async function apiDownload(path, filename) {
  try {
    const token = getAuthToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`${API_BASE}${path}`, { headers });
    if (!res.ok) throw new Error('Download failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || path.split('/').pop() || 'download';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    showToast('Download failed: ' + e.message, 'error');
  }
}
window.apiDownload = apiDownload;

export function toggleTheme() {
  const current = getTheme();
  const cycle = { system: 'light', light: 'dark', dark: 'system' };
  const next = cycle[current] || 'system';
  setTheme(next);
  const label = { system: 'System', light: 'Light', dark: 'Dark' };
  showToast(`Theme: ${label[next]}`, 'info');
}
