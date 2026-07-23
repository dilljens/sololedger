import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast } from '../api.js';

export async function renderTransactions(content) {
  const d = await apiGet('/dashboard');
  content.innerHTML = `
    <div class="page-header">
      <h1>Transactions</h1>
      <p>Ledger entries</p>
    </div>
    <div class="card">
      <div class="card-row">
        <div class="stat" style="border:none;padding:8px 0;"><div class="label">Revenue</div><div class="value blue">${money(d.gross_revenue)}</div></div>
        <div class="stat" style="border:none;padding:8px 0;"><div class="label">Expenses</div><div class="value red">${money(d.total_expenses)}</div></div>
        <div class="stat" style="border:none;padding:8px 0;"><div class="label">Net</div><div class="value green">${money(d.net_profit)}</div></div>
      </div>
    </div>
    <div class="card">
      <h2>Recent Activity</h2>
      ${d.recent_transactions && d.recent_transactions.length ? `
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Payee</th><th>Account</th><th class="amount">Amount</th></tr></thead>
        <tbody>
          ${d.recent_transactions.map(t => `
            <tr>
              <td>${t.date}</td>
              <td>${t.payee}</td>
              <td><span class="tag ${t.amount > 0 ? 'tag-red' : 'tag-green'}">${t.account}</span></td>
              <td class="amount ${t.amount > 0 ? 'red' : 'green'}">${money(t.amount)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table></div>` : '<p class="text-muted text-center" style="padding:20px;">No transactions yet.</p>'}
    </div>`;
}
