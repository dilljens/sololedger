import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast, showConfirm, getAuthToken } from '../api.js';

export async function renderPayroll(content) {
  content.innerHTML = `
    <div class="page-header">
      <h1>Payroll</h1>
      <p>S-Corp Payroll Management</p>
    </div>
    <div class="card">
      <h2>Import Gusto Payroll CSV</h2>
      <p style="color:#666;margin-bottom:12px;">Upload your Gusto payroll export CSV to record pay period journal entries in the ledger.</p>
      <div style="border:2px dashed #ccc;border-radius:8px;padding:24px;text-align:center;">
        <input type="file" id="payroll-csv-input" accept=".csv" style="margin-bottom:12px;">
        <br>
        <label><input type="checkbox" id="payroll-preview-check" checked> Preview only (don't write to ledger)</label>
        <br><br>
        <button class="btn btn-primary" onclick="importPayroll()" style="justify-content:center;margin:0 auto;">📤 Import Payroll CSV</button>
      </div>
      <div id="payroll-results" style="margin-top:16px;"></div>
    </div>
    <div class="card">
      <h2>YTD Payroll Summary</h2>
      <div id="payroll-summary">
        <p style="color:#666;">Loading...</p>
      </div>
    </div>
    <div class="card">
      <h2>Disburse Net Pay</h2>
      <p style="color:#666;margin-bottom:12px;">Record the transfer of net pay from your business account to the owner.</p>
      <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:end;">
        <div>
          <label style="display:block;font-size:0.8rem;color:#666;margin-bottom:4px;">Date</label>
          <input type="date" id="disburse-date" class="input" value="${new Date().toISOString().split('T')[0]}" style="padding:8px 12px;border:1px solid #ccc;border-radius:6px;">
        </div>
        <div>
          <label style="display:block;font-size:0.8rem;color:#666;margin-bottom:4px;">Net Pay Amount</label>
          <input type="number" id="disburse-amount" class="input" placeholder="3461.54" step="0.01" min="0" style="padding:8px 12px;border:1px solid #ccc;border-radius:6px;">
        </div>
        <button class="btn btn-outline" onclick="disbursePayroll()" style="margin-bottom:0;">💰 Record Disbursement</button>
      </div>
      <div id="disburse-results" style="margin-top:12px;"></div>
    </div>`;

  // Load summary
  loadPayrollSummary();
}

async function loadPayrollSummary() {
  const el = document.getElementById('payroll-summary');
  try {
    const summary = await apiGet('/payroll/summary');
    if (summary.entity_type !== 'scorp') {
      el.innerHTML = `<p style="color:#666;">${summary.note || 'Payroll is for S-Corp mode only.'}</p>`;
      return;
    }
    el.innerHTML = `
      <table>
        <tr><td>Total Gross Wages YTD</td><td class="amount">${money(summary.total_gross)}</td></tr>
        <tr><td style="font-weight:600;">Total Employer Taxes YTD</td><td class="amount" style="font-weight:600;">${money(summary.total_employer_taxes)}</td></tr>
        ${summary.employer_breakdown ? `
          <tr><td style="padding-left:24px;color:#666;">↳ Social Security (6.2%)</td><td class="amount" style="color:#666;">${money(summary.employer_breakdown.social_security)}</td></tr>
          <tr><td style="padding-left:24px;color:#666;">↳ Medicare (1.45%)</td><td class="amount" style="color:#666;">${money(summary.employer_breakdown.medicare)}</td></tr>
          <tr><td style="padding-left:24px;color:#666;">↳ FUTA (0.6%)</td><td class="amount" style="color:#666;">${money(summary.employer_breakdown.futa)}</td></tr>
          <tr><td style="padding-left:24px;color:#666;">↳ SUTA</td><td class="amount" style="color:#666;">${money(summary.employer_breakdown.suta)}</td></tr>
        ` : ''}
      </table>`;
  } catch (err) {
    el.innerHTML = `<p style="color:#dc3545;">⚠ Failed to load payroll summary: ${escapeHtml(err.message)}</p>`;
  }
}

window.importPayroll = async function() {
  const fileInput = document.getElementById('payroll-csv-input');
  const preview = document.getElementById('payroll-preview-check').checked;
  const resultsEl = document.getElementById('payroll-results');

  if (!fileInput.files || !fileInput.files[0]) {
    resultsEl.innerHTML = '<p style="color:#dc3545;">⚠ Please select a CSV file first.</p>';
    return;
  }

  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append('file', file);
  formData.append('preview', preview ? 'true' : 'false');

  resultsEl.innerHTML = '<p style="color:#666;">Importing...</p>';

  try {
    const token = getAuthToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch('/api/v1/payroll/import', { method: 'POST', headers, body: formData });
    const data = await res.json();

    if (data.error) {
      resultsEl.innerHTML = `<p style="color:#dc3545;">⚠ ${escapeHtml(data.error)}</p>`;
      return;
    }

    let html = '';
    if (data.imported > 0) {
      html += `<p style="color:#28a745;">✅ ${preview ? 'Parsed' : 'Imported'} ${data.imported} pay period(s)</p>`;
      html += `<table><tr><th>Date</th><th>Employee</th><th class="amount">Gross</th><th class="amount">Net</th></tr>`;
      for (const row of data.rows) {
        if (row.skipped) continue;
        html += `<tr><td>${row.date || ''}</td><td>${escapeHtml(row.employee || '')}</td><td class="amount">${money(row.gross || 0)}</td><td class="amount">${money(row.net || 0)}</td></tr>`;
      }
      html += `</table>`;
      html += `<p>Total gross: ${money(data.total_gross)} | Total net: ${money(data.total_net)} | Employer taxes: ${money(data.total_employer_taxes)}</p>`;
    }
    if (data.errors && data.errors.length > 0) {
      html += `<p style="color:#dc3545;">Errors: ${data.errors.join(', ')}</p>`;
    }
    if (data.imported === 0 && (!data.errors || data.errors.length === 0)) {
      html += '<p style="color:#666;">No valid pay periods found in CSV.</p>';
    }
    resultsEl.innerHTML = html;

    // Reload summary if not preview
    if (!preview) loadPayrollSummary();
  } catch (err) {
    resultsEl.innerHTML = `<p style="color:#dc3545;">⚠ Import failed: ${escapeHtml(err.message)}</p>`;
  }
};

window.disbursePayroll = async function() {
  const date = document.getElementById('disburse-date').value;
  const amount = parseFloat(document.getElementById('disburse-amount').value);
  const resultsEl = document.getElementById('disburse-results');

  if (!date || !amount || amount <= 0) {
    resultsEl.innerHTML = '<p style="color:#dc3545;">⚠ Enter a valid date and amount.</p>';
    return;
  }

  const confirmed = await showConfirm('Record Disbursement', `Record net pay disbursement of $${fmt(amount)} on ${date}?`);
  if (!confirmed) return;

  resultsEl.innerHTML = '<p style="color:#666;">Recording...</p>';

  try {
    const result = await apiPost('/payroll/disburse', { date, amount });
    resultsEl.innerHTML = `<p style="color:#28a745;">✅ Disbursement recorded: $${fmt(result.amount)} on ${result.date}</p>`;
    document.getElementById('disburse-amount').value = '';
    loadPayrollSummary();
  } catch (err) {
    resultsEl.innerHTML = `<p style="color:#dc3545;">⚠ ${escapeHtml(err.message)}</p>`;
  }
};
