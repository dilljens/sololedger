// SoloLedger web app — single page application
document.addEventListener('DOMContentLoaded', () => {
  const content = document.getElementById('page-content');
  const navLinks = document.querySelectorAll('[data-page]');

  // Navigation
  navLinks.forEach(link => {
    link.addEventListener('click', async (e) => {
      e.preventDefault();
      navLinks.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      await loadPage(link.dataset.page);
    });
  });

  // Load default page
  loadPage('dashboard');

  // ── Page loader ────────────────────────────────────────────────
  async function loadPage(page) {
    content.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
    try {
      switch (page) {
        case 'dashboard': await renderDashboard(); break;
        case 'invoices': await renderInvoices(); break;
        case 'transactions': await renderTransactions(); break;
        case 'tax': await renderTax(); break;
        case 'deadlines': await renderDeadlines(); break;
        case 'settings': await renderSettings(); break;
      }
    } catch (err) {
      content.innerHTML = `<div class="error">⚠ ${err.message}</div>`;
    }
  }

  // ── Dashboard ──────────────────────────────────────────────────
  async function renderDashboard() {
    const [status, ar] = await Promise.all([
      apiGet('/status'),
      apiGet('/invoices/ar'),
    ]);
    const d = status;
    content.innerHTML = `
      <div class="page-header">
        <h1>Dashboard</h1>
        <p>Your business at a glance</p>
      </div>
      <div class="card-row">
        <div class="stat"><div class="label">Cash</div><div class="value green">${money(d.cash)}</div></div>
        <div class="stat"><div class="label">Revenue YTD</div><div class="value blue">${money(d.gross_revenue)}</div></div>
        <div class="stat"><div class="label">Expenses YTD</div><div class="value red">${money(d.total_expenses)}</div></div>
        <div class="stat"><div class="label">Net Profit YTD</div><div class="value green">${money(d.net_profit)}</div></div>
        <div class="stat"><div class="label">AR Outstanding</div><div class="value blue">${money(ar.total_ar)}</div></div>
      </div>
      <div style="display:flex; gap:20px; margin-top:8px;">
        <div class="card" style="flex:2;">
          <h2>Tax Estimate</h2>
          <div class="card-row">
            <div class="stat" style="border:none;padding:8px 0;">
              <div class="label">Annual Estimated Tax</div>
              <div class="value blue" style="font-size:1.3rem;">${money(d.tax.annual_total_tax)}</div>
            </div>
            <div class="stat" style="border:none;padding:8px 0;">
              <div class="label">Already Paid</div>
              <div class="value green" style="font-size:1.3rem;">${money(d.tax.already_paid)}</div>
            </div>
            <div class="stat" style="border:none;padding:8px 0;">
              <div class="label">Suggested Next</div>
              <div class="value" style="font-size:1.3rem;">${money(d.tax.suggested_payment)}</div>
            </div>
          </div>
          <p style="color:#666;font-size:0.85rem;margin-top:8px;">${d.tax.note}</p>
        </div>
        <div class="card" style="flex:1;">
          <h2>Deadlines</h2>
          <ul class="deadline-list">
            ${d.deadlines.map(dl => `
              <li>
                <span class="dot ${dl.status === 'overdue' ? 'dot-red' : dl.status === 'upcoming' ? 'dot-yellow' : 'dot-green'}"></span>
                <strong>${dl.label}</strong>
                <span style="color:#666;">${dl.due}</span>
                <span style="margin-left:auto;color:${dl.days_until < 0 ? '#dc3545' : '#28a745'};">
                  ${dl.days_until < 0 ? 'OVERDUE' : dl.days_until + ' days'}
                </span>
              </li>
            `).join('')}
          </ul>
        </div>
      </div>
      <div class="card">
        <h2>System</h2>
        <p style="color:#888;">Ledger: ${d.ledger_errors ? `<span class="tag tag-red">${d.ledger_errors} error(s)</span>` : `<span class="tag tag-green">✓ Clean</span>`}</p>
      </div>`;
  }

  // ── Invoices ───────────────────────────────────────────────────
  async function renderInvoices() {
    const [invData, arData] = await Promise.all([
      apiGet('/invoices'),
      apiGet('/invoices/ar'),
    ]);
    content.innerHTML = `
      <div class="page-header">
        <h1>Invoices</h1>
        <p>Accounts Receivable: ${money(arData.total_ar)}</p>
      </div>
      <div class="card-row" style="margin-bottom:20px;">
        <div class="stat"><div class="label">Outstanding</div><div class="value blue">${money(arData.total_ar)}</div></div>
        <div class="stat"><div class="label">Open Invoices</div><div class="value">${arData.invoice_count}</div></div>
        <div class="stat"><div class="label">Overdue</div><div class="value ${arData.overdue_count > 0 ? 'red' : 'green'}">${arData.overdue_count} (${money(arData.estimated_overdue_amount)})</div></div>
      </div>
      <div class="card">
        <h2>All Invoices</h2>
        ${invData.total === 0 ? '<p style="color:#888;text-align:center;padding:20px;">No invoices yet.</p>' : `
        <table>
          <thead><tr><th>Date</th><th>Client</th><th>Description</th><th class="amount">Amount</th></tr></thead>
          <tbody>
            ${invData.invoices.map(i => `
              <tr><td>${i.date}</td><td>${i.client}</td><td>${i.description}</td><td class="amount">${money(i.amount)}</td></tr>
            `).join('')}
          </tbody>
        </table>`}
      </div>`;
  }

  // ── Transactions ───────────────────────────────────────────────
  async function renderTransactions() {
    // Fetch all transactions from the status endpoint as a sample
    const status = await apiGet('/status');
    content.innerHTML = `
      <div class="page-header">
        <h1>Transactions</h1>
        <p>Ledger entries. Run <code>llc transactions</code> in the CLI for full list.</p>
      </div>
      <div class="card">
        <div class="card-row">
          <div class="stat" style="border:none;padding:8px 0;"><div class="label">Revenue</div><div class="value blue">${money(status.gross_revenue)}</div></div>
          <div class="stat" style="border:none;padding:8px 0;"><div class="label">Expenses</div><div class="value red">${money(status.total_expenses)}</div></div>
          <div class="stat" style="border:none;padding:8px 0;"><div class="label">Net</div><div class="value green">${money(status.net_profit)}</div></div>
        </div>
      </div>`;
  }

  // ── Tax Estimate ───────────────────────────────────────────────
  async function renderTax() {
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
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <h2 style="margin:0;">Total Estimated Tax</h2>
          <span class="big-number">${money(tax.total_estimated_tax)}</span>
        </div>
        <div class="summary-row"><span>Already paid</span><span>${money(tax.already_paid)}</span></div>
        <div class="summary-row"><span>Suggested next payment</span><span><strong>${money(tax.suggested_next_payment)}</strong></span></div>
        <div class="summary-row"><span>Effective rate</span><span>${tax.effective_tax_rate.toFixed(1)}%</span></div>
        <div class="summary-row"><span>Note</span><span>${tax.note}</span></div>
      </div>`;
  }

  // ── Deadlines ──────────────────────────────────────────────────
  async function renderDeadlines() {
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

  // ── Settings ───────────────────────────────────────────────────
  async function renderSettings() {
    content.innerHTML = `
      <div class="page-header">
        <h1>Settings</h1>
        <p>System status &amp; configuration</p>
      </div>
      <div class="card">
        <h2>Quick Actions</h2>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          <a href="/api/v1/tax/estimate" target="_blank" class="btn btn-outline">💰 Tax API</a>
          <a href="/api/v1/status" target="_blank" class="btn btn-outline">📊 Status API</a>
          <a href="/docs" target="_blank" class="btn btn-outline">📖 API Docs</a>
          <a href="/api/v1/tax/state-list" target="_blank" class="btn btn-outline">🗺️ States</a>
        </div>
      </div>
      <div class="card">
        <h2>API Endpoints</h2>
        <p style="color:#888;font-size:0.85rem;">All endpoints available at <code>/api/v1/</code>. See <a href="/docs">/docs</a> for full Swagger documentation.</p>
        <table>
          <thead><tr><th>Path</th><th>Method</th></tr></thead>
          <tbody>
            <tr><td>/health</td><td>GET</td></tr>
            <tr><td>/status</td><td>GET</td></tr>
            <tr><td>/invoices</td><td>GET/POST</td></tr>
            <tr><td>/invoices/ar</td><td>GET</td></tr>
            <tr><td>/tax/estimate</td><td>GET</td></tr>
            <tr><td>/tax/deadlines</td><td>GET</td></tr>
            <tr><td>/tax/schedule-c</td><td>GET</td></tr>
            <tr><td>/bank/sync</td><td>POST</td></tr>
            <tr><td>/time/entries</td><td>POST</td></tr>
            <tr><td>/retainers</td><td>GET/POST</td></tr>
            <tr><td>/notify/check</td><td>POST</td></tr>
          </tbody>
        </table>
      </div>`;
  }
});
