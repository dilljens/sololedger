/* Shared rendering utilities for SoloLedger pages. */
import { money, escapeHtml } from '../api.js';

/**
 * Render a transaction table HTML string.
 * @param {Array} txns - Array of transaction objects with date, payee, account, amount
 * @param {Object} [opts]
 * @param {number} [opts.limit=15] - Max rows to show
 * @param {string} [opts.emptyMsg] - Message when no transactions
 * @returns {string} HTML string
 */
export function renderTransactionTable(txns, opts = {}) {
  const limit = opts.limit || 15;
  const emptyMsg = opts.emptyMsg || 'No transactions yet.';
  const list = (txns || []).slice(0, limit);

  if (list.length === 0) {
    return `<p class="text-muted text-center" style="padding:20px;">${escapeHtml(emptyMsg)}</p>`;
  }

  return `<div class="table-wrap"><table>
    <thead><tr><th>Date</th><th>Payee</th><th>Account</th><th class="amount">Amount</th></tr></thead>
    <tbody>
      ${list.map(t => {
        const amount = t.amount || 0;
        const account = (t.account || '').split(':').pop();
        return `<tr>
          <td>${t.date || ''}</td>
          <td>${escapeHtml(t.payee || '')}</td>
          <td><span class="tag ${amount > 0 ? 'tag-red' : 'tag-green'}">${escapeHtml(account)}</span></td>
          <td class="amount ${amount > 0 ? 'red' : 'green'}">${money(amount)}</td>
        </tr>`;
      }).join('')}
    </tbody>
  </table></div>`;
}

/**
 * Render an error state with retry button.
 * @param {string} title - Page title for the header
 * @param {string} subtitle - Page subtitle
 * @param {string} message - Error message to display
 * @param {string} retryPage - Page name to reload (for loadPage)
 * @returns {string} HTML string
 */
export function renderErrorState(title, subtitle, message, retryPage) {
  return `
    <div class="page-header"><h1>${escapeHtml(title)}</h1><p>${escapeHtml(subtitle || '')}</p></div>
    <div class="error text-center" style="padding:40px;">
      <div style="font-size:2rem;margin-bottom:8px;">⚠️</div>
      <p>${escapeHtml(message || 'Something went wrong.')}</p>
      <p style="color:var(--gray-500);font-size:0.85rem;">${escapeHtml(message)}</p>
      <button class="btn btn-primary mt-3" onclick="loadPage('${escapeHtml(retryPage || 'dashboard')}')" style="margin:12px auto 0;">🔄 Retry</button>
    </div>`;
}
