// SoloLedger API client — authenticated
const API_BASE = '/api/v1';

function getApiKey() {
  return localStorage.getItem('sololedger_api_key');
}

function setApiKey(key) {
  if (key) localStorage.setItem('sololedger_api_key', key);
  else localStorage.removeItem('sololedger_api_key');
}

async function apiFetch(path, options = {}) {
  const key = getApiKey();
  const headers = { ...options.headers };

  if (key) {
    headers['Authorization'] = `Bearer ${key}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401 || res.status === 403) {
    // Auth required but no valid key — show login
    setApiKey(null);
    showLogin();
    throw new Error('Authentication required');
  }

  return res;
}

async function apiGet(path) {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
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
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'API error');
  return json.data;
}

// Check if the API is reachable and if setup is needed
async function apiGetStatus() {
  try {
    const res = await apiFetch('/status');
    if (!res.ok) return { ok: false, needsSetup: true };
    const json = await res.json();
    if (json.success) return { ok: true, needsSetup: false, data: json.data };
    return { ok: true, needsSetup: true };
  } catch {
    return { ok: false, needsSetup: true };
  }
}

function fmt(n) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function money(n) {
  const abs = Math.abs(n);
  return (n < 0 ? '-$' : '$') + fmt(abs);
}
