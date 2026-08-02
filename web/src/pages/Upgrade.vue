<template>
  <div class="page">
    <div class="page-header">
      <h1>Upgrade</h1>
      <p>Pick a plan that grows with your business</p>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div>Loading plans...</div>

    <template v-else-if="error">
      <div class="card error">
        ⚠ {{ error }}
        <button class="btn btn-outline btn-sm" style="margin-left: 12px;" @click="fetchData">Retry</button>
      </div>
    </template>

    <template v-else>
      <div v-if="actionError" class="card error action-error">⚠ {{ actionError }}</div>

      <!-- Current status banner -->
      <div class="card status-card">
        <div class="status-main">
          <span class="status-emoji">{{ planEmoji[currentPlan] || '🆓' }}</span>
          <div>
            <div class="status-title">{{ planName(currentPlan) }} Plan</div>
            <div class="status-sub">
              <span class="badge" :class="statusBadgeClass">{{ statusBadge }}</span>
              <span v-if="status.trial_active" class="text-muted text-sm">
                · trial ends {{ trialEndLabel }} ({{ status.trial_days_remaining }} day{{ status.trial_days_remaining === 1 ? '' : 's' }} left)
              </span>
            </div>
          </div>
        </div>
        <button v-if="hasSubscription" class="btn btn-outline" @click="manageBilling">Manage billing</button>
      </div>

      <!-- Billing interval toggle -->
      <div class="billing-toggle">
        <button class="toggle-btn" :class="{ active: interval === 'month' }" @click="interval = 'month'">Monthly</button>
        <button class="toggle-btn" :class="{ active: interval === 'year' }" @click="interval = 'year'">
          Yearly<span class="save-badge">save 34%</span>
        </button>
      </div>

      <!-- Plan cards -->
      <div class="plan-grid">
        <div v-for="key in planOrder" :key="key" class="card plan-card" :class="{ highlighted: key === 'professional' }">
          <div class="plan-header">
            <h2>{{ planName(key) }}</h2>
            <span v-if="isCurrent(key)" class="badge badge-success">Current</span>
          </div>
          <div class="plan-price">
            <template v-if="key === 'free'">
              <span class="price">$0</span>
              <span class="period">forever</span>
            </template>
            <template v-else>
              <span class="price">{{ interval === 'month' ? fmt(plans[key].price_monthly) : fmt(plans[key].price_annual) }}</span>
              <span class="period">/{{ interval === 'month' ? 'month' : 'year' }}</span>
            </template>
          </div>
          <ul class="plan-features">
            <li v-for="feature in features[key]" :key="feature">✓ {{ feature }}</li>
          </ul>
          <div class="plan-action">
            <template v-if="key === 'free'">
              <button v-if="isCurrent(key)" class="btn btn-outline" disabled>Current plan</button>
              <p v-else class="note text-sm text-muted">Included on every plan</p>
            </template>
            <template v-else>
              <button v-if="hasSubscription" class="btn btn-outline" @click="manageBilling">Manage billing</button>
              <template v-else-if="isCurrent(key)">
                <button class="btn btn-outline" disabled>Current plan</button>
              </template>
              <template v-else-if="planRank(key) <= planRank(currentPlan)">
                <p class="note text-sm text-muted">You're already on the {{ planName(currentPlan) }} plan or a higher tier.</p>
              </template>
              <button v-else class="btn btn-primary" :disabled="checkoutPlan === key" @click="startTrial(key)">
                {{ checkoutPlan === key ? '⏳ Redirecting...' : 'Start 14-day trial' }}
              </button>
            </template>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiGet, apiPost } from '../api.js'

const loading = ref(true)
const error = ref('')
const actionError = ref('')
const plans = ref({ free: {}, professional: {}, business: {} })
const status = ref({
  plan: 'free',
  status: 'active',
  trial_active: false,
  trial_days_remaining: 0,
  trial_ends: '',
  stripe_subscription_id: '',
})
const interval = ref('month')
const checkoutPlan = ref('')

const planOrder = ['free', 'professional', 'business']
const planEmoji = { free: '🆓', professional: '⭐', business: '💼' }
const planRankMap = { free: 0, professional: 1, business: 2 }
const features = {
  free: ['10 invoices', '5 receipt scans/mo', 'Manual entry', 'Basic imports & tax estimates'],
  professional: ['Unlimited invoices & receipts', 'Bank sync (Plaid)', 'All importers (Amazon, Citi, Wave)', 'Quarterly tax estimates'],
  business: ['Everything in Professional', 'Bank reconciliation', 'Exports', 'Multiple entities'],
}

const currentPlan = computed(() => status.value.plan || 'free')
const hasSubscription = computed(() => !!status.value.stripe_subscription_id)

const statusBadge = computed(() => {
  if (status.value.trial_active) return 'Trial'
  const map = { active: 'Active', past_due: 'Past due', canceled: 'Canceled', trialing: 'Trial' }
  return map[status.value.status] || 'Active'
})
const statusBadgeClass = computed(() => {
  const s = status.value.status
  if (s === 'past_due') return 'badge-danger'
  if (s === 'canceled') return 'badge-warning'
  if (status.value.trial_active || s === 'trialing') return 'badge-info'
  return 'badge-success'
})
const trialEndLabel = computed(() => {
  const t = status.value.trial_ends
  if (!t) return ''
  const d = new Date(t)
  return isNaN(d) ? t : d.toLocaleDateString()
})

function planName(key) {
  return plans.value[key]?.name || key
}

function planRank(key) {
  return planRankMap[key] ?? 0
}

function isCurrent(key) {
  return key === currentPlan.value
}

function fmt(v) {
  const n = Number(v) || 0
  return n % 1 === 0 ? `$${n}` : `$${n.toFixed(2)}`
}

async function fetchData() {
  loading.value = true
  error.value = ''
  actionError.value = ''
  try {
    const [plansData, statusData] = await Promise.all([
      apiGet('/subscription/plans'),
      apiGet('/subscription/status'),
    ])
    plans.value = plansData.plans || plans.value
    status.value = statusData || status.value
  } catch (err) {
    error.value = err.data?.error || err.message || 'Failed to load plans'
  } finally {
    loading.value = false
  }
}

async function startTrial(plan) {
  checkoutPlan.value = plan
  actionError.value = ''
  try {
    const data = await apiPost('/subscription/create-checkout', {
      plan,
      interval: interval.value,
      success_url: '/settings?upgraded=true',
      cancel_url: '/settings',
    })
    window.location.href = data.url
  } catch (err) {
    actionError.value = err.data?.error || err.message || 'Failed to start checkout'
    checkoutPlan.value = ''
  }
}

async function manageBilling() {
  actionError.value = ''
  try {
    const data = await apiPost('/subscription/portal', {})
    window.location.href = data.url
  } catch (err) {
    actionError.value = err.data?.error || err.message || 'Failed to open billing portal'
  }
}

onMounted(fetchData)
</script>

<style scoped>
.status-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.status-main {
  display: flex;
  align-items: center;
  gap: 14px;
}

.status-emoji {
  font-size: 2rem;
}

.status-title {
  font-weight: 700;
  color: var(--gray-900);
  font-size: 1.05rem;
}

.status-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.85rem;
  margin-top: 4px;
  flex-wrap: wrap;
}

.action-error {
  border-left: 4px solid var(--danger);
}

.billing-toggle {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.toggle-btn {
  padding: 8px 18px;
  border-radius: 999px;
  border: 1px solid var(--gray-200);
  background: #fff;
  color: var(--gray-600);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.12s;
}

.toggle-btn:hover {
  border-color: var(--gray-300);
}

.toggle-btn.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.save-badge {
  font-size: 0.7rem;
  opacity: 0.85;
  margin-left: 4px;
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.plan-card {
  display: flex;
  flex-direction: column;
  margin-bottom: 0;
}

.plan-card.highlighted {
  border-color: var(--primary);
  box-shadow: var(--shadow-md);
}

.plan-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.plan-header h2 {
  margin: 0;
  font-size: 1.1rem;
  color: var(--gray-900);
}

.plan-price {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 14px;
}

.price {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--gray-900);
}

.period {
  font-size: 0.85rem;
  color: var(--gray-400);
}

.plan-features {
  list-style: none;
  padding: 0;
  margin: 0 0 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plan-features li {
  font-size: 0.85rem;
  color: var(--gray-600);
}

.plan-action {
  margin-top: auto;
}

.plan-action .btn {
  width: 100%;
  justify-content: center;
}

.plan-action .note {
  margin: 0;
  text-align: center;
}
</style>
