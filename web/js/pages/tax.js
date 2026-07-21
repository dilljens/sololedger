import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast, getAuthToken } from '../api.js';

export async function renderTax(content) {
  const tax = await apiGet('/tax/estimate');
  content.innerHTML = `
    <div class="page-header">
      <h1>Tax Estimate</h1>
      <p>Single-Member LLC — Federal + State</p>
      <div class="meta">
        <span>YTD Net: ${money(tax.ytd_net_profit)}</span>
        <span>Projected: ${money(tax.projected_annual_net)}</span>
      </div>
    </div>
    <div class="card">
      <h2>Federal</h2>
      <table>
        <tr><td>Self-Employment Tax (15.3%)</td><td class="amount">${money(tax.self_employment_tax.total)}</td></tr>
        <tr><td style="padding-left:24px;color:#666;">↳ Deductible half (AGI)</td><td class="amount" style="color:#666;">${money(tax.self_employment_tax.deductible_half)}</td></tr>
        <tr><td>Federal Income Tax</td><td class="amount">${money(tax.federal_income_tax.total)}</td></tr>
        <tr><td style="padding-left:24px;color:#666;">↳ Taxable income</td><td class="amount" style="color:#666;">${money(tax.federal_income_tax.taxable_income)}</td></tr>
      </table>
    </div>
    <div class="card summary-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
        <h2 style="margin:0;">Total Estimated Tax</h2>
        <span class="big-number">${money(tax.total_estimated_tax)}</span>
      </div>
      <div class="summary-row"><span>Already paid</span><span>${money(tax.already_paid)}</span></div>
      <div class="summary-row"><span>Suggested next payment</span><span><strong>${money(tax.suggested_next_payment)}</strong></span></div>
      <div class="summary-row"><span>Effective rate</span><span>${tax.effective_tax_rate.toFixed(1)}%</span></div>
      <div class="summary-row" style="border:none;">
        <span>${tax.note}</span>
        <span><button class="btn btn-outline btn-sm" onclick="apiDownload('/tax/voucher?quarter=${window.getCurrentQuarter()}&amount=${tax.suggested_next_payment}', '1040-ES-${window.getCurrentQuarter()}.pdf')">📄 Voucher PDF</button></span>
      </div>
    </div>
    <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:0.8rem;color:#8d6e00;">
      ⚠️ ${tax.disclaimer || 'This is an estimate for planning purposes only. Consult a qualified CPA.'}
    </div>
    <div style="display:flex;gap:12px;margin-top:8px;">
      <button class="btn btn-primary" onclick="window.open('https://www.irs.gov/payments/direct-pay-with-bank-account','_blank')">💳 Pay $${fmt(tax.suggested_next_payment)} via IRS Direct Pay</button>
      <button class="btn btn-outline" onclick="markTaxPaid(${tax.suggested_next_payment})">✅ Mark as Paid</button>
      <button class="btn btn-outline" onclick="apiDownload('/tax/schedule-c', 'schedule-c.json')">📋 Schedule C Data</button>
    </div>`;
}

export async function renderDeadlines(content) {
  const dl = await apiGet('/tax/deadlines');
  content.innerHTML = `
    <div class="page-header">
      <h1>Tax Deadlines</h1>
      <p>As of ${dl.as_of}</p>
    </div>
    <div class="card">
      <ul class="deadline-list">
        ${dl.deadlines.map(d => `
          <li>
            <span class="dot ${d.status === 'overdue' ? 'dot-red' : d.status === 'upcoming' ? 'dot-yellow' : 'dot-green'}"></span>
            <div style="flex:1;">
              <strong>${d.label}</strong>
              <span style="color:#666;margin-left:12px;">${d.due}</span>
            </div>
            <span style="font-weight:600;color:${d.days_until < 0 ? '#dc3545' : d.days_until <= 30 ? '#ffc107' : '#28a745'};">
              ${d.days_until < 0 ? 'OVERDUE (' + d.days_until + ' days)' : d.days_until === 0 ? 'Due today!' : d.days_until + ' days away'}
            </span>
          </li>
        `).join('')}
      </ul>
    </div>`;
}

window.apiDownload = async function(path, filename) {
  try {
    const token = getAuthToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`/api/v1${path}`, { headers });
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
    alert('Download failed: ' + escapeHtml(e.message));
  }
};
