<template>
  <div class="page">
    <div class="page-header">
      <h1>🏦 Accounts</h1>
      <p>All your accounts and balances</p>
    </div>

    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>

    <template v-else>
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-label">Business Checking</div>
          <div class="stat-value">{{ money(balances[checking] || 0) }}</div>
        </div>
        <div v-for="c in cards" :key="c.account" class="stat-card">
          <div class="stat-label">{{ c.name }} <span class="text-muted">{{ c.type }}</span></div>
          <div class="stat-value" :class="c.balance > 0 ? 'text-danger' : 'text-success'">{{ money(c.balance) }}</div>
          <div v-if="c.last_four" class="stat-sub">•••• {{ c.last_four }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Reimbursements Owed</div>
          <div class="stat-value text-success">{{ money(-(balances['Liabilities:Reimbursement'] || 0)) }}</div>
          <div class="stat-sub">Business owes you</div>
        </div>
      </div>

      <!-- Transfer -->
      <div class="card">
        <h2>💸 Transfer Between Accounts</h2>
        <p class="text-muted text-sm">Move money — e.g., owner draw from business to personal.</p>
        <div class="form-row">
          <FormField v-model="transfer.from_account" type="select" label="From" :options="accountOptions" />
          <FormField v-model="transfer.to_account" type="select" label="To" :options="accountOptions" />
          <FormField v-model.number="transfer.amount" type="number" label="Amount" placeholder="500" />
          <button class="btn btn-primary align-end" @click="doTransfer" :disabled="acting">Transfer</button>
        </div>
        <p v-if="transfer.msg" :class="transfer.ok ? 'text-success' : 'text-danger'" class="text-sm">{{ transfer.msg }}</p>
      </div>

      <!-- Reimburse -->
      <div class="card">
        <h2>🔄 Reimbursement (Business Expense Paid Personally)</h2>
        <p class="text-muted text-sm">Bought something for the business on your personal card? Record it here.</p>
        <div class="form-row">
          <FormField v-model="reimburse.merchant" type="text" label="Merchant" placeholder="Office Depot" />
          <FormField v-model.number="reimburse.amount" type="number" label="Amount" placeholder="47.23" />
          <FormField v-model="reimburse.account" type="select" label="Category" :options="categoryOptions" />
          <button class="btn btn-primary align-end" @click="doReimburse" :disabled="acting">Record</button>
        </div>
        <p v-if="reimburse.msg" :class="reimburse.ok ? 'text-success' : 'text-danger'" class="text-sm">{{ reimburse.msg }}</p>
      </div>

      <!-- Split -->
      <div class="card">
        <h2>✂️ Split a Transaction</h2>
        <p class="text-muted text-sm">One charge had both business and personal items? Split them.</p>
        <div class="form-row">
          <FormField v-model="split.merchant" type="text" label="Merchant" placeholder="Amazon" />
          <FormField v-model.number="split.total" type="number" label="Total Charged" placeholder="100" />
          <FormField v-model.number="split.business" type="number" label="Business Portion" placeholder="70" />
          <FormField v-model="split.account" type="select" label="Category" :options="categoryOptions" />
          <button class="btn btn-primary align-end" @click="doSplit" :disabled="acting">Split</button>
        </div>
        <p v-if="split.msg" :class="split.ok ? 'text-success' : 'text-danger'" class="text-sm">{{ split.msg }}</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { apiGet, apiPost } from '../api.js'
import FormField from '../components/FormField.vue'

const loading = ref(true)
const acting = ref(false)
const checking = ref('')
const balances = ref({})
const cards = ref([])

const transfer = ref({ from_account: '', to_account: '', amount: null, msg: '', ok: false })
const reimburse = ref({ merchant: '', amount: null, account: 'Expenses:Supplies', msg: '', ok: false })
const split = ref({ merchant: '', total: null, business: null, account: 'Expenses:Supplies', msg: '', ok: false })

const accountOptions = computed(() => {
  const opts = []
  if (checking.value) opts.push({ value: checking.value, label: 'Business Checking' })
  cards.value.forEach(c => opts.push({ value: c.account, label: c.name }))
  opts.push({ value: 'Assets:Bank:Personal', label: 'Personal Checking' })
  return opts
})

const categoryOptions = [
  { value: 'Expenses:Supplies', label: 'Supplies' },
  { value: 'Expenses:Software:SaaS', label: 'Software/SaaS' },
  { value: 'Expenses:Travel', label: 'Travel' },
  { value: 'Expenses:Meals', label: 'Meals' },
  { value: 'Expenses:ProfessionalServices', label: 'Professional Services' },
  { value: 'Expenses:Miscellaneous', label: 'Miscellaneous' },
]

function money(v) {
  const n = Number(v) || 0
  return (n < 0 ? '-$' : '$') + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2 })
}

function setMsg(target, ok, text) {
  target.msg = text
  target.ok = ok
}

async function doTransfer() {
  const t = transfer.value
  if (!t.from_account || !t.to_account || !t.amount) return setMsg(t, false, 'Fill in all fields.')
  acting.value = true
  try {
    await apiPost('/transfer', { from_account: t.from_account, to_account: t.to_account, amount: t.amount })
    setMsg(t, true, `✅ Transferred $${money(t.amount)}`)
    load()
  } catch (e) { setMsg(t, false, '⚠ ' + (e.message || 'Failed')) }
  finally { acting.value = false }
}

async function doReimburse() {
  const r = reimburse.value
  if (!r.merchant || !r.amount) return setMsg(r, false, 'Fill in all fields.')
  acting.value = true
  try {
    await apiPost('/reimburse', { merchant: r.merchant, amount: r.amount, account: r.account })
    setMsg(r, true, `✅ Recorded: ${r.merchant} $${money(r.amount)} → ${r.account}`)
    load()
  } catch (e) { setMsg(r, false, '⚠ ' + (e.message || 'Failed')) }
  finally { acting.value = false }
}

async function doSplit() {
  const s = split.value
  if (!s.merchant || !s.total || !s.business) return setMsg(s, false, 'Fill in all fields.')
  acting.value = true
  try {
    await apiPost('/split', { merchant: s.merchant, total: s.total, business: s.business, account: s.account })
    setMsg(s, true, `✅ Split: ${s.merchant} — $${money(s.business)} business, $${money(s.total - s.business)} personal`)
    load()
  } catch (e) { setMsg(s, false, '⚠ ' + (e.message || 'Failed')) }
  finally { acting.value = false }
}

async function load() {
  loading.value = true
  try {
    const d = await apiGet('/accounts')
    checking.value = d.checking || ''
    balances.value = d.balances || {}
    cards.value = d.cards || []
  } catch (e) {
    /* keep last data */
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.form-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
.form-row > * { flex: 0 0 auto; }
.align-end { margin-bottom: 2px; }
</style>
