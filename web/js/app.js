// SoloLedger web app — main entry point (ES Module)
import { apiGetPublicStatus } from './api.js';
import { updateGoogleClientId, updateSidebarAuth } from './pages/auth.js';

import { renderDashboard, markTaxPaid, getCurrentQuarter } from './pages/dashboard.js';
import { renderAccounts } from './pages/accounts.js';
import { renderImport } from './pages/import.js';
import { renderInvoices, renderNewInvoice } from './pages/invoices.js';
import { renderTransactions } from './pages/transactions.js';
import { renderReceipts, renderCaptureContent } from './pages/receipts.js';
import { renderCategorize } from './pages/categorize.js';
import { renderTax, renderDeadlines } from './pages/tax.js';
import { renderMileage } from './pages/mileage.js';
import { renderHealth } from './pages/health.js';
import { renderReports } from './pages/reports.js';
import { renderSettings } from './pages/settings.js';
import { renderRecon } from './pages/reports.js';
import { renderPayroll } from './pages/payroll.js';
import { checkOnboarding } from './pages/onboarding.js';
import { showSetup } from './pages/setup.js';

document.addEventListener('DOMContentLoaded', async () => {
  const content = document.getElementById('page-content');
  const sidebar = document.querySelector('.sidebar');
  const navLinks = document.querySelectorAll('[data-page]');

  // ── Auth state ──────────────────────────────────────────────
  updateSidebarAuth();

  // ── Public status (no auth needed) ─────────────────────────
  const status = await apiGetPublicStatus();
  if (status.needsSetup) { showSetup(); return; }

  if (status.auth_methods && status.auth_methods.google) {
    updateGoogleClientId();
  }

  // ── Navigation ──────────────────────────────────────────────
  navLinks.forEach(link => {
    link.addEventListener('click', async (e) => {
      e.preventDefault();
      const page = link.dataset.page;
      history.pushState({ page }, '', `#/${page}`);
      navLinks.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      await loadPage(page);
    });
  });

  // Handle browser back/forward
  window.addEventListener('popstate', (e) => {
    const page = (e.state && e.state.page) || getPageFromHash() || 'dashboard';
    navLinks.forEach(l => l.classList.remove('active'));
    const activeLink = document.querySelector(`[data-page="${page}"]`);
    if (activeLink) activeLink.classList.add('active');
    loadPage(page, { replace: true });
  });

  // Determine initial page from URL hash
  const initialPage = getPageFromHash() || 'dashboard';
  const activeLink = document.querySelector(`[data-page="${initialPage}"]`);
  if (activeLink) activeLink.classList.add('active');
  loadPage(initialPage);

  // Check onboarding after initial page load
  setTimeout(() => checkOnboarding(), 500);

  // ── Keyboard shortcuts ─────────────────────────────────
  let keyBuffer = '';
  let bufferTimeout = null;

  document.addEventListener('keydown', (e) => {
    // Don't trigger shortcuts when typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

    if (e.key === '?') {
      e.preventDefault();
      showShortcutHelp();
      return;
    }

    keyBuffer += e.key.toLowerCase();
    clearTimeout(bufferTimeout);
    bufferTimeout = setTimeout(() => { keyBuffer = ''; }, 800);

    const shortcuts = {
      'gd': 'dashboard',
      'gt': 'tax',
      'gi': 'invoices',
      'gs': 'settings',
      'gh': 'health',
      'gr': 'reports',
      'gc': 'categorize',
      'gm': 'mileage',
      'gp': 'payroll',
      'ga': 'accounts',
      'gn': 'deadlines',
    };

    if (shortcuts[keyBuffer]) {
      e.preventDefault();
      keyBuffer = '';
      const page = shortcuts[keyBuffer];
      history.pushState({ page }, '', `#/${page}`);
      navLinks.forEach(l => l.classList.remove('active'));
      const link = document.querySelector(`[data-page="${page}"]`);
      if (link) link.classList.add('active');
      loadPage(page);
    }
  });

  function showShortcutHelp() {
    const shortcuts = [
      ['g + d', 'Dashboard'],
      ['g + t', 'Tax Estimate'],
      ['g + i', 'Invoices'],
      ['g + a', 'Accounts'],
      ['g + p', 'Payroll'],
      ['g + c', 'Categorize'],
      ['g + m', 'Mileage'],
      ['g + h', 'Health'],
      ['g + r', 'Reports'],
      ['g + s', 'Settings'],
      ['g + n', 'Deadlines'],
      ['?', 'Show this help'],
    ];
    const html = `
      <div class="confirm-overlay" onclick="if(event.target===this)this.remove()">
        <div class="confirm-modal" style="max-width:420px;">
          <h3>⌨️ Keyboard Shortcuts</h3>
          <p style="margin-bottom:16px;">Press <code>g</code> then another key to navigate:</p>
          <table style="width:100%;font-size:0.875rem;">
            ${shortcuts.map(([key, desc]) => `
              <tr><td style="padding:6px 12px;border:none;"><code>${key}</code></td><td style="padding:6px 12px;border:none;color:var(--gray-500);">${desc}</td></tr>
            `).join('')}
          </table>
          <div class="confirm-actions" style="margin-top:12px;">
            <button class="btn btn-outline" onclick="this.closest('.confirm-overlay').remove()">Close</button>
          </div>
        </div>
      </div>`;
    const el = document.createElement('div');
    el.innerHTML = html;
    document.body.appendChild(el.firstElementChild);
  }

  function getPageFromHash() {
    const hash = location.hash.replace('#/', '');
    const valid = ['dashboard','accounts','import','invoices','new-invoice','transactions',
                   'receipts','categorize','tax','deadlines','mileage','health',
                   'reports','settings','payroll','recon','capture'];
    return valid.includes(hash) ? hash : null;
  }

  window.loadPage = async function(page, opts = {}) {
    content.innerHTML = '<div class="skeleton"><div class="skeleton-line w-1/3 h-6"></div><div class="skeleton-line w-1/2"></div><div class="skeleton-card"><div class="skeleton-line w-1/4 h-4"></div><div class="skeleton-line w-full h-8 mt-3"></div><div class="skeleton-line w-2/3 mt-3"></div></div><div class="skeleton-card"><div class="skeleton-line w-1/4 h-4"></div><div class="skeleton-line w-full h-8 mt-3"></div><div class="skeleton-line w-1/2 mt-3"></div></div></div>';
    try {
      const pages = {
        'dashboard': () => renderDashboard(content),
        'accounts': () => renderAccounts(content),
        'import': () => renderImport(content),
        'invoices': () => renderInvoices(content),
        'new-invoice': () => renderNewInvoice(content),
        'transactions': () => renderTransactions(content),
        'receipts': () => renderReceipts(content),
        'categorize': () => renderCategorize(content),
        'tax': () => renderTax(content),
        'deadlines': () => renderDeadlines(content),
        'mileage': () => renderMileage(content),
        'health': () => renderHealth(content),
        'reports': () => renderReports(content),
        'settings': () => renderSettings(content),
        'payroll': () => renderPayroll(content),
        'recon': () => renderRecon(content),
        'capture': () => renderCaptureContent(content),
      };
      if (pages[page]) await pages[page]();
      else content.innerHTML = '<div class="error"><h3>⚠ Page not found</h3></div>';
    } catch (err) {
      const { escapeHtml, showAuthModal } = await import('./pages/auth.js');
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
});
