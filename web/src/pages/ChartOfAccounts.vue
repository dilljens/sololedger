<template>
  <div class="page">
    <div class="page-header">
      <h1>📊 Chart of Accounts</h1>
      <p>All accounts in your ledger with current balances</p>
    </div>
    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>
    <div v-else-if="error" class="card error">⚠ {{ error }}</div>
    <template v-else>
      <!-- Add account -->
      <div class="card">
        <h2>➕ Add Account</h2>
        <div class="add-row">
          <input v-model="newAccount" type="text" list="coa-roots" placeholder="Expenses:Software:Hosting" class="form-input" />
          <datalist id="coa-roots">
            <option v-for="root in roots" :key="root" :value="root + ':'" />
          </datalist>
          <input v-model="newName" type="text" placeholder="Optional: display name" class="form-input" />
          <button class="btn btn-primary" @click="addAccount" :disabled="adding">{{ adding ? '⏳…' : 'Open Account' }}</button>
        </div>
        <p v-if="addMsg" :class="addMsg.ok ? 'text-success' : 'text-danger'" class="text-sm">{{ addMsg.text }}</p>
      </div>

      <div v-for="group in tree" :key="group.root" class="card">
        <h2>{{ group.root }} <span class="text-muted text-sm">({{ group.accounts.length }})</span></h2>
        <div class="coa-list">
          <div v-for="a in group.accounts" :key="a.account" class="coa-row" :style="{ paddingLeft: (a.depth * 16 + 8) + 'px' }">
            <span class="coa-name">{{ a.account }}</span>
            <span class="coa-balance" :class="{ negative: a.balance < 0 }">{{ formatMoney(a.balance) }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { apiGet, apiPut } from '../api.js'

const loading = ref(true)
const error = ref('')
const tree = ref([])
const newAccount = ref('')
const newName = ref('')
const adding = ref(false)
const addMsg = ref({ text: '', ok: false })
const roots = ['Assets', 'Liabilities', 'Equity', 'Income', 'Expenses']

function formatMoney(v) { return '$' + Math.abs(v).toFixed(2) }

async function addAccount() {
  const account = newAccount.value.trim()
  if (!account) { addMsg.value = { text: 'Enter an account, e.g. Expenses:Software:Hosting', ok: false }; return }
  adding.value = true
  addMsg.value = { text: '', ok: false }
  try {
    const d = await apiPut(`/coa/${encodeURIComponent(account)}`, { name: newName.value.trim() || undefined })
    addMsg.value = d.created
      ? { text: `✅ Opened ${account}`, ok: true }
      : { text: `ℹ️ ${account} already exists`, ok: true }
    newAccount.value = ''
    newName.value = ''
    load()
  } catch (e) {
    addMsg.value = { text: '⚠ ' + (e.message || 'Failed'), ok: false }
  } finally {
    adding.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const d = await apiGet('/coa/tree')
    tree.value = d.tree
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
<style scoped>
.add-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.add-row .form-input { flex: 1; min-width: 220px; font-family: var(--font-mono); font-size: 0.85rem; }
.coa-list { display: flex; flex-direction: column; }
.coa-row { display: flex; justify-content: space-between; padding: 6px 8px; font-size: 0.85rem; border-bottom: 1px solid var(--gray-100); }
.coa-row:hover { background: var(--gray-50); }
.coa-name { font-family: monospace; font-size: 0.82rem; }
.coa-balance { font-weight: 600; }
.coa-balance.negative { color: var(--danger); }
</style>
