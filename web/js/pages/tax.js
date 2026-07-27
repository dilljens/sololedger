import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast, getAuthToken } from '../api.js';

export async function renderTax(content) {
  const tax = await apiGet('/tax/estimate');

  // Handle no-profit / empty-ledger case
  if (!tax.self_employment_tax && !tax.fica && !tax.federal_income_tax) {
    content.innerHTML = `
      <div class="page-header">
        <h1>Tax Estimate</h1>
      </div>
      <div class="card text-center" style="padding:40px;">
        <div style="font-size:3rem;margin-bottom:12px;">💰</div>
        <h2 style="font-weight:600;margin-bottom:8px;">No Tax Due Yet</h2>
        <p style="color:var(--gray-500);">${escapeHtml(tax.note || 'No net profit yet. No tax estimated.')}</p>
      </div>`;
    return;
  }

  const isScorp = tax.entity_type === 'scorp';
  const formLabel = isScorp ? 'S-Corp (1120-S)' : 'Single-Member LLC (Schedule C)';

  let federalSection = '';
  if (isScorp) {
    const fica = tax.fica || {};
    const form1120 = tax.form_1120s || {};
    const fed = tax.federal_income_tax || {};
    federalSection = `
      <div class="card">
        <h2>Payroll (FICA)</h2>
        <table>
          <tr><td>Officer Salary</td><td class="amount">${money(fica.salary || 0)}</td></tr>
          <tr><td>Employee FICA (withheld)</td><td class="amount">${money(fica.employee_total || 0)}</td></tr>
          <tr><td>Employer FICA (expense)</td><td class="amount">${money(fica.employer_total || 0)}</td></tr>
          <tr><td style="font-weight:600;">Total FICA</td><td class="amount" style="font-weight:600;">${money(fica.total_fica || 0)}</td></tr>
        </table>
      </div>
      <div class="card">
        <h2>1120-S Income</h2>
        <table>
          <tr><td>Ordinary Business Income</td><td class="amount">${money(form1120.ordinary_income || 0)}</td></tr>
          <tr><td class="text-muted">↳ Officer salary deduction</td><td class="amount" class="text-muted">${money(form1120.officer_salary || 0)}</td></tr>
          <tr><td class="text-muted">↳ Employer payroll taxes</td><td class="amount" class="text-muted">${money(form1120.employer_payroll_taxes || 0)}</td></tr>
        </table>
      </div>
      <div class="card">
        <h2>Federal Income Tax</h2>
        <table>
          <tr><td>Taxable income (W-2 + K-1)</td><td class="amount">${money(fed.taxable_income || 0)}</td></tr>
          <tr><td>Federal Income Tax</td><td class="amount">${money(fed.total || 0)}</td></tr>
        </table>
      </div>`;
  } else {
    const se = tax.self_employment_tax || {};
    const fed = tax.federal_income_tax || {};
    federalSection = `
      <div class="card">
        <h2>Federal</h2>
        <table>
          <tr><td>Self-Employment Tax (15.3%)</td><td class="amount">${money(se.total || 0)}</td></tr>
          <tr><td class="text-muted">↳ Deductible half (AGI)</td><td class="amount" class="text-muted">${money(se.deductible_half || 0)}</td></tr>
          <tr><td>Federal Income Tax</td><td class="amount">${money(fed.total || 0)}</td></tr>
          <tr><td class="text-muted">↳ Taxable income</td><td class="amount" class="text-muted">${money(fed.taxable_income || 0)}</td></tr>
        </table>
      </div>`;
  }

  const nextPayment = tax.suggested_next_payment || 0;

  const downloadButton = isScorp
    ? `<button class="btn btn-outline" onclick="apiDownload('/tax/form-1120s', 'form-1120s.json')">📋 1120-S Data</button>`
    : `<button class="btn btn-outline" onclick="apiDownload('/tax/schedule-c', 'schedule-c.json')">📋 Schedule C Data</button>`;

  content.innerHTML = `
    <div class="page-header">
      <h1>Tax Estimate</h1>
      <p>${formLabel} — Federal + State</p>
      <div class="meta">
        <span>YTD Net: ${money(tax.ytd_net_profit || 0)}</span>
        <span>Projected: ${money(tax.projected_annual_net || 0)}</span>
      </div>
    </div>
    ${federalSection}
    <div class="card summary-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
        <h2 style="margin:0;">Total Estimated Tax</h2>
        <span class="big-number">${money(tax.total_estimated_tax || 0)}</span>
      </div>
      <div class="summary-row"><span>Already paid</span><span>${money(tax.already_paid || 0)}</span></div>
      <div class="summary-row"><span>Suggested next payment</span><span><strong>${money(nextPayment)}</strong></span></div>
      <div class="summary-row"><span>Effective rate</span><span>${tax.effective_tax_rate != null ? tax.effective_tax_rate.toFixed(1) : '0.0'}%</span></div>
      <div class="summary-row" style="border:none;">
        <span>${tax.note || ''}</span>
        <span><button class="btn btn-outline btn-sm" onclick="apiDownload('/tax/voucher?quarter=${window.getCurrentQuarter()}&amount=${nextPayment}', '1040-ES-${window.getCurrentQuarter()}.pdf')">📄 Voucher PDF</button></span>
      </div>
    </div>
    <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:0.8rem;color:#8d6e00;">
      ⚠️ ${tax.disclaimer || 'This is an estimate for planning purposes only. Consult a qualified CPA.'}
    </div>
    <div style="display:flex;gap:12px;margin-top:8px;">
      <button class="btn btn-primary" onclick="window.open('https://www.irs.gov/payments/direct-pay-with-bank-account','_blank')">💳 Pay $${fmt(nextPayment)} via IRS Direct Pay</button>
      <button class="btn btn-outline" onclick="markTaxPaid(${nextPayment})">✅ Mark as Paid</button>
      ${downloadButton}
    </div>`;
}

export async function renderDeadlines(content) {
  const dl = await apiGet('/tax/deadlines');
  const deadlines = dl.deadlines || [];
  content.innerHTML = `
    <div class="page-header">
      <h1>Tax Deadlines</h1>
      <p>As of ${dl.as_of || 'today'}</p>
    </div>
    <div class="card">
      <ul class="deadline-list">
        ${deadlines.length > 0 ? deadlines.map(d => `
          <li>
            <span class="dot ${d.status === 'overdue' ? 'dot-red' : d.status === 'upcoming' ? 'dot-yellow' : 'dot-green'}"></span>
            <div style="flex:1;">
              <strong>${d.label || ''}</strong>
              <span class="text-muted">${d.due || ''}</span>
            </div>
            <span style="font-weight:600;color:${(d.days_until || 0) < 0 ? '#dc3545' : (d.days_until || 0) <= 30 ? '#ffc107' : '#28a745'};">
              ${(d.days_until || 0) < 0 ? 'OVERDUE (' + (d.days_until || 0) + ' days)' : (d.days_until || 0) === 0 ? 'Due today!' : (d.days_until || 0) + ' days away'}
            </span>
          </li>
        `).join('') : '<li style="color:var(--gray-500);">No deadlines available.</li>'}
      </ul>
    </div>`;
}
