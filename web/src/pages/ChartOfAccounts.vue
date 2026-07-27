<template>
  <div class="page">
    <div class="page-header">
      <h1>📊 Chart of Accounts</h1>
      <p>All accounts in your ledger with current balances</p>
    </div>
    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>
    <div v-else-if="error" class="card error">⚠ {{ error }}</div>
    <template v-else>
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
import { apiGet } from '../api.js'
const loading = ref(true); const error = ref(''); const tree = ref([])
function formatMoney(v) { return '$' + Math.abs(v).toFixed(2) }
onMounted(async () => {
  try { const d = await apiGet('/coa/tree'); tree.value = d.tree } catch (e) { error.value = e.message }
  finally { loading.value = false }
})
</script>
<style scoped>
.coa-list { display: flex; flex-direction: column; }
.coa-row { display: flex; justify-content: space-between; padding: 6px 8px; font-size: 0.85rem; border-bottom: 1px solid var(--gray-100); }
.coa-row:hover { background: var(--gray-50); }
.coa-name { font-family: monospace; font-size: 0.82rem; }
.coa-balance { font-weight: 600; }
.coa-balance.negative { color: #dc2626; }
</style>
