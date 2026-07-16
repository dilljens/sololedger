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

  loadPage('dashboard');

  async function loadPage(page) {
    content.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';
    try {
      switch (page) {
        case 'dashboard': await renderDashboard(); break;
        case 'invoices': await renderInvoices(); break;
        case 'transactions': await renderTransactions(); break;
        case 'tax': await renderTax(); break;
        case 'deadlines': await renderDeadlines(); break;
        case 'capture': await renderCapture(); break;
        case 'recon': await renderRecon(); break;
        case 'settings': await renderSettings(); break;
      }
    } catch (err) {
      content.innerHTML = `<div class="error">⚠ ${err.message}</div>`;
    }
  }

  // ── Dashboard ──────────────────────────────────────────────────
  async function renderDashboard() {
    const d = await apiGet('/dashboard');
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
        <div class="stat"><div class="label">AR Outstanding</div><div class="value blue">${money(d.ar)}</div></div>
      </div>

      <div style="display:flex; gap:20px; margin-top:8px;">
        <div class="card" style="flex:2;">
          <h2>Estimated Tax</h2>
          <div class="card-row">
            <div class="stat" style="border:none;padding:8px 0;">
              <div class="label">Annual Tax</div>
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
          <p style="color:#666;font-size:0.85rem;margin:8px 0;">${d.tax.note}</p>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
            <button class="btn btn-primary btn-sm" onclick="window.open('https://www.irs.gov/payments/direct-pay-with-bank-account','_blank')">
              💳 Pay Now (IRS Direct Pay)
            </button>
            <button class="btn btn-outline btn-sm" onclick="markTaxPaid(${d.tax.suggested_payment})">
              ✅ Mark as Paid
            </button>
            <button class="btn btn-outline btn-sm" onclick="window.open('/api/v1/tax/voucher?quarter=' + getCurrentQuarter() + '&amount=' + ${d.tax.suggested_payment}, '_blank')">
              📄 Print Voucher
            </button>
          </div>
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
        <h2>Recent Transactions</h2>
        ${d.recent_transactions && d.recent_transactions.length ? `
        <table>
          <thead><tr><th>Date</th><th>Payee</th><th>Account</th><th class="amount">Amount</th></tr></thead>
          <tbody>
            ${d.recent_transactions.slice(0,8).map(t => `
              <tr>
                <td>${t.date}</td>
                <td>${t.payee}</td>
                <td><span class="tag ${t.amount > 0 ? 'tag-red' : 'tag-green'}">${t.account.split(':').pop()}</span></td>
                <td class="amount ${t.amount > 0 ? 'red' : 'green'}">${money(t.amount)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>` : '<p style="color:#888;text-align:center;padding:20px;">No transactions yet.</p>'}
      </div>`;
  }

  // ── Invoices ───────────────────────────────────────────────────
  async function renderInvoices() {
    const [invData, arData] = await Promise.all([
      apiGet('/invoices'),
      apiGet('/invoices/ar'),
    ]);
    const hasPdf = invData.invoices && invData.invoices.some(i => i.date);
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
          <thead><tr><th>Date</th><th>Client</th><th>Description</th><th class="amount">Amount</th><th></th></tr></thead>
          <tbody>
            ${invData.invoices.map(i => {
              const invNum = i.date ? 'INV-2026-' + String(invData.invoices.indexOf(i)+1).padStart(3,'0') : '';
              return `<tr>
                <td>${i.date}</td>
                <td>${i.client}</td>
                <td>${i.description}</td>
                <td class="amount">${money(i.amount)}</td>
                <td><a href="/api/v1/invoices/${invNum}/pdf" target="_blank" class="btn btn-outline btn-sm">📄 PDF</a></td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>`}
      </div>`;
  }

  // ── Transactions ───────────────────────────────────────────────
  async function renderTransactions() {
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
        <table>
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
        </table>` : '<p style="color:#888;text-align:center;padding:20px;">No transactions yet.</p>'}
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
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
          <h2 style="margin:0;">Total Estimated Tax</h2>
          <span class="big-number">${money(tax.total_estimated_tax)}</span>
        </div>
        <div class="summary-row"><span>Already paid</span><span>${money(tax.already_paid)}</span></div>
        <div class="summary-row"><span>Suggested next payment</span><span><strong>${money(tax.suggested_next_payment)}</strong></span></div>
        <div class="summary-row"><span>Effective rate</span><span>${tax.effective_tax_rate.toFixed(1)}%</span></div>
        <div class="summary-row" style="border:none;">
          <span>${tax.note}</span>
          <span>
            <a href="/api/v1/tax/voucher?quarter=${getCurrentQuarter()}&amount=${tax.suggested_next_payment}" target="_blank" class="btn btn-outline btn-sm">📄 Voucher PDF</a>
          </span>
        </div>
      </div>
      <div style="display:flex;gap:12px;margin-top:8px;">
        <button class="btn btn-primary" onclick="window.open('https://www.irs.gov/payments/direct-pay-with-bank-account','_blank')">
          💳 Pay $${fmt(tax.suggested_next_payment)} via IRS Direct Pay
        </button>
        <button class="btn btn-outline" onclick="markTaxPaid(${tax.suggested_next_payment})">
          ✅ Mark as Paid
        </button>
        <a href="/api/v1/tax/schedule-c" target="_blank" class="btn btn-outline">📋 Schedule C Data</a>
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
          <a href="/api/v1/dashboard" target="_blank" class="btn btn-outline">📊 Dashboard API</a>
          <a href="/docs" target="_blank" class="btn btn-outline">📖 Swagger Docs</a>
        </div>
      </div>
      <div class="card">
        <h2>Tax Payment Links</h2>
        <p style="color:#888;font-size:0.85rem;">Quick access to official payment portals:</p>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;">
          <a href="https://www.irs.gov/payments/direct-pay-with-bank-account" target="_blank" class="btn btn-primary btn-sm">🇺🇸 IRS Direct Pay</a>
          <a href="https://www.eftps.gov/" target="_blank" class="btn btn-outline btn-sm">🏛 EFTPS</a>
          <a href="https://www.ftb.ca.gov/pay/" target="_blank" class="btn btn-outline btn-sm">🌴 CA FTB</a>
          <a href="https://www.tax.ny.gov/pay/" target="_blank" class="btn btn-outline btn-sm">🗽 NY DTF</a>
        </div>
      </div>
      <div class="card">
        <h2>API Endpoints</h2>
        <p style="color:#888;font-size:0.85rem;">All at <code>/api/v1/</code>. See <a href="/docs">full docs</a>.</p>
        <table>
          <thead><tr><th>Path</th><th>Method</th></tr></thead>
          <tbody>
            <tr><td>/dashboard</td><td>GET</td></tr>
            <tr><td>/status</td><td>GET</td></tr>
            <tr><td>/invoices</td><td>GET/POST</td></tr>
            <tr><td>/invoices/ar</td><td>GET</td></tr>
            <tr><td>/tax/estimate</td><td>GET</td></tr>
            <tr><td>/tax/pay</td><td>POST</td></tr>
            <tr><td>/tax/voucher</td><td>GET</td></tr>
          </tbody>
        </table>
      </div>`;
  }
});

  // ── Capture (receipt camera + OCR + matching) ───────────────────
  async function renderCapture() {
    content.innerHTML = `
      <div class="page-header">
        <h1>📸 Capture Receipt</h1>
        <p>Snap a receipt photo with your camera or upload one from your gallery</p>
      </div>
      <div class="card">
        <h2>1. Choose Receipt</h2>
        <div style="text-align:center;padding:30px;">
          <label class="btn btn-primary" style="font-size:1rem;padding:14px 28px;cursor:pointer;display:inline-flex;align-items:center;gap:8px;">
            📷 Take Photo or Upload
            <input type="file" id="receipt-file" accept="image/*,application/pdf" capture="environment" style="display:none;" onchange="handleReceiptUpload(this)">
          </label>
          <p style="color:#888;font-size:0.85rem;margin-top:12px;">Supports JPG, PNG, PDF receipts</p>
        </div>
      </div>
      <div id="receipt-result" style="display:none;">
        <div class="card">
          <h2>2. Review &amp; Confirm</h2>
          <div id="receipt-preview"></div>
        </div>
        <div class="card" id="receipt-match-section" style="display:none;">
          <h2>🔗 Matching Bank Transaction</h2>
          <div id="receipt-matches"></div>
        </div>
        <div class="card">
          <h2>3. Category</h2>
          <div id="receipt-category"></div>
          <div style="margin-top:12px;display:flex;gap:8px;" id="receipt-actions">
            <button class="btn btn-primary" onclick="confirmReceipt()">✅ Append to Ledger</button>
            <button class="btn btn-outline" onclick="resetCapture()">🔄 Reset</button>
          </div>
        </div>
      </div>
      <div id="receipt-done" style="display:none;">
        <div class="card" style="text-align:center;padding:30px;">
          <h2 style="font-size:1.5rem;">✅ Receipt Recorded</h2>
          <p style="color:#666;margin:8px 0;" id="receipt-done-detail"></p>
          <button class="btn btn-outline" onclick="resetCapture()">📸 Capture Another</button>
        </div>
      </div>`;
  }

  // ── Reconciliation ────────────────────────────────────────────────
  async function renderRecon() {
    const d = await apiGet('/reconciliation');
    content.innerHTML = `
      <div class="page-header">
        <h1>🔄 Bank Reconciliation</h1>
        <p>Match your ledger against your bank statement</p>
      </div>
      <div class="card-row" style="margin-bottom:20px;">
        <div class="stat"><div class="label">Ledger Balance</div><div class="value blue">${money(d.ledger_balance)}</div></div>
        <div class="stat"><div class="label">Uncleared</div><div class="value red">${money(d.uncleared_total)} (${d.uncleared_count} txns)</div></div>
        <div class="stat"><div class="label">Cleared Balance</div><div class="value green">${money(d.cleared_balance)}</div></div>
      </div>
      <div class="card">
        <h2>All Transactions (${d.uncleared_count})</h2>
        <p style="color:#888;font-size:0.85rem;margin-bottom:12px;">View your recent ledger entries. Reconcile against your bank statement manually.</p>
        <table>
          <thead><tr><th>Date</th><th>Payee</th><th>Category</th><th class="amount">Amount</th></tr></thead>
          <tbody>
            ${d.uncleared.slice(0,30).map(t => `
              <tr>
                <td>${t.date}</td>
                <td>${t.payee}</td>
                <td><span class="tag tag-blue">${t.account.split(':').pop()}</span></td>
                <td class="amount ${t.amount < 0 ? 'green' : 'red'}">${money(t.amount)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
        ${d.uncleared_count > 30 ? `<p style="color:#888;text-align:center;margin-top:8px;">... and ${d.uncleared_count - 30} more</p>` : ''}
      </div>
      <div class="card">
        <h2>Quick Links</h2>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          <a href="https://www.irs.gov/payments/direct-pay-with-bank-account" target="_blank" class="btn btn-outline">🇺🇸 IRS Direct Pay</a>
          <button class="btn btn-outline" onclick="loadPage('dashboard')">📊 Dashboard</button>
        </div>
      </div>`;
  }
});

// ── Receipt capture (global so HTML onclick works) ──────────────
window.handleReceiptUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;

  const resultDiv = document.getElementById('receipt-result');
  const previewDiv = document.getElementById('receipt-preview');
  const matchSection = document.getElementById('receipt-match-section');
  const matchesDiv = document.getElementById('receipt-matches');
  const categoryDiv = document.getElementById('receipt-category');
  const doneDiv = document.getElementById('receipt-done');
  const doneDetail = document.getElementById('receipt-done-detail');

  resultDiv.style.display = 'none';
  matchSection.style.display = 'none';
  doneDiv.style.display = 'none';

  previewDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Scanning receipt...</div>';
  resultDiv.style.display = 'block';

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');

    const res = await fetch('/api/v1/receipts/scan', { method: 'POST', body: formData });
    const json = await res.json();
    if (!json.success) throw new Error(json.error || 'Scan failed');
    const data = json.data;

    previewDiv.innerHTML = `
      <table>
        <tr><td style="width:120px;"><strong>Merchant</strong></td><td>${data.merchant || 'Unknown'}</td></tr>
        <tr><td><strong>Date</strong></td><td>${data.date || 'Unknown'}</td></tr>
        <tr><td><strong>Total</strong></td><td><strong>$${fmt(data.total || 0)}</strong></td></tr>
        ${data.line_items && data.line_items.length ? `
        <tr><td><strong>Items</strong></td><td>${data.line_items.slice(0,5).map(i => `<span style="display:block;">· ${i.description}: $${fmt(i.amount)}</span>`).join('')}${data.line_items.length > 5 ? `<span style="color:#888;">...and ${data.line_items.length-5} more</span>` : ''}</td></tr>
        ` : ''}
      </table>
      <p style="color:#888;font-size:0.85rem;margin-top:8px;">${file.name} (${(file.size/1024).toFixed(0)} KB)</p>`;

    // Auto-categorize
    let suggestedAccount = '';
    if (data.merchant) {
      const catRes = await fetch('/api/v1/categories/suggest?merchant=' + encodeURIComponent(data.merchant));
      const catJson = await catRes.json();
      if (catJson.success && catJson.data && catJson.data.account) {
        suggestedAccount = catJson.data.account;
        const conf = catJson.data.confidence;
        const confLabel = conf === 'high' ? '✅' : conf === 'medium' ? '⚠️' : '❓';
        categoryDiv.innerHTML = `
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <span>${confLabel} Suggested: <strong>${suggestedAccount}</strong></span>
            <input type="text" id="receipt-account" value="${suggestedAccount}" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:0.85rem;width:250px;">
            <button class="btn btn-outline btn-sm" onclick="learnCategory()">✓ Learn</button>
          </div>`;
      } else {
        categoryDiv.innerHTML = `
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <span>Category:</span>
            <input type="text" id="receipt-account" value="Expenses:Miscellaneous" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:0.85rem;width:250px;">
          </div>`;
      }
    } else {
      categoryDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <span>Category:</span>
          <input type="text" id="receipt-account" value="Expenses:Miscellaneous" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;font-size:0.85rem;width:250px;">
        </div>`;
    }

    // Try to match against bank transactions
    const total = data.total || 0;
    if (total > 0) {
      const matchRes = await fetch('/api/v1/receipts/match?amount=' + total + '&merchant=' + encodeURIComponent(data.merchant || ''));
      const matchJson = await matchRes.json();
      if (matchJson.success && matchJson.data && matchJson.data.matches && matchJson.data.matches.length > 0) {
        matchSection.style.display = 'block';
        matchesDiv.innerHTML = matchJson.data.matches.slice(0,3).map(m => `
          <label style="display:flex;align-items:center;gap:10px;padding:8px;border:1px solid #ddd;border-radius:6px;margin:4px 0;cursor:pointer;">
            <input type="radio" name="receipt-match" value='${JSON.stringify(m).replace(/'/g, "&#39;")}'>
            <span>${m.date} — <strong>${m.description}</strong> — $${fmt(m.amount)}</span>
            <span class="tag ${m.match_score > 0.95 ? 'tag-green' : 'tag-blue'}">${(m.match_score * 100).toFixed(0)}% match</span>
          </label>
        `).join('');
        matchesDiv.innerHTML += '<p style="color:#888;font-size:0.85rem;margin-top:4px;">Select a match to link this receipt to a bank transaction.</p>';
      }
    }

    window._receiptData = data;
    window._receiptFile = file;

  } catch (err) {
    previewDiv.innerHTML = '<div class="error">⚠ ' + err.message + '</div>';
  }
};

window.confirmReceipt = async function() {
  const data = window._receiptData;
  const file = window._receiptFile;
  if (!data || !data.total) { alert('No receipt data to save.'); return; }

  const account = document.getElementById('receipt-account')?.value || 'Expenses:Miscellaneous';

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'false');
    formData.append('account', account);

    const res = await fetch('/api/v1/receipts/scan', { method: 'POST', body: formData });
    const json = await res.json();
    if (!json.success) throw new Error(json.error || 'Failed');

    document.getElementById('receipt-result').style.display = 'none';
    document.getElementById('receipt-done').style.display = 'block';
    document.getElementById('receipt-done-detail').textContent = `${data.merchant || 'Receipt'} — $${fmt(data.total)} → ${account}`;

    // Learn the category
    if (data.merchant) {
      await fetch('/api/v1/categories/learn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant: data.merchant, account: account }),
      });
    }
  } catch (err) {
    alert('❌ Error: ' + err.message);
  }
};

window.learnCategory = async function() {
  const account = document.getElementById('receipt-account')?.value || '';
  const data = window._receiptData;
  if (!data || !data.merchant || !account) return;
  await fetch('/api/v1/categories/learn', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ merchant: data.merchant, account: account, correct: true }),
  });
  alert('✅ Category learned for ' + data.merchant);
};

window.resetCapture = function() {
  window._receiptData = null;
  window._receiptFile = null;
  const active = document.querySelector('[data-page].active');
  if (active) loadPage(active.dataset.page);
};

// ── Helper: Mark tax as paid ─────────────────────────────────────
async function markTaxPaid(amount) {
  if (!amount || amount <= 0) {
    alert('No tax payment amount to record.');
    return;
  }
  const q = getCurrentQuarter();
  if (!confirm(`Record estimated tax payment of $${fmt(amount)} for ${q}?`)) return;

  try {
    const result = await apiPost('/tax/pay', {
      amount: amount,
      quarter: q,
      year: new Date().getFullYear(),
    });
    alert(`✅ Recorded $${fmt(result.amount)} as paid.\nTotal paid YTD: $${fmt(result.already_paid)}\nRemaining: $${fmt(result.remaining)}`);
    // Reload current page
    const active = document.querySelector('[data-page].active');
    if (active) {
      document.querySelector('#page-content').innerHTML = '<div class="loading"><div class="spinner"></div>Updating...</div>';
      await loadPage(active.dataset.page);
    }
  } catch (err) {
    alert('❌ Error recording payment: ' + err.message);
  }
}

// ── Helper: Get current quarter ─────────────────────────────────
function getCurrentQuarter() {
  const m = new Date().getMonth();
  return 'Q' + (Math.floor(m / 3) + 1);
}
