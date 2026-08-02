import { apiGet, apiPost, apiFetch, escapeHtml, fmt, money, showToast, showConfirm } from '../api.js';
import { renderTransactionTable } from './shared.js';
import { loadDemoData } from './onboarding.js';

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

export async function renderDashboard(content) {
  const [d, attention] = await Promise.all([
    apiGet('/dashboard'),
    apiGet('/attention').catch(() => ({ items: [] })),
  ]);

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
                <strong>${escapeHtml(item.label)}</strong>
                <div style="color:var(--gray-600);margin-top:2px;">${escapeHtml(item.detail)}</div>
              </div>
            </div>`;
        }).join('')}
      </div>`;
  }

  const entityLabel = d.entity_label || 'SMLLC (Schedule C)';
  const taxInfo = d.tax || {};
  const deadlines = d.deadlines || [];
  const sp = taxInfo.suggested_payment || 0;

  const isEmpty = !d.cash && !d.gross_revenue && !d.net_profit && !(d.recent_transactions && d.recent_transactions.length);
  const demoBanner = isEmpty ? `
    <div style="background:linear-gradient(135deg,#dbeafe,#ede9fe);border:1px solid #c7d2fe;border-radius:12px;padding:20px 24px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
      <div>
        <div style="font-weight:700;font-size:1rem;color:#4338ca;">🚀 Welcome to SoloLedger!</div>
        <div style="font-size:0.85rem;color:#6366f1;margin-top:4px;">Your ledger is empty. Load sample data to explore the features.</div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="demoBannerLoad()" style="white-space:nowrap;">🎲 Load Demo Data</button>
    </div>` : '';

  content.innerHTML = `
    ${demoBanner}
    <div class="page-header">
      <h1>Dashboard</h1>
      <p>${escapeHtml(entityLabel)}</p>
    </div>
    ${attentionHtml}
    <div class="card-row">
      <div class="stat-card">
        ${sparkline((d.cash || 0) * 0.95, (d.cash || 0) * 1.02, d.cash || 0, '#22c55e')}
        <div class="label">Cash</div>
        <div class="value green">${money(d.cash || 0)}</div>
        <span class="delta up">↑ 2.3%</span>
      </div>
      <div class="stat-card">
        ${sparkline((d.gross_revenue || 0) * 0.8, (d.gross_revenue || 0) * 0.95, d.gross_revenue || 0, '#3b82f6')}
        <div class="label">Revenue YTD</div>
        <div class="value blue">${money(d.gross_revenue || 0)}</div>
      </div>
      <div class="stat-card">
        ${sparkline((d.total_expenses || 0) * 0.9, (d.total_expenses || 0) * 1.1, d.total_expenses || 0, '#ef4444')}
        <div class="label">Expenses YTD</div>
        <div class="value red">${money(d.total_expenses || 0)}</div>
        <span class="delta up">↑ ${((d.total_expenses || 0) / (d.gross_revenue || 1)) * 100}% of revenue</span>
      </div>
      <div class="stat-card">
        ${sparkline((d.net_profit || 0) * 0.85, (d.net_profit || 0) * 0.98, d.net_profit || 0, '#22c55e')}
        <div class="label">Net Profit YTD</div>
        <div class="value green">${money(d.net_profit || 0)}</div>
        <span class="delta up">${((d.net_profit || 0) / (d.gross_revenue || 1)) * 100}% margin</span>
      </div>
      <div class="stat-card">
        <div class="label">AR Outstanding</div>
        <div class="value blue">${money(d.ar || 0)}</div>
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
            <div class="value blue" style="font-size:1.3rem;">${money(taxInfo.annual_total_tax || 0)}</div>
          </div>
          <div class="stat" style="border:none;padding:8px 0;">
            <div class="label">Already Paid</div>
            <div class="value green" style="font-size:1.3rem;">${money(taxInfo.already_paid || 0)}</div>
          </div>
          <div class="stat" style="border:none;padding:8px 0;">
            <div class="label">Suggested Next</div>
            <div class="value" style="font-size:1.3rem;">${money(sp)}</div>
          </div>
        </div>
        <p class="text-muted">${escapeHtml(taxInfo.note || '')}</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">
          <button class="btn btn-primary btn-sm" onclick="window.open('https://www.irs.gov/payments/direct-pay-with-bank-account','_blank')">💳 Pay Now (IRS Direct Pay)</button>
          <button class="btn btn-outline btn-sm" onclick="markTaxPaid(${sp})">✅ Mark as Paid</button>
          <button class="btn btn-outline btn-sm" onclick="window.open('/api/v1/tax/voucher?quarter=' + getCurrentQuarter() + '&amount=' + ${sp}, '_blank')">📄 Print Voucher</button>
        </div>
      </div>
      <div class="card" style="flex:1;">
        <h2>Deadlines</h2>
        <ul class="deadline-list">
          ${deadlines.map(dl => `
            <li>
              <span class="dot ${dl.status === 'overdue' ? 'dot-red' : dl.status === 'upcoming' ? 'dot-yellow' : 'dot-green'}"></span>
              <strong>${escapeHtml(dl.label || '')}</strong>
              <span class="text-muted">${escapeHtml(dl.due || '')}</span>
              <span style="margin-left:auto;color:${(dl.days_until || 0) < 0 ? '#dc3545' : '#28a745'};">
                ${(dl.days_until || 0) < 0 ? 'OVERDUE' : (dl.days_until || 0) + ' days'}
              </span>
            </li>
          `).join('')}
        </ul>
      </div>
    </div>
    <div class="card">
      <h2>Recent Transactions</h2>
      ${renderTransactionTable(d.recent_transactions, { limit: 8 })}</div>`;
}

export async function markTaxPaid(amount) {
  if (!amount || amount <= 0) { showToast('No tax payment amount to record.', 'warning'); return; }
  const q = getCurrentQuarter();
  const confirmed = await showConfirm('Record Tax Payment', `Record estimated tax payment of $${fmt(amount)} for ${q}?`);
  if (!confirmed) return;
  try {
    const result = await apiPost('/tax/pay', { amount, quarter: q, year: new Date().getFullYear() });
    showToast(`✅ Recorded $${fmt(result.amount)} as paid. Total paid YTD: $${fmt(result.already_paid)}`, 'success');
    window.loadPage('dashboard');
  } catch (err) { showToast('Error recording payment: ' + err.message, 'error'); }
}
window.markTaxPaid = markTaxPaid;

export function getCurrentQuarter() {
  const m = new Date().getMonth();
  return 'Q' + (Math.floor(m / 3) + 1);
}
window.getCurrentQuarter = getCurrentQuarter;

// Demo data banner button (called from inline onclick)
window.demoBannerLoad = async function() {
  const btn = document.querySelector('[onclick*="demoBannerLoad"]');
  if (btn) { btn.textContent = '⏳ Loading...'; btn.disabled = true; }
  try {
    const data = await apiPost('/onboarding/demo', {});
    showToast(data.message || 'Demo data loaded!', 'success');
    window.loadPage('dashboard');
  } catch (e) {
    showToast('Failed to load demo: ' + e.message, 'error');
    if (btn) { btn.textContent = '🎲 Load Demo Data'; btn.disabled = false; }
  }
};
