import { apiPost, escapeHtml, showToast } from '../api.js';

export function showSetup() {
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
window.showSetup = showSetup;

export async function submitSetup(e) {
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
}
window.submitSetup = submitSetup;
