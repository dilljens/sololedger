// SoloLedger web app — single page application
document.addEventListener('DOMContentLoaded', async () => {
  const content = document.getElementById('page-content');
  const sidebar = document.querySelector('.sidebar');
  const navLinks = document.querySelectorAll('[data-page]');

  // ── Auth state ──────────────────────────────────────────────
  // No forced login — show UI regardless of auth state.
  // Users authenticate via sidebar "Sign In" when they want.
  updateSidebarAuth();

  // ── Public status (no auth needed) ─────────────────────────
  const status = await apiGetPublicStatus();
  if (status.needsSetup) { showSetup(); return; }

  // Render Google sign-in button if Google auth is configured on the server
  if (status.auth_methods && status.auth_methods.google) {
    updateGoogleClientId();
  }

  // ── Navigation ──────────────────────────────────────────────
  navLinks.forEach(link => {
    link.addEventListener('click', async (e) => {
      e.preventDefault();
      navLinks.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      await loadPage(link.dataset.page);
    });
  });
  loadPage('dashboard');

  // Check onboarding after initial page load
  setTimeout(checkOnboarding, 500);

  window.loadPage = async function(page) {
    content.innerHTML = '<div class="skeleton"><div class="skeleton-line w-1/3 h-6"></div><div class="skeleton-line w-1/2"></div><div class="skeleton-card"><div class="skeleton-line w-1/4 h-4"></div><div class="skeleton-line w-full h-8 mt-3"></div><div class="skeleton-line w-2/3 mt-3"></div></div><div class="skeleton-card"><div class="skeleton-line w-1/4 h-4"></div><div class="skeleton-line w-full h-8 mt-3"></div><div class="skeleton-line w-1/2 mt-3"></div></div></div>';
    try {
      const pages = {
        'dashboard': renderDashboard,
        'accounts': renderAccounts,
        'import': renderImport,
        'invoices': renderInvoices,
        'new-invoice': renderNewInvoice,
        'transactions': renderTransactions,
        'receipts': renderReceipts,
        'categorize': renderCategorize,
        'tax': renderTax,
        'deadlines': renderDeadlines,
        'mileage': renderMileage,
        'health': renderHealth,
        'reports': renderReports,
        'settings': renderSettings,
      };
      if (pages[page]) await pages[page]();
      else content.innerHTML = '<div class="error"><h3>⚠ Page not found</h3></div>';
    } catch (err) {
      if (escapeHtml(err.message) === 'Authentication required') {
        content.innerHTML = `
          <div class="page-header">
            <h1>${page.charAt(0).toUpperCase() + page.slice(1)}</h1>
            <p>Sign in to view this data</p>
          </div>
          <div class="card text-center" style="padding:40px;">
            <div style="font-size:3rem;margin-bottom:12px;">🔐</div>
            <h2 style="font-weight:600;margin-bottom:8px;">Sign In Required</h2>
            <p style="color:var(--gray-500);margin-bottom:16px;">This page requires authentication. Sign in to access your data.</p>
            <button class="btn btn-primary" onclick="showAuthModal()" style="justify-content:center;margin:0 auto;">
              🔑 Sign In
            </button>
          </div>`;
      } else {
        content.innerHTML = `<div class="error"><h3>⚠ Error</h3><p>${escapeHtml(err.message)}</p></div>`;
      }
    }
  }

  // ── Dashboard ───────────────────────────────────────────────
  /* Mini SVG sparkline: trend curve showing three data points */
  function sparkline(v1, v2, v3, color = '#3b82f6') {
    const min = Math.min(v1, v2, v3);
    const max = Math.max(v1, v2, v3);
    const range = max - min || 1;
    const h = 24, w = 48;
    const p1 = `0,${h - ((v1 - min) / range) * h}`;
    const p2 = `${w/2},${h - ((v2 - min) / range) * h}`;
    const p3 = `${w},${h - ((v3 - min) / range) * h}`;
    return `<svg class="sparkline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <polyline points="${p1} ${p2} ${p3}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.3"/>
    </svg>`;
  }

  async function renderDashboard() {
    const [d, attention] = await Promise.all([
      apiGet('/dashboard'),
      apiGet('/attention').catch(() => ({ items: [] })),
    ]);

    // Build attention panel
    let attentionHtml = '';
    if (attention.items && attention.items.length > 0) {
      const severityColors = {
        critical: { bg: 'var(--danger-bg)', border: 'var(--danger)', icon: '🔴' },
        warning: { bg: 'var(--warning-bg)', border: 'var(--warning)', icon: '🟡' },
        info: { bg: 'var(--info-bg)', border: 'var(--info)', icon: 'ℹ️' },
      };
      attentionHtml = `
        <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px;">
          ${attention.items.map(item => {
            const s = severityColors[item.severity] || severityColors.info;
            return `
              <div style="display:flex;align-items:start;gap:10px;padding:12px 16px;
                    border-radius:8px;background:${s.bg};border-left:3px solid ${s.border};font-size:0.85rem;">
                <span style="font-size:1.1rem;">${s.icon}</span>
                <div>
                  <strong>${item.label}</strong>
                  <div style="color:var(--gray-600);margin-top:2px;">${item.detail}</div>
                </div>
              </div>`;
          }).join('')}
        </div>`;
    }

    content.innerHTML = `
      <div class="page-header">
        <h1>Dashboard</h1>
        <p>Your business at a glance</p>
      </div>
      ${attentionHtml}
      <div class="card-row">
        <div class="stat-card">
          ${sparkline(d.cash * 0.95, d.cash * 1.02, d.cash, '#22c55e')}
          <div class="label">Cash</div>
          <div class="value green">${money(d.cash)}</div>
          <span class="delta up">↑ 2.3%</span>
        </div>
        <div class="stat-card">
          ${sparkline(d.gross_revenue * 0.8, d.gross_revenue * 0.95, d.gross_revenue, '#3b82f6')}
          <div class="label">Revenue YTD</div>
          <div class="value blue">${money(d.gross_revenue)}</div>
        </div>
        <div class="stat-card">
          ${sparkline(d.total_expenses * 0.9, d.total_expenses * 1.1, d.total_expenses, '#ef4444')}
          <div class="label">Expenses YTD</div>
          <div class="value red">${money(d.total_expenses)}</div>
          <span class="delta up">↑ ${((d.total_expenses / (d.gross_revenue || 1)) * 100).toFixed(0)}% of revenue</span>
        </div>
        <div class="stat-card">
          ${sparkline(d.net_profit * 0.85, d.net_profit * 0.98, d.net_profit, '#22c55e')}
          <div class="label">Net Profit YTD</div>
          <div class="value green">${money(d.net_profit)}</div>
          <span class="delta up">${((d.net_profit / (d.gross_revenue || 1)) * 100).toFixed(0)}% margin</span>
        </div>
        <div class="stat-card">
          <div class="label">AR Outstanding</div>
          <div class="value blue">${money(d.ar)}</div>
        </div>
      </div>
      <div class="trust-panel">
        <span class="trust-icon">🔒</span>
        <div><strong>Your data is yours — no vendor lock-in.</strong>
        <div class="trust-detail">Plain-text Beancount format · Git-versioned · Local storage · Free and open source forever</div></div>
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
            <button class="btn btn-primary btn-sm" onclick="window.open('https://www.irs.gov/payments/direct-pay-with-bank-account','_blank')">💳 Pay Now (IRS Direct Pay)</button>
            <button class="btn btn-outline btn-sm" onclick="markTaxPaid(${d.tax.suggested_payment})">✅ Mark as Paid</button>
            <button class="btn btn-outline btn-sm" onclick="window.open('/api/v1/tax/voucher?quarter=' + getCurrentQuarter() + '&amount=' + ${d.tax.suggested_payment}, '_blank')">📄 Print Voucher</button>
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
        <div class="table-wrap"><table>
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
        </table></div>` : '<p class="text-muted text-center" style="padding:20px;">No transactions yet.</p>'}
      </div>`;
  }

  // ── Accounts / Transfer / Split ────────────────────────────
  async function renderAccounts() {
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

  // ── Import (OFX + CSV + Plaid) ─────────────────────────────
  async function renderImport() {
    content.innerHTML = `
      <div class="page-header">
        <h1>📥 Import Transactions</h1>
        <p>Upload bank statements, connect your bank, or import expense files</p>
      </div>

      <!-- Plaid / Auto Bank Sync -->
      <div class="card" id="plaid-card">
        <h2>🏦 Automated Bank Sync</h2>
        <div id="plaid-status">Checking bank connection...</div>
      </div>

      <div class="card">
        <h2>📄 OFX/QFX Bank Statement</h2>
        <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
          Upload an OFX or QFX file from your bank.
        </p>
        <div style="text-align:center;padding:20px;border:2px dashed #ddd;border-radius:12px;">
          <label class="btn btn-primary" style="cursor:pointer;padding:12px 24px;">
            📄 Choose OFX/QFX File
            <input type="file" id="ofx-file" accept=".ofx,.qfx,.ofx.gz" style="display:none;" onchange="handleOfxUpload(this)">
          </label>
          <p class="text-muted text-sm mt-3">.ofx or .qfx files from your bank</p>
        </div>
        <div id="ofx-result" style="margin-top:12px;"></div>
      </div>
      <div class="card">
        <h2>📋 CSV / QBO Import</h2>
        <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
          Upload a CSV or QuickBooks Online (QBO) file from your bank.
        </p>
        <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
          <div style="text-align:center;padding:16px;border:2px dashed #ddd;border-radius:12px;flex:1;min-width:140px;">
            <label class="btn btn-outline" style="cursor:pointer;padding:10px 20px;">
              📊 Upload CSV
              <input type="file" id="csv-file" accept=".csv" style="display:none;" onchange="handleCsvUpload(this)">
            </label>
            <p class="text-muted text-sm mt-2">.csv files</p>
          </div>
          <div style="text-align:center;padding:16px;border:2px dashed #ddd;border-radius:12px;flex:1;min-width:140px;">
            <label class="btn btn-outline" style="cursor:pointer;padding:10px 20px;">
              📋 Upload QBO
              <input type="file" id="qbo-file" accept=".qbo,.csv" style="display:none;" onchange="handleQboUpload(this)">
            </label>
            <p class="text-muted text-sm mt-2">QuickBooks Online</p>
          </div>
        </div>
        <div id="csv-result" style="margin-top:12px;"></div>
        <div id="qbo-result" style="margin-top:8px;"></div>
      </div>`;

    // Load Plaid status after render
    loadPlaidStatus();
  }

  async function loadPlaidStatus() {
    const statusDiv = document.getElementById('plaid-status');
    if (!statusDiv) return;

    try {
      const res = await apiFetch('/bank/status');
      const json = await res.json();
      if (!json.success) throw new Error(escapeHtml(json.error));

      const data = json.data;
      if (data.connected && data.account_count > 0) {
        statusDiv.innerHTML = `
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <span style="color:var(--success);font-size:1.2rem;">✅</span>
            <span><strong>Bank connected</strong> — ${data.account_count} account(s)</span>
            <button class="btn btn-primary btn-sm" onclick="syncBank()">🔄 Sync Now</button>
            <button class="btn btn-outline btn-sm" onclick="connectBank()">🔗 Reconnect</button>
          </div>
          ${data.accounts && data.accounts.length ? `
          <div style="margin-top:8px;font-size:0.85rem;color:var(--gray-500);">
            ${data.accounts.map(a => `<span style="display:inline-block;margin-right:12px;">• ${a.name}: $${a.balance.toFixed(2)}</span>`).join('')}
          </div>` : ''}
          <div id="plaid-sync-result" style="margin-top:8px;"></div>`;
      } else if (data.connected) {
        statusDiv.innerHTML = `
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <span style="color:var(--success);font-size:1.2rem;">✅</span>
            <span><strong>Bank connected</strong></span>
            <button class="btn btn-primary btn-sm" onclick="syncBank()">🔄 Sync Now</button>
          </div>
          <div id="plaid-sync-result" style="margin-top:8px;"></div>`;
      } else {
        statusDiv.innerHTML = `
          <p style="color:var(--gray-500);font-size:0.85rem;margin-bottom:10px;">
            Connect your bank to automatically import and categorize transactions.
          </p>
          <button class="btn btn-primary" onclick="connectBank()">🏦 Connect Your Bank</button>
          <div id="plaid-sync-result" style="margin-top:8px;"></div>`;
      }
    } catch (e) {
      if (escapeHtml(e.message) === 'Authentication required') {
        statusDiv.innerHTML = `<p style="color:var(--gray-500);">Sign in to connect your bank.</p>`;
      } else {
        statusDiv.innerHTML = `<p style="color:var(--gray-500);">Bank sync unavailable. <button class="btn btn-outline btn-sm" onclick="connectBank()">Connect Bank</button></p>`;
      }
    }
  }

  window.connectBank = async function() {
    try {
      const data = await apiGet('/bank/link-token');
      if (!data.link_token) throw new Error('No link token returned');

      const handler = Plaid.create({
        token: data.link_token,
        onSuccess: async (public_token, metadata) => {
          await apiPost('/bank/exchange-token', {
            public_token: public_token,
            accounts: metadata.accounts ? metadata.accounts.map(a => a.id) : [],
          });
          showToast('✅ Bank connected successfully!', 'success');
          loadPlaidStatus();
        },
        onExit: (err, metadata) => {
          if (err) showToast('⚠ Bank connection failed: ' + err.error_message, 'error');
        },
      });
      handler.open();
    } catch (e) {
      if (escapeHtml(e.message) === 'Authentication required') {
        showAuthModal();
      } else {
        alert('Failed to connect bank: ' + escapeHtml(e.message));
      }
    }
  };

  window.syncBank = async function() {
    const resultDiv = document.getElementById('plaid-sync-result');
    if (!resultDiv) return;
    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Syncing bank transactions...</div>';
    try {
      const data = await apiPost('/bank/sync', { days: 90, preview: false });
      resultDiv.innerHTML = `<span style="color:var(--success);">✅ Synced ${data.imported} transactions (${data.income_count} income, ${data.expense_count} expenses)</span>`;
    } catch (e) {
      resultDiv.innerHTML = `<span style="color:var(--danger);">⚠ Sync failed: ${escapeHtml(e.message)}</span>`;
    }
  };

  // ── Receipt Browser ──────────────────────────────────────────
  async function renderReceipts() {
    content.innerHTML = `
      <div class="page-header">
        <h1>🧾 Receipts</h1>
        <p>All receipt documents attached to your ledger</p>
      </div>
      <div class="card" id="receipt-list">
        <div class="loading"><div class="spinner"></div>Loading receipts...</div>
      </div>
      <div class="card">
        <h2>📸 New Receipt</h2>
        <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
          Take a photo or upload a PDF receipt. It will be scanned,
          categorized, and permanently attached to your ledger.
        </p>
        <a href="#" onclick="loadPage('capture')" class="btn btn-primary">📸 Capture Receipt</a>
      </div>`;

    // Load receipts list
    try {
      const res = await apiFetch('/receipts/list');
      const json = await res.json();
      const docs = json.success ? json.data.documents || [] : [];

      const listDiv = document.getElementById('receipt-list');
      if (docs.length === 0) {
        listDiv.innerHTML = '<p class="text-muted text-center" style="padding:20px;">No receipt documents attached yet.</p>';
      } else {
        listDiv.innerHTML = `
          <h2>Attached Receipts (${docs.length})</h2>
          <table>
            <thead><tr><th>Date</th><th>Account</th><th>File</th></tr></thead>
            <tbody>
              ${docs.map(d => `
                <tr>
                  <td>${d.date}</td>
                  <td><span class="tag tag-blue">${d.account}</span></td>
                  <td><code style="font-size:0.75rem;">${d.path.split('/').pop()}</code></td>
                </tr>
              `).join('')}
            </tbody>
          </table>`;
      }
    } catch (err) {
      document.getElementById('receipt-list').innerHTML =
        '<div class="error">⚠ Could not load receipts: ' + escapeHtml(err.message) + '</div>';
    }
  }

  // ── New Invoice Form ─────────────────────────────────────────
  async function renderNewInvoice() {
    content.innerHTML = `
      <div class="page-header">
        <h1>➕ New Invoice</h1>
        <p>Create an invoice for a client</p>
      </div>
      <div class="card">
        <div style="max-width:500px;">
          <div style="margin-bottom:16px;">
            <label style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:4px;color:#333;">Client Name</label>
            <input type="text" id="inv-client" placeholder="Acme Corp" style="width:100%;padding:10px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;">
          </div>
          <div style="margin-bottom:16px;">
            <label style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:4px;color:#333;">Description</label>
            <textarea id="inv-desc" placeholder="Q3 2026 Consulting Retainer" rows="2" style="width:100%;padding:10px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;resize:vertical;"></textarea>
          </div>
          <div style="margin-bottom:16px;">
            <label style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:4px;color:#333;">Amount ($)</label>
            <input type="number" id="inv-amount" placeholder="5000" step="0.01" style="width:200px;padding:10px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;">
          </div>
          <div style="margin-bottom:16px;">
            <label style="display:block;font-size:0.85rem;font-weight:600;margin-bottom:4px;color:#333;">Client Email (for Stripe payment link)</label>
            <input type="email" id="inv-email" placeholder="client@acme.com" style="width:100%;padding:10px 12px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;">
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="createInvoice()" style="padding:12px 24px;">📄 Create Invoice</button>
            <label><input type="checkbox" id="inv-pdf" checked> Generate PDF</label>
            <label><input type="checkbox" id="inv-payment"> Create Stripe payment link</label>
          </div>
          <div id="inv-result" style="margin-top:12px;"></div>
        </div>
      </div>`;
  }

  window.createInvoice = async function() {
    const client = document.getElementById('inv-client').value.trim();
    const description = document.getElementById('inv-desc').value.trim();
    const amount = parseFloat(document.getElementById('inv-amount').value);
    const email = document.getElementById('inv-email').value.trim();
    const genPdf = document.getElementById('inv-pdf').checked;
    const genPayment = document.getElementById('inv-payment').checked;
    const resultDiv = document.getElementById('inv-result');

    if (!client || !description || !amount) {
      resultDiv.innerHTML = '<span style="color:#c92a2a;">Please fill in client, description, and amount.</span>';
      return;
    }

    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Creating invoice...</div>';

    try {
      const res = await apiFetch('/invoices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client, description, amount,
          client_email: email || undefined,
          generate_pdf: genPdf,
          payment_link: genPayment,
        }),
      });
      const json = await res.json();
      if (json.success) {
        const d = json.data;
        resultDiv.innerHTML = `
          <div style="background:#d3f9d8;border:1px solid #b2dfdb;border-radius:8px;padding:16px;">
            <strong style="color:#2b8a3e;">✅ Invoice created!</strong>
            <p style="margin-top:8px;">Invoice for ${d.client}: <strong>$${fmt(d.amount)}</strong></p>
            ${d.pdf_url ? `<p><a href="${d.pdf_url}" target="_blank" class="btn btn-outline btn-sm">📄 Download PDF</a></p>` : ''}
            ${d.payment_link ? `<p><a href="${d.payment_link}" target="_blank" class="btn btn-primary btn-sm">💳 Payment Link</a></p>` : ''}
          </div>`;
      } else {
        resultDiv.innerHTML = `<div class="error">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Failed to create invoice'}</div>`;
      }
    } catch (err) {
      resultDiv.innerHTML = `<div class="error">⚠ ${escapeHtml(err.message)}</div>`;
    }
  };

  // ── Ledger Health ────────────────────────────────────────────
  async function renderHealth() {
    content.innerHTML = `
      <div class="page-header">
        <h1>🔍 Ledger Health</h1>
        <p>Beancount validation and data integrity</p>
      </div>
      <div class="card" id="health-results">
        <div class="loading"><div class="spinner"></div>Validating ledger...</div>
      </div>`;

    try {
      const res = await apiFetch('/check');
      const json = await res.json();
      const data = json.success ? json.data : { valid: false, error_count: 1, errors: [{ message: 'API error' }] };

      const div = document.getElementById('health-results');
      if (data.valid) {
        div.innerHTML = `
          <div class="text-center" style="padding:30px;">
            <div style="font-size:3rem;margin-bottom:12px;">✅</div>
            <h2 style="color:#2b8a3e;">Ledger is clean</h2>
            <p style="color:#666;">No errors found in your Beancount ledger.</p>
          </div>
          <table>
            <tr><td>Total accounts</td><td class="amount">${Object.keys(data.balances || {}).length}</td></tr>
            <tr><td>Data format</td><td class="amount">Plain-text Beancount</td></tr>
            <tr><td>Backup</td><td class="amount">Git-versioned</td></tr>
          </table>`;
      } else {
        div.innerHTML = `
          <div style="background:#fff5f5;border:1px solid #ffc9c9;border-radius:8px;padding:16px;margin-bottom:16px;">
            <strong style="color:#c92a2a;">⚠ ${data.error_count} error(s) found</strong>
            <p style="font-size:0.85rem;color:#666;margin-top:4px;">
              Fix these issues to keep your ledger in balance.
            </p>
          </div>
          ${data.errors.map(e => `
            <div style="background:#fff;border:1px solid #ffe0e0;border-left:3px solid #c92a2a;border-radius:6px;padding:12px;margin:8px 0;font-size:0.85rem;">
              <strong>${escapeHtml(e.message) || 'Unknown error'}</strong>
              ${e.file ? `<div style="color:#888;margin-top:4px;">${e.file}${e.line ? ':' + e.line : ''}</div>` : ''}
            </div>
          `).join('')}`;
      }
    } catch (err) {
      document.getElementById('health-results').innerHTML =
        '<div class="error">⚠ Failed to validate: ' + escapeHtml(err.message) + '</div>';
    }
  }

  // ── Invoices ────────────────────────────────────────────────
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
        ${invData.total === 0 ? '<p class="text-muted text-center" style="padding:20px;">No invoices yet.</p>' : `
        <div class="table-wrap"><table>
          <thead><tr><th>Date</th><th>Client</th><th>Description</th><th class="amount">Amount</th><th>Status</th><th></th></tr></thead>
          <tbody>
            ${invData.invoices.map((i, idx) => {
              const invNum = 'INV-' + (i.date ? i.date.slice(0,4) : '2026') + '-' + String(idx+1).padStart(3,'0');
              const paid = i.paid === true;
              return `<tr>
                <td>${i.date}</td>
                <td>${i.client}</td>
                <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${i.description}</td>
                <td class="amount">${money(i.amount)}</td>
                <td>${paid ? '<span class="tag tag-green">Paid</span>' : '<span class="tag tag-red">Unpaid</span>'}</td>
                <td style="display:flex;gap:4px;flex-wrap:wrap;">
                  <button class="btn btn-outline btn-sm" onclick="apiDownload('/invoices/${escapeHtml(invNum)}/pdf', '${escapeHtml(invNum)}.pdf')">📄 PDF</button>
                  ${!paid ? `<button class="btn btn-success btn-sm" onclick="markInvoicePaid('${escapeHtml(invNum)}', ${i.amount})">✅ Pay</button>` : ''}
                  <a href="mailto:?subject=Invoice ${invNum}&body=Hi,%0D%0A%0D%0AInvoice ${invNum} for ${i.description} is attached.%0D%0A%0D%0AAmount due: ${money(i.amount)}%0D%0A%0D%0AThank you!" class="btn btn-outline btn-sm">✉️ Send</a>
                </td>
              </tr>`;
            }).join('')}
          </tbody>
        </table></div>`}
      </div>`;
  }

  // ── Transactions ────────────────────────────────────────────
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

  // ── Tax Estimate ────────────────────────────────────────────
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
          <span><button class="btn btn-outline btn-sm" onclick="apiDownload('/tax/voucher?quarter=${getCurrentQuarter()}&amount=${tax.suggested_next_payment}', '1040-ES-${getCurrentQuarter()}.pdf')">📄 Voucher PDF</button></span>
        </div>
      </div>
      <div style="background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:0.8rem;color:#8d6e00;">
        ⚠️ ${tax.disclaimer || 'This is an estimate for planning purposes only. Consult a qualified CPA.'}
      </div>
      <div style="display:flex;gap:12px;margin-top:8px;">
        <button class="btn btn-primary" onclick="window.open('https://www.irs.gov/payments/direct-pay-with-bank-account','_blank')">💳 Pay $${fmt(tax.suggested_next_payment)} via IRS Direct Pay</button>
        <button class="btn btn-outline" onclick="markTaxPaid(${tax.suggested_next_payment})">✅ Mark as Paid</button>
        <button class="btn btn-outline" onclick="apiDownload('/tax/schedule-c', 'schedule-c.json')">📋 Schedule C Data</button>
      </div>`;
  }

  // ── Deadlines ───────────────────────────────────────────────
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

  // ── Reports ─────────────────────────────────────────────────
  async function renderReports() {
    const [expenses, pl] = await Promise.all([
      apiGet('/reports/expenses'),
      apiGet('/reports/profit-loss'),
    ]);
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
        <table>
          <thead><tr><th>Category</th><th class="amount">Amount</th><th class="amount">Transactions</th></tr></thead>
          <tbody>
            ${expenses.categories.map(c => `
              <tr>
                <td>${c.category.replace('Expenses:', '')}</td>
                <td class="amount">${money(c.amount)}</td>
                <td class="amount">${c.count}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      <div style="display:flex;gap:12px;">
        <a href="${'/api/v1/reports/expenses?format=csv'}" target="_blank" class="btn btn-primary">📥 Download CSV</a>
      </div>`;
  }

  // ── Reconciliation ───────────────────────────────────────────
  async function renderRecon() {
    const [status, dashboard] = await Promise.all([
      apiGet('/status'),
      apiGet('/dashboard'),
    ]);
    content.innerHTML = `
      <div class="page-header">
        <h1>🔄 Reconciliation</h1>
        <p>Match your ledger against bank statements</p>
      </div>
      <div class="card">
        <h2>How It Works</h2>
        <ol style="margin-left:20px;font-size:0.85rem;color:#555;">
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

  // ── Categorization Review ────────────────────────────────────
  async function renderCategorize() {
    content.innerHTML = `
      <div class="page-header">
        <h1>🏷️ Categorization</h1>
        <p>Review and correct transaction categories</p>
      </div>
      <div class="card">
        <h2>Quick Suggest</h2>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <input type="text" id="cat-merchant" placeholder="Paste a merchant name..."
            style="flex:1;min-width:200px;padding:10px 14px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;">
          <input type="number" id="cat-amount" placeholder="Amount (optional)"
            style="width:140px;padding:10px 14px;border:1.5px solid #ddd;border-radius:8px;font-size:0.9rem;">
          <button class="btn btn-primary" onclick="suggestCategory()">🔍 Suggest</button>
        </div>
        <div id="cat-suggestion" style="margin-top:12px;"></div>
      </div>
      <div class="card">
        <h2>Uncategorized Transaction Tester</h2>
        <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
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
      // Try the local categorizer via API
      const res = await apiFetch('/categories/suggest?merchant=' + encodeURIComponent(merchant));
      const json = await res.json();

      if (json.success) {
        const s = json.data;
        const confLabel = s.confidence === 'high' ? '✅ High' : s.confidence === 'medium' ? '⚠️ Medium' : '❓ Low';

        // Also check pattern rules via merchant_map
        const ledgerRes = await apiGet('/dashboard');
        const similarTxn = ledgerRes.recent_transactions
          ? ledgerRes.recent_transactions.filter(t => t.payee.toUpperCase().includes(merchant.toUpperCase().slice(0,8)))
          : [];

        div.innerHTML = `
          <div style="background:#f0f9ff;border:1px solid #b2ddff;border-radius:8px;padding:16px;">
            <div style="font-weight:700;font-size:1.1rem;margin-bottom:8px;">Suggested: ${s.account || 'Unknown'}</div>
            <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:0.85rem;color:#555;">
              <span>Confidence: ${confLabel}</span>
              ${s.count !== undefined ? `<span>Seen ${s.count} time(s)</span>` : ''}
            </div>
            ${similarTxn.length > 0 ? `
              <div style="margin-top:8px;font-size:0.85rem;color:#666;">
                <strong>Similar past transactions:</strong>
                ${similarTxn.slice(0,3).map(t => `<span class="tag tag-green" style="margin:2px;">${t.payee} → ${t.account}</span>`).join('')}
              </div>
            ` : ''}
            <div style="margin-top:12px;display:flex;gap:8px;">
              <input type="text" id="cat-correct" value="${s.account || 'Expenses:Miscellaneous'}"
                style="flex:1;padding:8px 12px;border:1.5px solid #ddd;border-radius:6px;font-size:0.85rem;">
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

  // ── Mileage Tracking ─────────────────────────────────────────
  async function renderMileage() {
    // Try loading trips from API
    let trips = [];
    let report = null;
    try {
      const res = await apiFetch('/mileage/trips?limit=20');
      const json = await res.json();
      if (json.success) trips = json.data.trips || [];
    } catch (e) { /* API may not support mileage yet */ }

    try {
      const res2 = await apiFetch('/mileage/report');
      const json2 = await res2.json();
      if (json2.success) report = json2.data;
    } catch (e) { /* not available */ }

    const totalMiles = trips.reduce((s, t) => s + t.miles, 0);
    const totalDeduction = trips.reduce((s, t) => s + (t.deduction || 0), 0);

    content.innerHTML = `
      <div class="page-header">
        <h1>🚗 Mileage</h1>
        <p>Track business driving for IRS deductions (${new Date().getFullYear()}: $0.70/mi)</p>
      </div>
      ${report ? `
      <div class="card-row" style="margin-bottom:16px;">
        <div class="stat"><div class="label">Total Miles</div><div class="value blue">${report.total_miles.toFixed(0)}</div></div>
        <div class="stat"><div class="label">Deduction</div><div class="value green">$${fmt(report.total_deduction)}</div></div>
        <div class="stat"><div class="label">Trips</div><div class="value">${report.trip_count}</div></div>
        <div class="stat"><div class="label">Rate</div><div class="value">$${report.rate_per_mile.toFixed(2)}/mi</div></div>
      </div>` : ''}
      <div class="card">
        <h2>Log a Trip</h2>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;">
          <div><label style="font-size:0.75rem;color:#888;display:block;">Date</label>
            <input type="date" id="mil-date" value="${new Date().toISOString().slice(0,10)}" style="padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
          <div><label style="font-size:0.75rem;color:#888;display:block;">Miles</label>
            <input type="number" id="mil-miles" placeholder="42" style="width:80px;padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
          <div style="flex:1;min-width:150px;"><label style="font-size:0.75rem;color:#888;display:block;">Purpose</label>
            <input type="text" id="mil-purpose" placeholder="Client meeting" style="width:100%;padding:8px;border:1.5px solid #ddd;border-radius:6px;"></div>
          <div><label style="font-size:0.75rem;color:#888;display:block;">&nbsp;</label>
            <button class="btn btn-primary" onclick="logMileage()">➕ Log Trip</button></div>
        </div>
        <div id="mil-result" style="margin-top:8px;"></div>
      </div>
      <div class="card">
        <h2>Trip Log ${trips.length > 0 ? `(${trips.length} trips, ${totalMiles.toFixed(0)} mi, $${fmt(totalDeduction)} deduction)` : ''}</h2>
        ${trips.length > 0 ? `
        <table>
          <thead><tr><th>Date</th><th>Purpose</th><th>Miles</th><th class="amount">Deduction</th></tr></thead>
          <tbody>
            ${trips.map(t => `
              <tr>
                <td>${t.date}</td>
                <td>${t.purpose}</td>
                <td>${t.miles.toFixed(1)}</td>
                <td class="amount green">$${fmt(t.deduction)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>` : '<p class="text-muted text-center" style="padding:20px;">No trips logged yet. Use the CLI or API to add trips.</p>'}
      </div>`;
  }

  window.logMileage = async function() {
    const date = document.getElementById('mil-date').value;
    const miles = parseFloat(document.getElementById('mil-miles').value);
    const purpose = document.getElementById('mil-purpose').value.trim();
    if (!date || !miles || !purpose) {
      document.getElementById('mil-result').innerHTML = '<span style="color:#c92a2a;">Please fill in all fields.</span>';
      return;
    }
    try {
      const res = await apiFetch('/mileage/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date, miles, purpose, post_to_ledger: false }),
      });
      const json = await res.json();
      if (json.success) {
        document.getElementById('mil-result').innerHTML =
          `<span style="color:#2b8a3e;">✅ Logged: ${purpose} — ${miles} mi ($${(miles * 0.70).toFixed(2)} deduction)</span>`;
        loadPage('mileage');
      } else {
        document.getElementById('mil-result').innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Failed'}</span>`;
      }
    } catch (err) {
      document.getElementById('mil-result').innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`;
    }
  };

  // ── Capture ──────────────────────────────────────────────────
  async function renderCapture() { renderCaptureContent(); }

  // ── Settings ─────────────────────────────────────────────────
  async function renderSettings() {
    const user = getUserInfo();

    let authSection = '';
    if (isAuthenticated()) {
      authSection = `
        <div class="card">
          <h2>🔐 Authentication</h2>
          <div style="display:flex;align-items:center;gap:12px;">
            ${user?.picture ? `<img src="${user.picture}" style="width:36px;height:36px;border-radius:50%;">` : '<div style="width:36px;height:36px;border-radius:50%;background:var(--primary-light);display:flex;align-items:center;justify-content:center;font-size:1.2rem;">👤</div>'}
            <div>
              <div style="font-weight:600;">${user?.name || 'Signed in'}</div>
              <div style="font-size:0.8rem;color:var(--gray-500);">${user?.email || ''}</div>
            </div>
            <button class="btn btn-outline btn-sm" onclick="handleLogout()" style="margin-left:auto;">Sign Out</button>
          </div>
        </div>`;
    }

    const llmKey = getLlmApiKey();
    const maskedLlmKey = llmKey ? llmKey.slice(0, 8) + '••••••••••' : '';
    const llmBackend = getLlmBackend();
    const llmModel = getLlmModel();

    content.innerHTML = `
      <div class="page-header">
        <h1>Settings</h1>
        <p>System status &amp; configuration</p>
      </div>
      ${authSection}

      <!-- Subscription / Billing -->
      <div class="card" id="subscription-card">
        <h2>⭐ Plan &amp; Billing</h2>
        <div id="subscription-loading" class="loading"><div class="spinner"></div>Loading plan info...</div>
        <div id="subscription-content" style="display:none;"></div>
      </div>

      <!-- LLM / AI API Key -->
      <div class="card">
        <h2>🤖 AI / LLM API Key</h2>
        <p style="font-size:0.85rem;color:var(--gray-500);margin-bottom:12px;">
          Used for AI-powered features: smart transaction categorization,
          receipt scanning, and content generation.
          <strong>Not used for authentication.</strong>
        </p>
        ${llmKey ? `<p class="text-muted" style="font-size:0.85rem;margin-bottom:8px;">Current key: <code style="font-size:0.8rem;">${maskedLlmKey}</code></p>` : ''}
        <div style="display:flex;flex-direction:column;gap:8px;">
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <select id="llm-backend" class="form-select" style="width:140px;">
              <option value="openai" ${llmBackend === 'openai' ? 'selected' : ''}>OpenAI</option>
              <option value="anthropic" ${llmBackend === 'anthropic' ? 'selected' : ''}>Anthropic</option>
              <option value="ollama" ${llmBackend === 'ollama' ? 'selected' : ''}>Ollama (local)</option>
            </select>
            <input type="text" id="llm-model" placeholder="Model (e.g. gpt-4o-mini)" value="${llmModel}"
              class="form-input" style="flex:1;min-width:140px;font-family:var(--font-mono);font-size:0.85rem;">
          </div>
          <div style="display:flex;gap:8px;">
            <input type="password" id="llm-api-key" placeholder="sk-..." value="${llmKey}"
              class="form-input" style="flex:1;font-family:var(--font-mono);font-size:0.85rem;">
            <button class="btn btn-primary" onclick="saveLlmConfig()">Save</button>
            ${llmKey ? '<button class="btn btn-outline" onclick="clearLlmConfig()">Remove</button>' : ''}
          </div>
        </div>
      </div>
      <div class="card">
        <h2>🔒 Data Ownership</h2>
        <p style="font-size:0.85rem;color:#555;">
          Your data lives in plain-text Beancount files. It is not locked into any proprietary format.
          You can stop using SoloLedger at any time and your data goes with you — it's just text files.
        </p>
        <p style="font-size:0.85rem;color:#555;margin-top:8px;">
          ✅ Plain text · ✅ Git versioned · ✅ No subscription · ✅ Self-hosted · ✅ Open source (MIT)
        </p>
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
        <h2>📤 Backup</h2>
        <p style="font-size:0.85rem;color:#666;margin-bottom:12px;">
          Commit your latest changes to git. Your ledger is versioned and
          recoverable at any point in history.
        </p>
        <button class="btn btn-primary" onclick="doBackup()">📤 Backup Now</button>
        <div id="backup-result" style="margin-top:8px;"></div>
      </div>
      <div class="card">
        <h2>💸 Tax Payment Links</h2>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;">
          <a href="https://www.irs.gov/payments/direct-pay-with-bank-account" target="_blank" class="btn btn-primary btn-sm">🇺🇸 IRS Direct Pay</a>
          <a href="https://www.eftps.gov/" target="_blank" class="btn btn-outline btn-sm">🏛 EFTPS</a>
          <a href="https://www.ftb.ca.gov/pay/" target="_blank" class="btn btn-outline btn-sm">🌴 CA FTB</a>
          <a href="https://www.tax.ny.gov/pay/" target="_blank" class="btn btn-outline btn-sm">🗽 NY DTF</a>
        </div>
      </div>`;

    // Load subscription info
    if (isAuthenticated()) {
      loadSubscriptionInfo();
    } else {
      document.getElementById('subscription-card').style.display = 'none';
    }
  }

  async function loadSubscriptionInfo() {
    const loadingEl = document.getElementById('subscription-loading');
    const contentEl = document.getElementById('subscription-content');
    if (!loadingEl || !contentEl) return;

    try {
      const [plansResp, subResp] = await Promise.all([
        apiFetch('/subscription/plans'),
        apiFetch('/subscription/status'),
      ]);

      const plansJson = await plansResp.json();
      const subJson = await subResp.json();

      if (!plansJson.success || !subJson.success) {
        loadingEl.textContent = 'Could not load plan info.';
        return;
      }

      const plans = plansJson.data.plans;
      const currentPlan = subJson.data.plan || 'free';
      const subStatus = subJson.data.status || 'active';

      loadingEl.style.display = 'none';
      contentEl.style.display = 'block';

      const planNames = { free: 'Free', professional: 'Professional', business: 'Business' };
      const planEmojis = { free: '🆓', professional: '⭐', business: '💼' };
      const statusBadges = {
        active: '<span class="tag tag-green">Active</span>',
        trialing: '<span class="tag tag-blue">Trial</span>',
        past_due: '<span class="tag tag-red">Past Due</span>',
        canceled: '<span class="tag tag-gray">Canceled</span>',
      };

      let upgradeHtml = '';
      if (currentPlan === 'free') {
        upgradeHtml = `
          <div style="margin-top:12px;">
            <p style="font-size:0.85rem;color:var(--gray-500);margin-bottom:10px;">Upgrade to unlock AI categorization, bank sync, and more:</p>
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
              ${Object.entries(plans).filter(([k]) => k !== 'free').map(([key, plan]) => `
                <div class="card" style="flex:1;min-width:180px;cursor:pointer;text-align:center;padding:16px;border:2px solid var(--gray-200);transition:border-color 0.12s;"
                     onmouseover="this.style.borderColor='var(--primary)'" onmouseout="this.style.borderColor=''"
                     onclick="startUpgrade('${key}')">
                  <div style="font-size:1.5rem;margin-bottom:6px;">${planEmojis[key] || '⭐'}</div>
                  <div style="font-weight:600;">${plan.name}</div>
                  <div style="font-size:1.1rem;font-weight:700;color:var(--primary);margin:4px 0;">
                    $${plan.price_monthly}<span style="font-size:0.8rem;font-weight:400;color:var(--gray-500);">/mo</span>
                  </div>
                  <div style="font-size:0.75rem;color:var(--gray-400);">$${plan.price_annual}/yr (save ${Math.round((1 - plan.price_annual / (plan.price_monthly * 12)) * 100)}%)</div>
                  <div style="margin-top:10px;"><button class="btn btn-primary btn-sm" style="width:100%;justify-content:center;">Upgrade →</button></div>
                </div>
              `).join('')}
            </div>
          </div>`;
      } else {
        upgradeHtml = `
          <div style="margin-top:12px;">
            <button class="btn btn-outline btn-sm" onclick="manageBilling()">💳 Manage Billing</button>
          </div>`;
      }

      contentEl.innerHTML = `
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
          <div style="font-size:2rem;">${planEmojis[currentPlan] || '🆓'}</div>
          <div>
            <div style="font-weight:600;font-size:1.1rem;">${planNames[currentPlan] || 'Free'} Plan</div>
            <div>${statusBadges[subStatus] || '<span class="tag tag-green">Active</span>'}</div>
          </div>
        </div>
        ${upgradeHtml}`;
    } catch (e) {
      if (loadingEl) loadingEl.textContent = 'Plan info unavailable.';
    }
  }

  window.startUpgrade = async function(plan) {
    if (!confirm(`Upgrade to ${plan} plan? You'll be redirected to Stripe.`)) return;
    try {
      const data = await apiPost('/subscription/create-checkout', {
        plan: plan,
        interval: 'month',
        success_url: '/settings?upgraded=true',
        cancel_url: '/settings',
      });
      window.location.href = data.url;
    } catch (e) {
      alert('Failed to start upgrade: ' + escapeHtml(e.message));
    }
  };

  window.manageBilling = async function() {
    try {
      const data = await apiPost('/subscription/portal', {});
      window.location.href = data.url;
    } catch (e) {
      alert('Failed to open billing portal: ' + escapeHtml(e.message));
    }
  };

  /** Download a file from an authenticated API endpoint. */
window.apiDownload = async function(path, filename) {
  try {
    const token = getAuthToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(`/api/v1${path}`, { headers });
    if (!res.ok) throw new Error('Download failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || path.split('/').pop() || 'download';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    alert('Download failed: ' + escapeHtml(e.message));
  }
};

window.markInvoicePaid = async function(invNum, amount) {
    if (!confirm(`Mark invoice ${invNum} as paid for $${fmt(amount)}?`)) return;
    try {
      const data = await apiPost(`/invoices/${encodeURIComponent(invNum)}/pay`, {
        amount: amount,
      });
      showToast(`✅ ${data.invoice} marked as paid — $${fmt(data.amount)}`, 'success');
      loadPage('invoices');
    } catch (e) {
      alert('Failed to mark paid: ' + escapeHtml(e.message));
    }
  };

  // ── Helper: Mark tax as paid ─────────────────────────────────
  window.markTaxPaid = async function(amount) {
    if (!amount || amount <= 0) { alert('No tax payment amount to record.'); return; }
    const q = getCurrentQuarter();
    if (!confirm(`Record estimated tax payment of $${fmt(amount)} for ${q}?`)) return;
    try {
      const result = await apiPost('/tax/pay', { amount, quarter: q, year: new Date().getFullYear() });
      alert(`✅ Recorded $${fmt(result.amount)} as paid.\nTotal paid YTD: $${fmt(result.already_paid)}\nRemaining: $${fmt(result.remaining)}`);
      loadPage('dashboard');
    } catch (err) { alert('❌ Error recording payment: ' + escapeHtml(err.message)); }
  }

  function getCurrentQuarter() {
    const m = new Date().getMonth();
    return 'Q' + (Math.floor(m / 3) + 1);
  }
});

// ── Auth modal ──────────────────────────────────────────────────

let _authMode = 'signin'; // 'signin' or 'signup'

function showAuthModal() {
  _authMode = 'signin';
  const overlay = document.getElementById('auth-modal-overlay');
  if (overlay) overlay.style.display = 'flex';
  // Reset form
  const email = document.getElementById('auth-email');
  const pass = document.getElementById('auth-password');
  const err = document.getElementById('auth-error');
  if (email) email.value = '';
  if (pass) pass.value = '';
  if (err) err.style.display = 'none';
  document.getElementById('auth-modal-title').textContent = 'Sign In';
  document.getElementById('auth-submit-btn').textContent = 'Sign In';
  document.getElementById('auth-toggle-text').textContent = "Don't have an account?";
  document.getElementById('auth-toggle-link').textContent = 'Sign Up';
  if (email) setTimeout(() => email.focus(), 150);
  // Fetch Google client ID if not already set
  updateGoogleClientId();
}

function toggleAuthMode() {
  _authMode = _authMode === 'signin' ? 'signup' : 'signin';
  const title = document.getElementById('auth-modal-title');
  const btn = document.getElementById('auth-submit-btn');
  const toggleText = document.getElementById('auth-toggle-text');
  const toggleLink = document.getElementById('auth-toggle-link');
  const err = document.getElementById('auth-error');
  if (err) err.style.display = 'none';

  if (_authMode === 'signup') {
    title.textContent = 'Sign Up';
    btn.textContent = 'Create Account';
    toggleText.textContent = 'Already have an account?';
    toggleLink.textContent = 'Sign In';
  } else {
    title.textContent = 'Sign In';
    btn.textContent = 'Sign In';
    toggleText.textContent = "Don't have an account?";
    toggleLink.textContent = 'Sign Up';
  }
}

window.submitSignIn = async function() {
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;
  const errDiv = document.getElementById('auth-error');
  errDiv.style.display = 'none';

  if (!email || !password) {
    errDiv.textContent = 'Please fill in both email and password.';
    errDiv.style.display = 'block';
    return;
  }

  const btn = document.getElementById('auth-submit-btn');
  const origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Please wait...';

  try {
    let data;
    if (_authMode === 'signup') {
      if (password.length < 6) {
        errDiv.textContent = 'Password must be at least 6 characters.';
        errDiv.style.display = 'block';
        btn.disabled = false;
        btn.textContent = origText;
        return;
      }
      data = await apiSignUp(email, password, email.split('@')[0]);
    } else {
      data = await apiSignIn(email, password);
    }

    setSessionToken(data.token);
    setUserInfo(data.user);
    updateSidebarAuth();
    closeAuthModal();
    const active = document.querySelector('[data-page].active');
    if (active) await loadPage(active.dataset.page);
    // Check onboarding after sign in
    setTimeout(checkOnboarding, 600);
  } catch (e) {
    errDiv.textContent = escapeHtml(e.message);
    errDiv.style.display = 'block';
    btn.disabled = false;
    btn.textContent = origText;
  }
};

function closeAuthModal(e) {
  if (e && e.target !== e.currentTarget) return;
  const overlay = document.getElementById('auth-modal-overlay');
  if (overlay) overlay.style.display = 'none';
  const err = document.getElementById('auth-error');
  if (err) err.style.display = 'none';
}

// ── Onboarding wizard ─────────────────────────────────────

async function checkOnboarding() {
  if (!isAuthenticated()) return;
  try {
    const data = await apiGet('/onboarding/status');
    if (data.needs_onboarding) showOnboarding();
  } catch { /* ignore */ }
}

let _onboardingStep = 1;

function showOnboarding() {
  const content = document.getElementById('page-content');
  if (!content) return;
  _onboardingStep = 1;
  renderOnboarding();

  window._onboardingNext = function(s) { _onboardingStep = s; renderOnboarding(); };
}

function renderOnboarding() {
  const content = document.getElementById('page-content');
  if (!content) return;
  const step = _onboardingStep;
    if (step === 1) {
      content.innerHTML = `
        <div style="max-width:560px;margin:40px auto;padding:0 16px;">
          <div class="card" style="padding:32px;text-align:center;">
            <div style="font-size:3rem;margin-bottom:12px;">🚀</div>
            <h1 style="font-size:1.3rem;font-weight:700;margin-bottom:8px;">Welcome to SoloLedger!</h1>
            <p style="color:var(--gray-500);margin-bottom:20px;">
              Your ledger is ready. Let's get your first data in — or skip straight to the dashboard.
            </p>
            <div style="display:flex;flex-direction:column;gap:12px;max-width:300px;margin:0 auto;">
              <button class="btn btn-primary btn-lg" onclick="_onboardingNext(2)" style="justify-content:center;">
                🏦 Connect My Bank
              </button>
              <button class="btn btn-outline btn-lg" onclick="_onboardingNext(3)" style="justify-content:center;">
                📤 Import a File
              </button>
              <button class="btn btn-ghost" onclick="finishOnboarding()" style="justify-content:center;color:var(--gray-500);">
                Skip — take me to the dashboard
              </button>
            </div>
            <div style="margin-top:20px;font-size:0.8rem;color:var(--gray-400);">
              Step 1 of 3 — Setup
            </div>
          </div>
        </div>`;
    } else if (step === 2) {
      content.innerHTML = `
        <div style="max-width:560px;margin:40px auto;padding:0 16px;">
          <div class="card" style="padding:32px;text-align:center;">
            <div style="font-size:2.5rem;margin-bottom:12px;">🏦</div>
            <h1 style="font-size:1.3rem;font-weight:700;margin-bottom:8px;">Connect Your Bank</h1>
            <p style="color:var(--gray-500);margin-bottom:20px;">
              Automatically import transactions from your business bank account.
              <strong>Professional plan feature.</strong>
            </p>
            <div id="plaid-onboarding-status">
              <button class="btn btn-primary btn-lg" onclick="connectBank()" style="justify-content:center;">
                🔗 Connect Bank
              </button>
            </div>
            <div style="margin-top:16px;display:flex;gap:12px;justify-content:center;">
              <button class="btn btn-outline" onclick="_onboardingNext(3)">Skip — next step</button>
            </div>
            <div style="margin-top:20px;font-size:0.8rem;color:var(--gray-400);">
              Step 2 of 3
            </div>
          </div>
        </div>`;
    } else if (step === 3) {
      content.innerHTML = `
        <div style="max-width:560px;margin:40px auto;padding:0 16px;">
          <div class="card" style="padding:32px;text-align:center;">
            <div style="font-size:2.5rem;margin-bottom:12px;">📤</div>
            <h1 style="font-size:1.3rem;font-weight:700;margin-bottom:8px;">Import Your First File</h1>
            <p style="color:var(--gray-500);margin-bottom:20px;">
              Upload a bank statement or CSV to populate your ledger right away.
            </p>
            <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-bottom:16px;">
              <label class="btn btn-primary" style="cursor:pointer;padding:12px 24px;">
                📄 Upload OFX/QFX
                <input type="file" accept=".ofx,.qfx,.ofx.gz" style="display:none;"
                  onchange="handleOnboardingOfx(this)">
              </label>
              <label class="btn btn-outline" style="cursor:pointer;padding:12px 24px;">
                📊 Upload CSV
                <input type="file" accept=".csv" style="display:none;"
                  onchange="handleOnboardingCsv(this)">
              </label>
            </div>
            <div id="onboarding-import-result"></div>
            <div style="margin-top:16px;">
              <button class="btn btn-primary" onclick="finishOnboarding()">✅ Done — Go to Dashboard</button>
            </div>
            <div style="margin-top:20px;font-size:0.8rem;color:var(--gray-400);">
              Step 3 of 3
            </div>
          </div>
        </div>`;
    }

  render();
}

async function finishOnboarding() {
  try {
    await apiPost('/onboarding/complete', { skipped_bank: true, skipped_import: true });
  } catch { /* ignore */ }
  const active = document.querySelector('[data-page].active');
  if (active) loadPage(active.dataset.page);
}

window.handleOnboardingOfx = async function(input) {
  const file = input.files[0];
  if (!file) return;
  const div = document.getElementById('onboarding-import-result');
  if (!div) return;
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Importing...</div>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'false');
    const res = await apiFetch('/ofx/import', { method: 'POST', body: formData });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:var(--success);">✅ ${json.data.imported} transactions imported!</span>`;
    } else {
      div.innerHTML = `<span style="color:var(--danger);">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Import failed'}</span>`;
    }
  } catch (e) {
    div.innerHTML = `<span style="color:var(--danger);">⚠ ${escapeHtml(e.message)}</span>`;
  }
};

window.handleOnboardingCsv = async function(input) {
  const file = input.files[0];
  if (!file) return;
  const div = document.getElementById('onboarding-import-result');
  if (!div) return;
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Importing...</div>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'false');
    const res = await apiFetch('/expenses/import', { method: 'POST', body: formData });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:var(--success);">✅ ${json.data.imported} transactions imported!</span>`;
    } else {
      div.innerHTML = `<span style="color:var(--danger);">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Import failed'}</span>`;
    }
  } catch (e) {
    div.innerHTML = `<span style="color:var(--danger);">⚠ ${escapeHtml(e.message)}</span>`;
  }
};

// Google credential callback (called by GIS)
window.handleGoogleCredential = async function(response) {
  const errDiv = document.getElementById('auth-error');
  try {
    const data = await apiSignInWithGoogle(response.credential);
    setSessionToken(data.token);
    setUserInfo(data.user);
    updateSidebarAuth();
    closeAuthModal();
    // Reload current page to show authenticated data
    const active = document.querySelector('[data-page].active');
    if (active) await loadPage(active.dataset.page);
    setTimeout(checkOnboarding, 600);
  } catch (e) {
    errDiv.textContent = escapeHtml(e.message);
    errDiv.style.display = 'block';
  }
};

// ── Mobile drawer ────────────────────────────────────────

window.openMobileDrawer = function() {
  const overlay = document.getElementById('mobile-drawer-overlay');
  if (overlay) overlay.style.display = 'flex';
};

window.closeMobileDrawer = function(e) {
  if (e && e.target !== e.currentTarget) return;
  const overlay = document.getElementById('mobile-drawer-overlay');
  if (overlay) overlay.style.display = 'none';
};

// Open drawer when "More" is tapped in mobile nav
document.addEventListener('click', function(e) {
  const moreBtn = e.target.closest('#mobile-more-btn');
  if (moreBtn) {
    e.preventDefault();
    window.openMobileDrawer();
  }
});

// Handle clicks inside the drawer to navigate and close
document.addEventListener('click', function(e) {
  const item = e.target.closest('.mobile-drawer-item');
  if (item) {
    e.preventDefault();
    const page = item.dataset.page;
    if (page && window.loadPage) {
      window.closeMobileDrawer();
      // Update nav active state
      document.querySelectorAll('[data-page]').forEach(l => l.classList.remove('active'));
      const navLink = document.querySelector(`[data-page="${page}"]`);
      if (navLink) navLink.classList.add('active');
      window.loadPage(page);
    }
  }
});

window.handleLogout = async function() {
  if (!confirm('Sign out?')) return;
  await apiLogout();
  updateSidebarAuth();
  const active = document.querySelector('[data-page].active');
  if (active) await loadPage(active.dataset.page);
};

function updateSidebarAuth() {
  const user = getUserInfo();
  const userInfo = document.getElementById('sidebar-user-info');
  const signinBtn = document.getElementById('sidebar-signin');
  const avatar = document.getElementById('user-avatar');
  const nameSpan = document.getElementById('user-name');

  if (user && isAuthenticated()) {
    userInfo.style.display = 'flex';
    signinBtn.style.display = 'none';
    if (user.picture) avatar.src = user.picture;
    else avatar.style.display = 'none';
    nameSpan.textContent = user.name || user.email || 'User';
  } else {
    userInfo.style.display = 'none';
    signinBtn.style.display = 'flex';
  }
}

function updateGoogleClientId(retries = 5) {
  const container = document.getElementById('google-signin-container');
  const notConfigured = document.getElementById('google-not-configured');
  const divider = document.getElementById('auth-divider-local');
  if (!container) return;

  fetch('/api/v1/auth/google/config')
    .then(r => r.json())
    .then(data => {
      if (!data.success || !data.data.client_id) {
        // Google not configured — hide button + divider
        container.style.display = 'none';
        if (notConfigured) notConfigured.style.display = 'block';
        if (divider) divider.style.display = 'none';
        return;
      }

      const cid = data.data.client_id;

      function render() {
        if (window.google && window.google.accounts) {
          try {
            window.google.accounts.id.initialize({
              client_id: cid,
              callback: window.handleGoogleCredential,
              auto_prompt: false,
            });
            window.google.accounts.id.renderButton(container, {
              type: 'standard',
              shape: 'rectangular',
              theme: 'outline',
              text: 'signin_with',
              size: 'large',
              logo_alignment: 'left',
            });
            container.style.display = '';
            if (notConfigured) notConfigured.style.display = 'none';
            if (divider) divider.style.display = 'flex';
            return true;
          } catch (e) { return false; }
        }
        return false;
      }

      if (!render() && retries > 0) {
        setTimeout(() => updateGoogleClientId(retries - 1), 500);
      }
    })
    .catch(() => {});
}

// ── LLM config handlers ──────────────────────────────────

window.saveLlmConfig = function() {
  const key = document.getElementById('llm-api-key').value.trim();
  const backend = document.getElementById('llm-backend').value;
  const model = document.getElementById('llm-model').value.trim();

  setLlmApiKey(key);
  setLlmBackend(backend);
  setLlmModel(model || (backend === 'openai' ? 'gpt-4o-mini' : backend === 'anthropic' ? 'claude-3-haiku' : 'gemma3:1b'));

  // Also save to server if authenticated
  if (isAuthenticated()) {
    apiSaveLlmConfig({
      api_key: key || undefined,
      backend: backend,
      model: model || undefined,
    }).catch(() => {});
  }

  showToast('AI/LLM settings saved', 'success');
  const active = document.querySelector('[data-page].active');
  if (active) loadPage(active.dataset.page);
};

window.clearLlmConfig = function() {
  if (!confirm('Remove LLM API key?')) return;
  setLlmApiKey(null);
  setLlmBackend('openai');
  setLlmModel('gpt-4o-mini');
  if (isAuthenticated()) {
    apiSaveLlmConfig({ api_key: null, backend: 'openai', model: null }).catch(() => {});
  }
  showToast('AI/LLM settings cleared', 'info');
  const active = document.querySelector('[data-page].active');
  if (active) loadPage(active.dataset.page);
};

// ── First-run setup wizard ──────────────────────────────────────
function showSetup() {
  const content = document.getElementById('page-content');
  const sidebar = document.querySelector('.sidebar');
  if (sidebar) sidebar.style.display = 'none';
  document.querySelector('.main').style.marginLeft = '0';
  content.innerHTML = `
    <div class="flex-row" style="justify-content:center;min-height:80vh;padding:20px;">
      <div style="background:#fff;border-radius:16px;padding:48px;max-width:520px;width:100%;box-shadow:var(--shadow-lg);">
        <div class="text-center" style="margin-bottom:24px;">
          <div style="font-size:2rem;margin-bottom:8px;">🚀</div>
          <h1 style="font-size:1.4rem;font-weight:700;">Welcome to SoloLedger</h1>
          <p style="color:var(--gray-500);">Let's set up your business. This takes 2 minutes.</p>
        </div>
        <form onsubmit="submitSetup(event)">
          <div class="form-group">
            <label class="form-label">Business name</label>
            <input type="text" id="setup-name" value="My LLC" required class="form-input">
          </div>
          <div class="form-group">
            <label class="form-label">Your full name</label>
            <input type="text" id="setup-owner" value="Your Name" required class="form-input">
          </div>
          <div class="form-group">
            <label class="form-label">State</label>
            <select id="setup-state" required class="form-select">
              <option value="WY">Wyoming — $0 income tax, $60/yr fee</option>
              <option value="CA">California — 1-13.3% income tax + $800 min franchise tax</option>
              <option value="TX">Texas — $0 income tax, margin tax only >$2.47M revenue</option>
              <option value="NY">New York — 4-10.9% income tax</option>
              <option value="FL">Florida — $0 income tax, $138.75/yr fee</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">EIN (or SSN)</label>
            <input type="text" id="setup-ein" value="XX-XXXXXXX" class="form-input">
          </div>
          <div class="form-group">
            <label class="form-label">Email</label>
            <input type="email" id="setup-email" placeholder="you@yourllc.com" required class="form-input">
          </div>
          <button type="submit" class="btn btn-primary btn-lg" style="width:100%;justify-content:center;">
            Complete Setup →
          </button>
          <div id="setup-error" class="text-danger text-sm mt-3 hidden"></div>
        </form>
      </div>
    </div>`;
}

window.submitSetup = async function(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  const err = document.getElementById('setup-error');
  btn.disabled = true;
  btn.textContent = 'Setting up...';
  try {
    await apiPost('/setup', {
      name: document.getElementById('setup-name').value.trim(),
      owner: document.getElementById('setup-owner').value.trim(),
      state: document.getElementById('setup-state').value,
      ein: document.getElementById('setup-ein').value.trim(),
      email: document.getElementById('setup-email').value.trim(),
    });
    location.reload();
  } catch (e) {
    err.textContent = 'Setup failed: ' + escapeHtml(e.message);
    err.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Complete Setup →';
  }
};

// ── Receipt capture ─────────────────────────────────────────────
function renderCaptureContent() {
  const content = document.getElementById('page-content');
  content.innerHTML = `
    <div class="page-header">
      <h1>📸 Capture Receipt</h1>
      <p>Snap a receipt photo with your camera or upload one from your gallery</p>
    </div>
    <div class="card">
      <h2>1. Choose Receipt</h2>
      <div class="text-center" style="padding:30px;">
        <label class="btn btn-primary" style="font-size:1rem;padding:14px 28px;cursor:pointer;display:inline-flex;align-items:center;gap:8px;">
          📷 Take Photo or Upload
          <input type="file" id="receipt-file" accept="image/*,application/pdf" capture="environment" style="display:none;" onchange="handleReceiptUpload(this)">
        </label>
        <p class="text-muted text-sm mt-3">Supports JPG, PNG, PDF receipts</p>
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
      <div class="card" class="text-center" style="padding:30px;">
        <h2 style="font-size:1.5rem;">✅ Receipt Recorded</h2>
        <p style="color:#666;margin:8px 0;" id="receipt-done-detail"></p>
        <button class="btn btn-outline" onclick="resetCapture()">📸 Capture Another</button>
      </div>
    </div>`;
}

window._receiptBusy = false;

window.handleReceiptUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;
  if (window._receiptBusy) {
    showToast('Already processing a receipt, please wait...', 'warning');
    input.value = '';
    return;
  }
  window._receiptBusy = true;

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
    const res = await apiFetch('/receipts/scan', { method: 'POST', body: formData });
    const json = await res.json();
    if (!json.success) throw new Error(escapeHtml(escapeHtml(json.error)) || 'Scan failed');
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
      <p class="text-muted text-sm mt-3">${file.name} (${(file.size/1024).toFixed(0)} KB)</p>`;

    let suggestedAccount = '';
    if (data.merchant) {
      const catRes = await apiFetch('/categories/suggest?merchant=' + encodeURIComponent(data.merchant));
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

    const total = data.total || 0;
    if (total > 0) {
      const matchRes = await apiFetch('/receipts/match?amount=' + total + '&merchant=' + encodeURIComponent(data.merchant || ''));
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
      }
    }

    window._receiptData = data;
    window._receiptFile = file;
    window._receiptBusy = false;
  } catch (err) {
    previewDiv.innerHTML = '<div class="error">⚠ ' + escapeHtml(err.message) + '</div>';
    window._receiptBusy = false;
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
    const res = await apiFetch('/receipts/scan', { method: 'POST', body: formData });
    const json = await res.json();
    if (!json.success) throw new Error(escapeHtml(json.error) || 'Failed');
    document.getElementById('receipt-result').style.display = 'none';
    document.getElementById('receipt-done').style.display = 'block';
    document.getElementById('receipt-done-detail').textContent = `${data.merchant || 'Receipt'} — $${fmt(data.total)} → ${account}`;
    if (data.merchant) {
      await apiFetch('/categories/learn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ merchant: data.merchant, account, correct: true }),
      });
    }
    window._receiptBusy = false;
  } catch (err) { alert('❌ Error: ' + escapeHtml(err.message)); window._receiptBusy = false; }
};

// Single learnCategory handles both categorization page and receipt page
window.learnCategory = async function() {
  // Try receipt page first
  const receiptData = window._receiptData;
  const receiptAccount = document.getElementById('receipt-account')?.value;
  if (receiptData && receiptData.merchant && receiptAccount) {
    await apiFetch('/categories/learn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ merchant: receiptData.merchant, account: receiptAccount, correct: true }),
    });
    alert('✅ Category learned for ' + receiptData.merchant);
    return;
  }

  // Fall back to categorization page
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
      '<p style="color:#2b8a3e;">✅ Learned: ' + escapeHtml(merchant) + ' → ' + escapeHtml(account) + '</p>';
  } catch (err) {
    alert('❌ Error: ' + escapeHtml(err.message));
  }
};

window.resetCapture = function() {
  window._receiptData = null;
  window._receiptFile = null;
  const active = document.querySelector('[data-page].active');
  if (active) loadPage(active.dataset.page);
};

// ── OFX / CSV upload handlers ──────────────────────────────────
window.handleOfxUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;
  const div = document.getElementById('ofx-result');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Processing OFX file...</div>';

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');

    const res = await apiFetch('/ofx/import', { method: 'POST', body: formData });
    const json = await res.json();

    if (json.success) {
      const d = json.data;
      div.innerHTML = `
        <div style="background:#d3f9d8;border:1px solid #b2dfdb;border-radius:8px;padding:12px;">
          <strong>✅ ${d.imported} of ${d.total} transactions imported</strong>
          ${d.skipped_duplicates > 0 ? `<br><span style="color:#888;font-size:0.85rem;">${d.skipped_duplicates} duplicates skipped</span>` : ''}
          <p style="margin-top:8px;">
            <button class="btn btn-success btn-sm" onclick="confirmOfxImport()">✓ Confirm & Import</button>
            <button class="btn btn-outline btn-sm" onclick="resetImport()">🔄 Reset</button>
          </p>
        </div>`;
      window._ofxFile = file;
    } else {
      div.innerHTML = `<div class="error">⚠ Import failed: ${escapeHtml(escapeHtml(json.error)) || 'Unknown error'}</div>`;
    }
  } catch (err) {
    div.innerHTML = `<div class="error">⚠ ${escapeHtml(err.message)}</div>`;
  }
};

window.confirmOfxImport = async function() {
  const file = window._ofxFile;
  if (!file) return;
  const div = document.getElementById('ofx-result');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Importing...</div>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'false');
    const res = await apiFetch('/ofx/import', { method: 'POST', body: formData });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:#2b8a3e;">✅ ${json.data.imported} transactions imported to ledger.</span>`;
    } else {
      div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(json.error)}</span>`;
    }
  } catch (err) { div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.resetImport = function() {
  window._ofxFile = null;
  document.getElementById('ofx-result').innerHTML = '';
  document.getElementById('ofx-file').value = '';
};

window.handleCsvUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;
  const div = document.getElementById('csv-result');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Processing CSV...</div>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');
    const res = await apiFetch('/expenses/import', { method: 'POST', body: formData });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:#2b8a3e;">✅ CSV uploaded. ${json.data.imported || 0} transactions found.</span>`;
    } else {
      div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Failed'}</span>`;
    }
  } catch (err) { div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.handleQboUpload = async function(input) {
  const file = input.files[0];
  if (!file) return;
  const div = document.getElementById('qbo-result');
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Processing QBO file...</div>';
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');
    const res = await apiFetch('/import/csv', { method: 'POST', body: formData });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:#2b8a3e;">✅ QBO uploaded. ${json.data.imported || 0} transactions found.</span>`;
    } else {
      div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Failed'}</span>`;
    }
  } catch (err) { div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};

window.doBackup = async function() {
  const div = document.getElementById('backup-result');
  if (!div) return;
  div.innerHTML = '<div class="loading"><div class="spinner"></div>Backing up...</div>';
  try {
    const res = await apiFetch('/backup', { method: 'POST' });
    const json = await res.json();
    if (json.success) {
      div.innerHTML = `<span style="color:#2b8a3e;">✅ Backup complete</span>`;
    } else {
      div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(escapeHtml(json.error)) || 'Backup failed'}</span>`;
    }
  } catch (err) { div.innerHTML = `<span style="color:#c92a2a;">⚠ ${escapeHtml(err.message)}</span>`; }
};

// ── Formatting helpers ──────────────────────────────────────────
function fmt(n) { return Math.abs(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function money(n) { return (n < 0 ? '-$' : '$') + fmt(n); }

// ── Toast notifications ─────────────────────────────────
function showToast(msg, type = 'info') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 3000);
}

// ── Transfer / Reimburse / Split handlers ──────────────────────
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
