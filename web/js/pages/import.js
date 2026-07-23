import { apiGet, apiPost, apiFetch, escapeHtml, showToast } from '../api.js';

export async function renderImport(content) {
  content.innerHTML = `
      <div class="page-header">
        <h1>📥 Import Transactions</h1>
        <p>Upload bank statements, connect your bank, or import expense files</p>
      </div>

      <!-- Plaid / Auto Bank Sync -->
      <div class="card" id="plaid-card">
        <h2>🏦 Automated Bank Sync</h2>
        <div id="plaid-status">Checking bank connection...</div>
      </div>

      <div class="card">
        <h2>📄 OFX/QFX Bank Statement</h2>
        <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
          Upload an OFX or QFX file from your bank.
        </p>
        <div style="text-align:center;padding:20px;border:2px dashed #ddd;border-radius:12px;">
          <label class="btn btn-primary" style="cursor:pointer;padding:12px 24px;">
            📄 Choose OFX/QFX File
            <input type="file" id="ofx-file" accept=".ofx,.qfx,.ofx.gz" style="display:none;" onchange="handleOfxUpload(this)">
          </label>
          <p class="text-muted text-sm mt-3">.ofx or .qfx files from your bank</p>
        </div>
        <div id="ofx-result" style="margin-top:12px;"></div>
      </div>
      <div class="card">
        <h2>📋 CSV / QBO Import</h2>
        <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
          Upload a CSV or QuickBooks Online (QBO) file from your bank.
        </p>
        <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
          <div style="text-align:center;padding:16px;border:2px dashed #ddd;border-radius:12px;flex:1;min-width:140px;">
            <label class="btn btn-outline" style="cursor:pointer;padding:10px 20px;">
              📊 Upload CSV
              <input type="file" id="csv-file" accept=".csv" style="display:none;" onchange="handleCsvUpload(this)">
            </label>
            <p class="text-muted text-sm mt-2">.csv files</p>
          </div>
          <div style="text-align:center;padding:16px;border:2px dashed #ddd;border-radius:12px;flex:1;min-width:140px;">
            <label class="btn btn-outline" style="cursor:pointer;padding:10px 20px;">
              📋 Upload QBO
              <input type="file" id="qbo-file" accept=".qbo,.csv" style="display:none;" onchange="handleQboUpload(this)">
            </label>
            <p class="text-muted text-sm mt-2">QuickBooks Online</p>
          </div>
        </div>
        <div id="csv-result" style="margin-top:12px;"></div>
        <div id="qbo-result" style="margin-top:8px;"></div>
      </div>`;

  loadPlaidStatus();
}

async function loadPlaidStatus() {
  const statusDiv = document.getElementById('plaid-status');
  if (!statusDiv) return;

  try {
    const res = await apiFetch('/bank/status');
    const json = await res.json();
    if (!json.success) throw new Error(escapeHtml(json.error));

    const data = json.data;
    if (data.connected && data.account_count > 0) {
      statusDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <span style="color:var(--success);font-size:1.2rem;">✅</span>
          <span><strong>Bank connected</strong> — ${data.account_count} account(s)</span>
          <button class="btn btn-primary btn-sm" onclick="syncBank()">🔄 Sync Now</button>
          <button class="btn btn-outline btn-sm" onclick="connectBank()">🔗 Reconnect</button>
        </div>
        ${data.accounts && data.accounts.length ? `
        <div style="margin-top:8px;font-size:0.85rem;color:var(--gray-500);">
          ${data.accounts.map(a => `<span style="display:inline-block;margin-right:12px;">• ${a.name}: $${a.balance.toFixed(2)}</span>`).join('')}
        </div>` : ''}
        <div id="plaid-sync-result" style="margin-top:8px;"></div>`;
    } else if (data.connected) {
      statusDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <span style="color:var(--success);font-size:1.2rem;">✅</span>
          <span><strong>Bank connected</strong></span>
          <button class="btn btn-primary btn-sm" onclick="syncBank()">🔄 Sync Now</button>
        </div>
        <div id="plaid-sync-result" style="margin-top:8px;"></div>`;
    } else {
      statusDiv.innerHTML = `
        <p style="color:var(--gray-500);font-size:0.85rem;margin-bottom:10px;">
          Connect your bank to automatically import and categorize transactions.
        </p>
        <button class="btn btn-primary" onclick="connectBank()">🏦 Connect Your Bank</button>
        <div id="plaid-sync-result" style="margin-top:8px;"></div>`;
    }
  } catch (e) {
    if (escapeHtml(e.message) === 'Authentication required') {
      statusDiv.innerHTML = `<p style="color:var(--gray-500);">Sign in to connect your bank.</p>`;
    } else {
      statusDiv.innerHTML = `<p style="color:var(--gray-500);">Bank sync unavailable. <button class="btn btn-outline btn-sm" onclick="connectBank()">Connect Bank</button></p>`;
    }
  }
}

window.connectBank = async function() {
  try {
    const data = await apiGet('/bank/link-token');
    if (!data.link_token) throw new Error('No link token returned');

    const handler = Plaid.create({
      token: data.link_token,
      onSuccess: async (public_token, metadata) => {
        await apiPost('/bank/exchange-token', {
          public_token: public_token,
          accounts: metadata.accounts ? metadata.accounts.map(a => a.id) : [],
        });
        showToast('✅ Bank connected successfully!', 'success');
        loadPlaidStatus();
      },
      onExit: (err, metadata) => {
        if (err) showToast('⚠ Bank connection failed: ' + err.error_message, 'error');
      },
    });
    handler.open();
  } catch (e) {
    if (escapeHtml(e.message) === 'Authentication required') {
      window.showAuthModal();
    } else {
      alert('Failed to connect bank: ' + escapeHtml(e.message));
    }
  }
};

window.syncBank = async function() {
  const resultDiv = document.getElementById('plaid-sync-result');
  if (!resultDiv) return;
  resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Syncing bank transactions...</div>';
  try {
    const data = await apiPost('/bank/sync', { days: 90, preview: false });
    resultDiv.innerHTML = `<span style="color:var(--success);">✅ Synced ${data.imported} transactions (${data.income_count} income, ${data.expense_count} expenses)</span>`;
  } catch (e) {
    resultDiv.innerHTML = `<span style="color:var(--danger);">⚠ Sync failed: ${escapeHtml(e.message)}</span>`;
  }
};

window.handleOfxUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;
  const div = document.getElementById('ofx-result');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Processing OFX file...</div>';

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');

    const res = await apiFetch('/ofx/import', { method: 'POST', body: formData });
    const json = await res.json();

    if (json.success) {
      const d = json.data;
      div.innerHTML = `
        <div style="background:#d3f9d8;border:1px solid #b2dfdb;border-radius:8px;padding:12px;">
          <strong>✅ ${d.imported} of ${d.total} transactions imported</strong>
          ${d.skipped_duplicates > 0 ? `<br><span style="color:#888;font-size:0.85rem;">${d.skipped_duplicates} duplicates skipped</span>` : ''}
          <p style="margin-top:8px;">
            <button class="btn btn-success btn-sm" onclick="confirmOfxImport()">✓ Confirm & Import</button>
            <button class="btn btn-outline btn-sm" onclick="resetImport()">🔄 Reset</button>
          </p>
        </div>`;
      window._ofxFile = file;
    } else {
      div.innerHTML = `<div class="error">⚠ Import failed: ${escapeHtml(escapeHtml(json.error)) || 'Unknown error'}</div>`;
    }
  } catch (err) {
    div.innerHTML = `<div class="error">⚠ ${escapeHtml(err.message)}</div>`;
  }
};

window.confirmOfxImport = async function() {
  const file = window._ofxFile;
  if (!file) return;
  const div = document.getElementById('ofx-result');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Importing...</div>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'false');
    const res = await apiFetch('/ofx/import', { method: 'POST', body: formData });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:#2b8a3e;">✅ ${json.data.imported} transactions imported to ledger.</span>`;
    } else {
      div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(json.error)}</span>`;
    }
  } catch (err) { div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.resetImport = function() {
  window._ofxFile = null;
  document.getElementById('ofx-result').innerHTML = '';
  document.getElementById('ofx-file').value = '';
};

window.handleCsvUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;
  const div = document.getElementById('csv-result');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Processing CSV...</div>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');
    const res = await apiFetch('/expenses/import', { method: 'POST', body: formData });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:#2b8a3e;">✅ CSV uploaded. ${json.data.imported || 0} transactions found.</span>`;
    } else {
      div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Failed'}</span>`;
    }
  } catch (err) { div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.handleQboUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;
  const div = document.getElementById('qbo-result');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Processing QBO file...</div>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');
    const res = await apiFetch('/import/csv', { method: 'POST', body: formData });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:#2b8a3e;">✅ QBO uploaded. ${json.data.imported || 0} transactions found.</span>`;
    } else {
      div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Failed'}</span>`;
    }
  } catch (err) { div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};
