import { apiFetch, apiPost, escapeHtml, showToast, showConfirm, getUserInfo, isAuthenticated, getAuthToken, getLlmApiKey, getLlmBackend, getLlmModel, setLlmApiKey, setLlmBackend, setLlmModel, apiSaveLlmConfig } from '../api.js';

export async function renderSettings(content) {
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
  const upgradeConfirmed = await showConfirm('Upgrade Plan', `Upgrade to ${plan} plan? You'll be redirected to Stripe.`, { confirmText: 'Upgrade' });
  if (!upgradeConfirmed) return;
  try {
    const data = await apiPost('/subscription/create-checkout', {
      plan: plan,
      interval: 'month',
      success_url: '/settings?upgraded=true',
      cancel_url: '/settings',
    });
    window.location.href = data.url;
  } catch (e) {
    showToast('Failed to start upgrade: ' + e.message, 'error');
  }
};

window.manageBilling = async function() {
  try {
    const data = await apiPost('/subscription/portal', {});
    window.location.href = data.url;
  } catch (e) {
    showToast('Failed to open billing portal: ' + e.message, 'error');
  }
};


window.saveLlmConfig = function() {
  const key = document.getElementById('llm-api-key').value.trim();
  const backend = document.getElementById('llm-backend').value;
  const model = document.getElementById('llm-model').value.trim();

  setLlmApiKey(key);
  setLlmBackend(backend);
  setLlmModel(model || (backend === 'openai' ? 'gpt-4o-mini' : backend === 'anthropic' ? 'claude-3-haiku' : 'gemma3:1b'));

  if (isAuthenticated()) {
    apiSaveLlmConfig({
      api_key: key || undefined,
      backend: backend,
      model: model || undefined,
    }).catch(() => {});
  }

  showToast('AI/LLM settings saved', 'success');
  const active = document.querySelector('[data-page].active');
  if (active) window.loadPage(active.dataset.page);
};

window.clearLlmConfig = async function() {
  const removeKeyConfirmed = await showConfirm('Remove API Key', 'Remove LLM API key?', { confirmText: 'Remove', danger: true });
  if (!removeKeyConfirmed) return;
  setLlmApiKey(null);
  setLlmBackend('openai');
  setLlmModel('gpt-4o-mini');
  if (isAuthenticated()) {
    apiSaveLlmConfig({ api_key: null, backend: 'openai', model: null }).catch(() => {});
  }
  showToast('AI/LLM settings cleared', 'info');
  const active = document.querySelector('[data-page].active');
  if (active) window.loadPage(active.dataset.page);
};
