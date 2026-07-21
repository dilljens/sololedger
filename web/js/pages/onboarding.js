import { apiGet, apiPost, apiFetch, escapeHtml, isAuthenticated } from '../api.js';

let _onboardingStep = 1;

export async function checkOnboarding() {
  if (!isAuthenticated()) return;
  try {
    const data = await apiGet('/onboarding/status');
    if (data.needs_onboarding) showOnboarding();
  } catch { /* ignore */ }
}
window.checkOnboarding = checkOnboarding;

export function showOnboarding() {
  const content = document.getElementById('page-content');
  if (!content) return;
  _onboardingStep = 1;
  renderOnboarding();
  window._onboardingNext = function(s) { _onboardingStep = s; renderOnboarding(); };
}
window.showOnboarding = showOnboarding;

export function renderOnboarding() {
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
window.renderOnboarding = renderOnboarding;

export async function finishOnboarding() {
  try {
    await apiPost('/onboarding/complete', { skipped_bank: true, skipped_import: true });
  } catch { /* ignore */ }
  const active = document.querySelector('[data-page].active');
  if (active) window.loadPage(active.dataset.page);
}
window.finishOnboarding = finishOnboarding;

export async function handleOnboardingOfx(input) {
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
}
window.handleOnboardingOfx = handleOnboardingOfx;

export async function handleOnboardingCsv(input) {
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
}
window.handleOnboardingCsv = handleOnboardingCsv;
