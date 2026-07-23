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
      navLinks.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      await loadPage(link.dataset.page);
    });
  });
  loadPage('dashboard');

  // Check onboarding after initial page load
  setTimeout(() => checkOnboarding(), 500);

  window.loadPage = async function(page) {
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
