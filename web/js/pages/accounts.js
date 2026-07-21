import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast } from '../api.js';

export async function render(content) {
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
      ${cards.map(c => `
        <div class="stat"><div class="label">${c.name} <span style="font-weight:400;color:#888;">${c.type}</span></div>
          <div class="value ${c.balance > 0 ? 'red' : 'green'}">${money(c.balance)}</div>
          ${c.last_four ? `<div style="font-size:0.75rem;color:#888;">•••• ${c.last_four}</div>` : ''}
        </div>`).join('')}
      <div class="stat"><div class="label">Personal Checking</div>
        <div class="value">${money(balances['Assets:Bank:Personal'] || 0)}</div></div>
      <div class="stat"><div class="label">Reimbursements Owed</div>
        <div class="value green">${money(-(balances['Liabilities:Reimbursement'] || 0))}</div>
        <div style="font-size:0.75rem;color:#888;">Business owes you</div>
      </div>
    </div>

    <div class="card">
      <h2>💸 Transfer Between Accounts</h2>
      <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">Move money — e.g., owner draw from business to personal.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
        <div><label style="font-size:0.75rem;color:#888;display:block;">From</label>
          <select id="tx-from" style="padding:8px;border:1.5px solid #ddd;border-radius:6px;">
            <option value="${accts.checking}">Business Checking</option>
            ${cards.map(c => `<option value="${c.account}">${c.name}</option>`).join('')}
            <option value="Assets:Bank:Personal">Personal Checking</option>
          </select></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">To</label>
          <select id="tx-to" style="padding:8px;border:1.5px solid #ddd;border-radius:6px;">
            <option value="Assets:Bank:Personal">Personal Checking</option>
            ${cards.map(c => `<option value="${c.account}">${c.name}</option>`).join('')}
            <option value="${accts.checking}">Business Checking</option>
          </select></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">Amount</label>
          <input type="number" id="tx-amount" placeholder="500" style="width:100px;padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">&nbsp;</label>
          <button class="btn btn-primary" onclick="doTransfer()">Transfer</button></div>
      </div>
      <div id="tx-result" style="margin-top:8px;"></div>
    </div>

    <div class="card">
      <h2>🔄 Reimbursement (Business Expense Paid Personally)</h2>
      <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">Bought something for the business on your personal card? Record it here.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
        <div><label style="font-size:0.75rem;color:#888;display:block;">Merchant</label>
          <input type="text" id="re-merchant" placeholder="Office Depot" style="padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">Amount</label>
          <input type="number" id="re-amount" placeholder="47.23" style="width:100px;padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">Category</label>
          <select id="re-account" style="padding:8px;border:1.5px solid #ddd;border-radius:6px;">
            <option value="Expenses:Supplies">Supplies</option>
            <option value="Expenses:Software:SaaS">Software/SaaS</option>
            <option value="Expenses:Travel">Travel</option>
            <option value="Expenses:Meals">Meals</option>
            <option value="Expenses:ProfessionalServices">Professional Services</option>
            <option value="Expenses:Miscellaneous">Miscellaneous</option>
          </select></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">&nbsp;</label>
          <button class="btn btn-primary" onclick="doReimburse()">Record</button></div>
      </div>
      <div id="re-result" style="margin-top:8px;"></div>
    </div>

    <div class="card">
      <h2>✂️ Split a Transaction</h2>
      <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
        One charge had both business and personal items? Split them. E.g., Amazon order: $70 software + $30 personal item on a $100 charge.
      </p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
        <div><label style="font-size:0.75rem;color:#888;display:block;">Merchant</label>
          <input type="text" id="sp-merchant" placeholder="Amazon" style="padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">Total Charged</label>
          <input type="number" id="sp-total" placeholder="100" style="width:100px;padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">Business Portion</label>
          <input type="number" id="sp-business" placeholder="70" style="width:100px;padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">Category</label>
          <select id="sp-account" style="padding:8px;border:1.5px solid #ddd;border-radius:6px;">
            <option value="Expenses:Supplies">Supplies</option>
            <option value="Expenses:Software:SaaS">Software/SaaS</option>
            <option value="Expenses:Travel">Travel</option>
            <option value="Expenses:Meals">Meals</option>
            <option value="Expenses:Miscellaneous">Miscellaneous</option>
          </select></div>
        <div><label style="font-size:0.75rem;color:#888;display:block;">&nbsp;</label>
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
  if (!from || !to || !amount) { resultDiv.innerHTML = '<span style="color:#c92a2a;">Fill in all fields.</span>'; return; }
  try {
    const res = await apiFetch('/transfer', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_account: from, to_account: to, amount }),
    });
    const json = await res.json();
    if (json.success) resultDiv.innerHTML = `<span style="color:#2b8a3e;">✅ Transferred $${fmt(amount)}</span>`;
    else resultDiv.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(json.error)}</span>`;
  } catch (err) { resultDiv.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.doReimburse = async function() {
  const merchant = document.getElementById('re-merchant')?.value.trim();
  const amount = parseFloat(document.getElementById('re-amount')?.value);
  const account = document.getElementById('re-account')?.value || 'Expenses:Miscellaneous';
  const resultDiv = document.getElementById('re-result');
  if (!merchant || !amount) { resultDiv.innerHTML = '<span style="color:#c92a2a;">Fill in all fields.</span>'; return; }
  try {
    const res = await apiFetch('/reimburse', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant, amount, account }),
    });
    const json = await res.json();
    if (json.success) resultDiv.innerHTML = `<span style="color:#2b8a3e;">✅ Recorded: ${merchant} $${fmt(amount)} → ${account}</span>`;
    else resultDiv.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(json.error)}</span>`;
  } catch (err) { resultDiv.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.doSplit = async function() {
  const merchant = document.getElementById('sp-merchant')?.value.trim();
  const total = parseFloat(document.getElementById('sp-total')?.value);
  const business = parseFloat(document.getElementById('sp-business')?.value);
  const account = document.getElementById('sp-account')?.value || 'Expenses:Miscellaneous';
  const resultDiv = document.getElementById('sp-result');
  if (!merchant || !total || !business) { resultDiv.innerHTML = '<span style="color:#c92a2a;">Fill in all fields.</span>'; return; }
  const personal = total - business;
  try {
    const res = await apiFetch('/split', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant, total, business, account }),
    });
    const json = await res.json();
    if (json.success) resultDiv.innerHTML = `<span style="color:#2b8a3e;">✅ Split: ${merchant} — $${fmt(business)} business, $${fmt(personal)} personal</span>`;
    else resultDiv.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(json.error)}</span>`;
  } catch (err) { resultDiv.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};
