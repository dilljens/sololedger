import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast } from '../api.js';
import { renderTransactionTable, renderErrorState } from './shared.js';

export async function renderTransactions(content) {
  let d;
  try {
    d = await apiGet('/dashboard');
  } catch (e) {
    content.innerHTML = renderErrorState('Transactions', 'Ledger entries', e.message, 'transactions');
    return;
  }
  d = d || {};
  content.innerHTML = `
    <div class="page-header">
      <h1>Transactions</h1>
      <p>Ledger entries</p>
    </div>
    <div class="card">
      <div class="card-row">
        <div class="stat" style="border:none;padding:8px 0;"><div class="label">Revenue</div><div class="value blue">${money(d.gross_revenue || 0)}</div></div>
        <div class="stat" style="border:none;padding:8px 0;"><div class="label">Expenses</div><div class="value red">${money(d.total_expenses || 0)}</div></div>
        <div class="stat" style="border:none;padding:8px 0;"><div class="label">Net</div><div class="value green">${money(d.net_profit || 0)}</div></div>
      </div>
    </div>
    <div class="card">
      <h2>Recent Activity</h2>
      ${renderTransactionTable(d.recent_transactions, { limit: 15 })}</div>`;
}
