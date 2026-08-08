<template>
  <div class="page">
    <div class="page-header">
      <h1>Settings</h1>
      <p>System status &amp; configuration</p>
    </div>

    <!-- Auth -->
    <div v-if="isAuthenticated()" class="card">
      <h2>🔐 Authentication</h2>
      <div class="auth-row">
        <div class="avatar">{{ (userEmail || '?')[0].toUpperCase() }}</div>
        <div>
          <div class="auth-name">{{ userEmail }}</div>
          <div class="text-muted text-sm">Signed in</div>
        </div>
        <button class="btn btn-outline btn-sm" style="margin-left: auto;" @click="signOut">Sign Out</button>
      </div>
    </div>

    <!-- Plan & Billing -->
    <div v-if="isAuthenticated()" class="card">
      <h2>⭐ Plan &amp; Billing</h2>
      <div v-if="billingLoading" class="loading"><div class="spinner"></div>Loading plan info...</div>
      <template v-else>
        <div class="plan-row">
          <span class="plan-emoji">{{ planEmoji }}</span>
          <div>
            <div class="plan-name">{{ planName }} Plan</div>
            <StatusBadge :status="subStatus" />
          </div>
        </div>
        <div v-if="currentPlan === 'free'" class="mt-2">
          <p class="text-muted text-sm">Upgrade to unlock AI categorization, bank sync, and more:</p>
          <div class="plan-grid">
            <div v-for="(plan, key) in paidPlans" :key="key" class="plan-card" @click="upgrade(key)">
              <div class="plan-card-icon">{{ planEmojis[key] || '⭐' }}</div>
              <div class="plan-card-name">{{ plan.name }}</div>
              <div class="plan-card-price">${{ plan.price_monthly }}<span class="text-muted">/mo</span></div>
              <div class="text-muted text-sm">${{ plan.price_annual }}/yr</div>
              <button class="btn btn-primary btn-sm plan-card-btn">Upgrade →</button>
            </div>
          </div>
        </div>
        <div v-else class="mt-2">
          <button class="btn btn-outline btn-sm" @click="manageBilling">💳 Manage Billing</button>
        </div>
      </template>
    </div>

    <!-- LLM config -->
    <div class="card">
      <h2>🤖 AI / LLM API Key</h2>
      <p class="text-muted text-sm">
        Used for AI-powered features: smart transaction categorization, receipt scanning, and content generation.
        <strong>Not used for authentication.</strong>
      </p>
      <p v-if="llmKey" class="text-muted text-sm">Current key: <code>{{ maskKey(llmKey) }}</code></p>
      <p v-else class="text-muted text-sm">No key configured.</p>
      <div class="llm-row">
        <select v-model="llmBackend" class="form-select">
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
          <option value="ollama">Ollama (local)</option>
        </select>
        <input v-model="llmModel" type="text" placeholder="Model (e.g. gpt-4o-mini)" class="form-input" />
      </div>
      <div class="llm-row">
        <input v-model="llmKeyInput" type="password" :placeholder="llmKey ? 'Leave empty to keep current key' : 'sk-...'" class="form-input" />
        <button class="btn btn-primary" @click="saveLlmConfig">Save</button>
        <button v-if="llmKey" class="btn btn-outline" @click="clearLlmConfig">Remove</button>
      </div>
      <p class="text-muted text-sm">Key is stored in your browser (localStorage) and synced to the server.</p>
    </div>

    <!-- Data ownership -->
    <div class="card">
      <h2>🔒 Data Ownership</h2>
      <p class="text-muted text-sm">
        Your data lives in plain-text Beancount files. It is not locked into any proprietary format.
        You can stop using SoloLedger at any time and your data goes with you — it's just text files.
      </p>
      <p class="text-muted text-sm">✅ Plain text · ✅ Git versioned · ✅ No subscription · ✅ Self-hosted · ✅ Open source (MIT)</p>
    </div>

    <!-- Quick actions -->
    <div class="card">
      <h2>Quick Actions</h2>
      <div class="action-row">
        <a href="/api/v1/tax/estimate" target="_blank" class="btn btn-outline">💰 Tax API</a>
        <a href="/api/v1/dashboard" target="_blank" class="btn btn-outline">📊 Dashboard API</a>
        <a href="/docs" target="_blank" class="btn btn-outline">📖 Swagger Docs</a>
      </div>
    </div>

    <!-- Backup -->
    <div class="card">
      <h2>📤 Backup</h2>
      <p class="text-muted text-sm">Commit your latest changes to git. Your ledger is versioned and recoverable at any point in history.</p>
      <button class="btn btn-primary" @click="doBackup" :disabled="backingUp">{{ backingUp ? '⏳ Backing up...' : '📤 Backup Now' }}</button>
      <p v-if="backupMsg" :class="backupMsg.ok ? 'text-success' : 'text-danger'" class="text-sm">{{ backupMsg.text }}</p>
    </div>

    <!-- Tax payment links -->
    <div class="card">
      <h2>💸 Tax Payment Links</h2>
      <div class="action-row">
        <a href="https://www.irs.gov/payments/direct-pay-with-bank-account" target="_blank" class="btn btn-primary btn-sm">🇺🇸 IRS Direct Pay</a>
        <a href="https://www.eftps.gov/" target="_blank" class="btn btn-outline btn-sm">🏛 EFTPS</a>
        <a href="https://www.ftb.ca.gov/pay/" target="_blank" class="btn btn-outline btn-sm">🌴 CA FTB</a>
        <a href="https://www.tax.ny.gov/pay/" target="_blank" class="btn btn-outline btn-sm">🗽 NY DTF</a>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiGet, apiPost, isAuthenticated, clearAuth } from '../api.js'
import StatusBadge from '../components/StatusBadge.vue'

const userEmail = ref(localStorage.getItem('user_email') || '')

const billingLoading = ref(true)
const plans = ref({})
const currentPlan = ref('free')
const subStatus = ref('active')

const llmKey = ref(localStorage.getItem('sololedger_llm_key') || '')
const llmBackend = ref(localStorage.getItem('sololedger_llm_backend') || 'openai')
const llmModel = ref(localStorage.getItem('sololedger_llm_model') || '')
const llmKeyInput = ref('')

const backingUp = ref(false)
const backupMsg = ref({ text: '', ok: false })

const planNames = { free: 'Free', professional: 'Professional', business: 'Business' }
const planEmojis = { free: '🆓', professional: '⭐', business: '💼' }

const planName = computed(() => planNames[currentPlan.value] || 'Free')
const planEmoji = computed(() => planEmojis[currentPlan.value] || '🆓')
const paidPlans = computed(() =>
  Object.fromEntries(Object.entries(plans.value).filter(([k]) => k !== 'free'))
)

function maskKey(key) {
  return key.slice(0, 8) + '••••••••••'
}

function signOut() {
  clearAuth()
  window.location.reload()
}

async function loadBilling() {
  billingLoading.value = true
  try {
    const [plansData, subData] = await Promise.all([apiGet('/subscription/plans'), apiGet('/subscription/status')])
    plans.value = plansData.plans || {}
    currentPlan.value = subData.plan || 'free'
    subStatus.value = subData.status || 'active'
  } catch {
    /* plan info unavailable — hide the section gracefully */
  } finally {
    billingLoading.value = false
  }
}

async function upgrade(plan) {
  if (!confirm(`Upgrade to ${plan} plan? You'll be redirected to Stripe.`)) return
  try {
    const data = await apiPost('/subscription/create-checkout', {
      plan, interval: 'month', success_url: '/settings?upgraded=true', cancel_url: '/settings',
    })
    window.location.href = data.url
  } catch (e) {
    alert('Failed to start upgrade: ' + (e.message || 'error'))
  }
}

async function manageBilling() {
  try {
    const data = await apiPost('/subscription/portal', {})
    window.location.href = data.url
  } catch (e) {
    alert('Failed to open billing portal: ' + (e.message || 'error'))
  }
}

function saveLlmConfig() {
  const key = llmKeyInput.value.trim() || llmKey.value || ''
  const backend = llmBackend.value
  const model = llmModel.value.trim() || (backend === 'openai' ? 'gpt-4o-mini' : backend === 'anthropic' ? 'claude-3-haiku' : 'gemma3:1b')

  localStorage.setItem('sololedger_llm_key', key)
  localStorage.setItem('sololedger_llm_backend', backend)
  localStorage.setItem('sololedger_llm_model', model)
  llmKey.value = key
  llmKeyInput.value = ''

  if (isAuthenticated()) {
    apiPost('/settings/llm', { api_key: key || undefined, backend, model }).catch(() => {})
  }
}

function clearLlmConfig() {
  if (!confirm('Remove LLM API key?')) return
  localStorage.removeItem('sololedger_llm_key')
  localStorage.setItem('sololedger_llm_backend', 'openai')
  localStorage.setItem('sololedger_llm_model', 'gpt-4o-mini')
  llmKey.value = ''
  llmKeyInput.value = ''
  if (isAuthenticated()) {
    apiPost('/settings/llm', { api_key: null, backend: 'openai', model: null }).catch(() => {})
  }
}

async function doBackup() {
  backingUp.value = true
  backupMsg.value = { text: '', ok: false }
  try {
    const data = await apiPost('/backup', {})
    backupMsg.value = { text: '✅ Backup complete: ' + (data.message || ''), ok: true }
  } catch (e) {
    backupMsg.value = { text: '⚠ Backup failed: ' + (e.message || 'error'), ok: false }
  } finally {
    backingUp.value = false
  }
}

onMounted(() => {
  if (isAuthenticated()) loadBilling()
  else billingLoading.value = false
})
</script>

<style scoped>
.auth-row { display: flex; align-items: center; gap: 12px; }
.avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--primary-light); color: var(--primary-dark); display: flex; align-items: center; justify-content: center; font-weight: 700; }
.auth-name { font-weight: 600; }
.plan-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.plan-emoji { font-size: 2rem; }
.plan-name { font-weight: 600; font-size: 1.1rem; }
.plan-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-top: 10px; }
.plan-card { border: 2px solid var(--gray-200); border-radius: 10px; padding: 16px; text-align: center; cursor: pointer; transition: border-color 0.12s; }
.plan-card:hover { border-color: var(--primary); }
.plan-card-icon { font-size: 1.5rem; margin-bottom: 6px; }
.plan-card-name { font-weight: 600; }
.plan-card-price { font-size: 1.1rem; font-weight: 700; color: var(--primary); margin: 4px 0; }
.plan-card-btn { width: 100%; justify-content: center; margin-top: 10px; }
.llm-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.llm-row .form-select { width: 140px; }
.llm-row .form-input { flex: 1; min-width: 160px; font-family: var(--font-mono); }
.action-row { display: flex; gap: 12px; flex-wrap: wrap; }
</style>
