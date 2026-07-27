import { apiGet, money, fmt, escapeHtml } from '../api.js';

export async function renderReports(content) {
  let expenses, pl;
  try {
    const res = await Promise.all([
      apiGet('/reports/expenses'),
      apiGet('/reports/profit-loss'),
    ]);
    expenses = res[0];
    pl = res[1];
  } catch (e) {
    content.innerHTML = `
      <div class="page-header"><h1>Reports</h1><p>Financial summaries and exports</p></div>
      <div class="error text-center" style="padding:40px;">
        <div style="font-size:2rem;margin-bottom:8px;">⚠️</div>
        <p>Failed to load reports.</p>
        <p style="color:var(--gray-500);font-size:0.85rem;">${escapeHtml(e.message)}</p>
        <button class="btn btn-primary mt-3" onclick="loadPage('reports')" style="margin:12px auto 0;">🔄 Retry</button>
      </div>`;
    return;
  }
  content.innerHTML = `
      <div class="page-header">
        <h1>📊 Reports</h1>
        <p>Financial summaries and exports</p>
      </div>
      <div class="card">
        <h2>Profit & Loss — ${pl.year}</h2>
        <table>
          <tr><td>Income</td><td class="amount green">${money(pl.income)}</td></tr>
          <tr><td>Expenses</td><td class="amount red">${money(pl.expenses)}</td></tr>
          <tr style="font-weight:700;"><td>Net Profit</td><td class="amount ${pl.net_profit >= 0 ? 'green' : 'red'}">${money(pl.net_profit)}</td></tr>
        </table>
      </div>
      <div class="card">
        <h2>Expenses by Category — $${fmt(expenses.total)} total</h2>
        ${expenses.categories && expenses.categories.length > 0 ? `
        <table>
          <thead><tr><th>Category</th><th class="amount">Amount</th><th class="amount">Transactions</th></tr></thead>
          <tbody>
            ${expenses.categories.map(c => `
              <tr>
                <td>${(c.category || '').replace('Expenses:', '')}</td>
                <td class="amount">${money(c.amount || 0)}</td>
                <td class="amount">${c.count || 0}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>` : `
        <div class="text-center" style="padding:24px;color:var(--gray-500);">
          <div style="font-size:2rem;margin-bottom:8px;">📊</div>
          <p>No expense transactions yet. Import your bank statements to see expense breakdowns.</p>
        </div>`}
      </div>
      <div style="display:flex;gap:12px;">
        <a href="${'/api/v1/reports/expenses?format=csv'}" target="_blank" class="btn btn-primary">📥 Download CSV</a>
      </div>`;
}

export async function renderRecon(content) {
  let status, dashboard;
  try {
    const res = await Promise.all([
      apiGet('/status'),
      apiGet('/dashboard'),
    ]);
    status = res[0];
    dashboard = res[1];
  } catch (e) {
    content.innerHTML = `
      <div class="page-header"><h1>Reconciliation</h1><p>Match your ledger against bank statements</p></div>
      <div class="error text-center" style="padding:40px;">
        <div style="font-size:2rem;margin-bottom:8px;">⚠️</div>
        <p>Failed to load reconciliation data.</p>
        <p style="color:var(--gray-500);font-size:0.85rem;">${escapeHtml(e.message)}</p>
        <button class="btn btn-primary mt-3" onclick="loadPage('recon')" style="margin:12px auto 0;">🔄 Retry</button>
      </div>`;
    return;
  }
  content.innerHTML = `
      <div class="page-header">
        <h1>🔄 Reconciliation</h1>
        <p>Match your ledger against bank statements</p>
      </div>
      <div class="card">
        <h2>How It Works</h2>
        <ol class="text-muted">
          <li>Download your latest bank statement</li>
          <li>Run <code>llc reconcile start --date YYYY-MM-DD --balance XXXX</code> in your terminal</li>
          <li>Review uncleared items below</li>
          <li>Add missing transactions or fix discrepancies</li>
          <li>Repeat each month</li>
        </ol>
      </div>
      <div class="card">
        <h2>Account Status</h2>
        <table>
          <tr><td>Ledger balance (checking)</td><td class="amount">${money(dashboard.cash)}</td></tr>
          <tr><td>Latest transaction</td><td class="amount">${dashboard.recent_transactions && dashboard.recent_transactions.length ? dashboard.recent_transactions[0].date : '—'}</td></tr>
          <tr><td>Net profit YTD</td><td class="amount green">${money(dashboard.net_profit)}</td></tr>
        </table>
      </div>
      <div class="card">
        <h2>Quick Actions</h2>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          <button class="btn btn-outline btn-sm" onclick="loadPage('transactions')">📋 Review Transactions</button>
          <button class="btn btn-outline btn-sm" onclick="apiDownload('/backup', 'backup.json')">📤 Backup Now</button>
          <button class="btn btn-outline btn-sm" onclick="apiDownload('/reports/expenses?format=csv', 'expenses.csv')">📥 Export CSV</button>
        </div>
      </div>`;
}
