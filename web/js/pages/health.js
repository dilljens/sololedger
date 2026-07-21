import { apiFetch, escapeHtml } from '../api.js';

export async function render(content) {
  content.innerHTML = `
      <div class="page-header">
        <h1>🔍 Ledger Health</h1>
        <p>Beancount validation and data integrity</p>
      </div>
      <div class="card" id="health-results">
        <div class="loading"><div class="spinner"></div>Validating ledger...</div>
      </div>`;

  try {
    const res = await apiFetch('/check');
    const json = await res.json();
    const data = json.success ? json.data : { valid: false, error_count: 1, errors: [{ message: 'API error' }] };

    const div = document.getElementById('health-results');
    if (data.valid) {
      div.innerHTML = `
        <div class="text-center" style="padding:30px;">
          <div style="font-size:3rem;margin-bottom:12px;">✅</div>
          <h2 style="color:#2b8a3e;">Ledger is clean</h2>
          <p style="color:#666;">No errors found in your Beancount ledger.</p>
        </div>
        <table>
          <tr><td>Total accounts</td><td class="amount">${Object.keys(data.balances || {}).length}</td></tr>
          <tr><td>Data format</td><td class="amount">Plain-text Beancount</td></tr>
          <tr><td>Backup</td><td class="amount">Git-versioned</td></tr>
        </table>`;
    } else {
      div.innerHTML = `
        <div style="background:#fff5f5;border:1px solid #ffc9c9;border-radius:8px;padding:16px;margin-bottom:16px;">
          <strong style="color:#c92a2a;">⚠ ${data.error_count} error(s) found</strong>
          <p style="font-size:0.85rem;color:#666;margin-top:4px;">
            Fix these issues to keep your ledger in balance.
          </p>
        </div>
        ${data.errors.map(e => `
          <div style="background:#fff;border:1px solid #ffe0e0;border-left:3px solid #c92a2a;border-radius:6px;padding:12px;margin:8px 0;font-size:0.85rem;">
            <strong>${escapeHtml(e.message) || 'Unknown error'}</strong>
            ${e.file ? `<div style="color:#888;margin-top:4px;">${e.file}${e.line ? ':' + e.line : ''}</div>` : ''}
          </div>
        `).join('')}`;
    }
  } catch (err) {
    document.getElementById('health-results').innerHTML =
      '<div class="error">⚠ Failed to validate: ' + escapeHtml(err.message) + '</div>';
  }
}
