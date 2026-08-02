import { apiFetch, apiGet, escapeHtml, showToast } from '../api.js';

const escAttr = (s) => escapeHtml(s).replace(/"/g, '&quot;');

export async function renderCategorize(content) {
  content.innerHTML = `
      <div class="page-header">
        <h1>🏷️ Categorization</h1>
        <p>Review and correct transaction categories</p>
      </div>
      <div class="card">
        <h2>Quick Suggest</h2>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <input type="text" id="cat-merchant" placeholder="Paste a merchant name..."
            class="border">
          <input type="number" id="cat-amount" placeholder="Amount (optional)"
            class="border">
          <button class="btn btn-primary" onclick="suggestCategory()">🔍 Suggest</button>
        </div>
        <div id="cat-suggestion" style="margin-top:12px;"></div>
      </div>
      <div class="card">
        <h2>Uncategorized Transaction Tester</h2>
        <p class="text-muted">
          Try merchants to see how the three-tier cascade categorizes them:
          exact match → pattern rule → embedding similarity.
        </p>
        <div id="cat-examples">
          ${['AMAZON MKTPLACE PMTS', 'UBER RIDE', 'STARBUCKS COFFEE', 'WEWORK COWORKING', 'ADOBE CREATIVE CLOUD'].map(m => `
            <span class="tag tag-blue" style="cursor:pointer;margin:2px;" onclick="document.getElementById('cat-merchant').value='${m}';suggestCategory()">${m}</span>
          `).join('')}
        </div>
      </div>`;
}

window.suggestCategory = async function() {
  const merchant = document.getElementById('cat-merchant').value.trim();
  const amount = document.getElementById('cat-amount').value.trim();
  if (!merchant) return;
  const div = document.getElementById('cat-suggestion');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Analyzing...</div>';

  try {
    const res = await apiFetch('/categories/suggest?merchant=' + encodeURIComponent(merchant));
    const json = await res.json();

    if (json.success) {
      const s = json.data;
      const confLabel = s.confidence === 'high' ? '✅ High' : s.confidence === 'medium' ? '⚠️ Medium' : '❓ Low';

      const ledgerRes = await apiGet('/dashboard');
      const similarTxn = ledgerRes.recent_transactions
        ? ledgerRes.recent_transactions.filter(t => t.payee.toUpperCase().includes(merchant.toUpperCase().slice(0,8)))
        : [];

      div.innerHTML = `
        <div style="background:#f0f9ff;border:1px solid #b2ddff;border-radius:8px;padding:16px;">
          <div style="font-weight:700;font-size:1.1rem;margin-bottom:8px;">Suggested: ${escapeHtml(s.account || 'Unknown')}</div>
          <div class="text-muted">
            <span>Confidence: ${confLabel}</span>
            ${s.count !== undefined ? `<span>Seen ${s.count} time(s)</span>` : ''}
          </div>
          ${similarTxn.length > 0 ? `
            <div class="text-muted">
              <strong>Similar past transactions:</strong>
              ${similarTxn.slice(0,3).map(t => `<span class="tag tag-green" style="margin:2px;">${escapeHtml(t.payee)} → ${escapeHtml(t.account)}</span>`).join('')}
            </div>
          ` : ''}
          <div style="margin-top:12px;display:flex;gap:8px;">
            <input type="text" id="cat-correct" value="${escAttr(s.account || 'Expenses:Miscellaneous')}"
              class="border">
            <button class="btn btn-outline btn-sm" onclick="learnCategory()">✓ Learn</button>
          </div>
        </div>`;
    } else {
      div.innerHTML = '<div class="error">⚠ Could not suggest category</div>';
    }
  } catch (err) {
    div.innerHTML = `<div class="error">⚠ ${escapeHtml(err.message)}</div>`;
  }
};

window.learnCategory = async function() {
  const receiptData = window._receiptData;
  const receiptAccount = document.getElementById('receipt-account')?.value;
  if (receiptData && receiptData.merchant && receiptAccount) {
    await apiFetch('/categories/learn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant: receiptData.merchant, account: receiptAccount, correct: true }),
    });
    showToast('✅ Category learned for ' + receiptData.merchant, 'success');
    return;
  }

  const account = document.getElementById('cat-correct')?.value || '';
  const merchant = document.getElementById('cat-merchant')?.value || '';
  if (!merchant || !account) return;
  try {
    await apiFetch('/categories/learn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant, account, correct: true }),
    });
    document.getElementById('cat-suggestion').innerHTML =
      '<p class="text-success">✅ Learned: ' + escapeHtml(merchant) + ' → ' + escapeHtml(account) + '</p>';
  } catch (err) {
    showToast('Error: ' + escapeHtml(err.message), 'error');
  }
};
