import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast } from '../api.js';

export async function renderAccounts(content) {
  let accts = { checking: '', income: '', cards: [], balances: {} };
  try { accts = await apiGet('/accounts'); } catch (e) { /* offline */ }

  const cards = accts.cards || [];
  const balances = accts.balances || {};

  content.innerHTML = `
    <div class="page-header">
      <h1>🏦 Accounts</h1>
      <p>All your accounts and balances</p>
    </div>
    <div class="card-row" style="margin-bottom:16px;">
      <div class="stat"><div class="label">Business Checking</div>
        <div class="value blue">${money(balances[accts.checking] || 0)}</div></div>
      ${cards.length > 0 ? cards.map(c => `
        <div class="stat"><div class="label">${c.name} <span class="text-muted-light">${c.type}</span></div>
          <div class="value ${c.balance > 0 ? 'red' : 'green'}">${money(c.balance)}</div>
          ${c.last_four ? `<div class="text-muted-light">•••• ${c.last_four}</div>` : ''}
        </div>`).join('') : `
        <div class="stat empty-state" style="opacity:0.7;border:1px dashed var(--gray-300);border-radius:8px;padding:12px;">
          <div class="icon" style="font-size:1.5rem;">💳</div>
          <div class="label">Cards</div>
          <div style="font-size:0.8rem;">Add cards in <code>config.toml</code></div>
        </div>`}
      <div class="stat"><div class="label">Personal Checking</div>
        <div class="value">${money(balances['Assets:Bank:Personal'] || 0)}</div></div>
      <div class="stat"><div class="label">Reimbursements Owed</div>
        <div class="value green">${money(-(balances['Liabilities:Reimbursement'] || 0))}</div>
        <div class="text-muted-light">Business owes you</div>
      </div>
    </div>

    <div class="card">
      <h2>💸 Transfer Between Accounts</h2>
      <p class="text-muted">Move money — e.g., owner draw from business to personal.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
        <div><label class="text-muted-light">From</label>
          <select id="tx-from" class="border">
            <option value="${accts.checking}">Business Checking</option>
            ${cards.map(c => `<option value="${c.account}">${c.name}</option>`).join('')}
            <option value="Assets:Bank:Personal">Personal Checking</option>
          </select></div>
        <div><label class="text-muted-light">To</label>
          <select id="tx-to" class="border">
            <option value="Assets:Bank:Personal">Personal Checking</option>
            ${cards.map(c => `<option value="${c.account}">${c.name}</option>`).join('')}
            <option value="${accts.checking}">Business Checking</option>
          </select></div>
        <div><label class="text-muted-light">Amount</label>
          <input type="number" id="tx-amount" placeholder="500" class="border"></div>
        <div><label class="text-muted-light">&nbsp;</label>
          <button class="btn btn-primary" onclick="doTransfer()">Transfer</button></div>
      </div>
      <div id="tx-result" style="margin-top:8px;"></div>
    </div>

    <div class="card">
      <h2>🔄 Reimbursement (Business Expense Paid Personally)</h2>
      <p class="text-muted">Bought something for the business on your personal card? Record it here.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
        <div><label class="text-muted-light">Merchant</label>
          <input type="text" id="re-merchant" placeholder="Office Depot" class="border"></div>
        <div><label class="text-muted-light">Amount</label>
          <input type="number" id="re-amount" placeholder="47.23" class="border"></div>
        <div><label class="text-muted-light">Category</label>
          <select id="re-account" class="border">
            <option value="Expenses:Supplies">Supplies</option>
            <option value="Expenses:Software:SaaS">Software/SaaS</option>
            <option value="Expenses:Travel">Travel</option>
            <option value="Expenses:Meals">Meals</option>
            <option value="Expenses:ProfessionalServices">Professional Services</option>
            <option value="Expenses:Miscellaneous">Miscellaneous</option>
          </select></div>
        <div><label class="text-muted-light">&nbsp;</label>
          <button class="btn btn-primary" onclick="doReimburse()">Record</button></div>
      </div>
      <div id="re-result" style="margin-top:8px;"></div>
    </div>

    <div class="card">
      <h2>✂️ Split a Transaction</h2>
      <p class="text-muted">
        One charge had both business and personal items? Split them. E.g., Amazon order: $70 software + $30 personal item on a $100 charge.
      </p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
        <div><label class="text-muted-light">Merchant</label>
          <input type="text" id="sp-merchant" placeholder="Amazon" class="border"></div>
        <div><label class="text-muted-light">Total Charged</label>
          <input type="number" id="sp-total" placeholder="100" class="border"></div>
        <div><label class="text-muted-light">Business Portion</label>
          <input type="number" id="sp-business" placeholder="70" class="border"></div>
        <div><label class="text-muted-light">Category</label>
          <select id="sp-account" class="border">
            <option value="Expenses:Supplies">Supplies</option>
            <option value="Expenses:Software:SaaS">Software/SaaS</option>
            <option value="Expenses:Travel">Travel</option>
            <option value="Expenses:Meals">Meals</option>
            <option value="Expenses:Miscellaneous">Miscellaneous</option>
          </select></div>
        <div><label class="text-muted-light">&nbsp;</label>
          <button class="btn btn-primary" onclick="doSplit()">Split</button></div>
      </div>
      <div id="sp-result" style="margin-top:8px;"></div>
    </div>`;
}

window.doTransfer = async function() {
  const from = document.getElementById('tx-from')?.value;
  const to = document.getElementById('tx-to')?.value;
  const amount = parseFloat(document.getElementById('tx-amount')?.value);
  const resultDiv = document.getElementById('tx-result');
  if (!from || !to || !amount) { resultDiv.innerHTML = '<span class="text-error">Fill in all fields.</span>'; return; }
  try {
    const res = await apiFetch('/transfer', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_account: from, to_account: to, amount }),
    });
    const json = await res.json();
    if (json.success) resultDiv.innerHTML = `<span class="text-success">✅ Transferred $${fmt(amount)}</span>`;
    else resultDiv.innerHTML = `<span class="text-error">⚠ ${escapeHtml(json.error)}</span>`;
  } catch (err) { resultDiv.innerHTML = `<span class="text-error">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.doReimburse = async function() {
  const merchant = document.getElementById('re-merchant')?.value.trim();
  const amount = parseFloat(document.getElementById('re-amount')?.value);
  const account = document.getElementById('re-account')?.value || 'Expenses:Miscellaneous';
  const resultDiv = document.getElementById('re-result');
  if (!merchant || !amount) { resultDiv.innerHTML = '<span class="text-error">Fill in all fields.</span>'; return; }
  try {
    const res = await apiFetch('/reimburse', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant, amount, account }),
    });
    const json = await res.json();
    if (json.success) resultDiv.innerHTML = `<span class="text-success">✅ Recorded: ${merchant} $${fmt(amount)} → ${account}</span>`;
    else resultDiv.innerHTML = `<span class="text-error">⚠ ${escapeHtml(json.error)}</span>`;
  } catch (err) { resultDiv.innerHTML = `<span class="text-error">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.doSplit = async function() {
  const merchant = document.getElementById('sp-merchant')?.value.trim();
  const total = parseFloat(document.getElementById('sp-total')?.value);
  const business = parseFloat(document.getElementById('sp-business')?.value);
  const account = document.getElementById('sp-account')?.value || 'Expenses:Miscellaneous';
  const resultDiv = document.getElementById('sp-result');
  if (!merchant || !total || !business) { resultDiv.innerHTML = '<span class="text-error">Fill in all fields.</span>'; return; }
  const personal = total - business;
  try {
    const res = await apiFetch('/split', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant, total, business, account }),
    });
    const json = await res.json();
    if (json.success) resultDiv.innerHTML = `<span class="text-success">✅ Split: ${merchant} — $${fmt(business)} business, $${fmt(personal)} personal</span>`;
    else resultDiv.innerHTML = `<span class="text-error">⚠ ${escapeHtml(json.error)}</span>`;
  } catch (err) { resultDiv.innerHTML = `<span class="text-error">⚠ ${escapeHtml(err.message)}</span>`; }
};
