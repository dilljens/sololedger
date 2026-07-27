<template>
  <div class="page">
    <div class="page-header">
      <h1>💰 Tax Estimate</h1>
      <p>Estimated taxes for your business</p>
    </div>
    <div v-if="loading" class="loading"><div class="spinner"></div>Loading...</div>
    <div v-else-if="error" class="card error text-center" style="padding:40px;">
      <p>{{ error }}</p>
      <button class="btn btn-primary mt-3" @click="load">🔄 Retry</button>
    </div>
    <template v-else>
      <div class="card">
        <h2>Summary</h2>
        <div class="tax-summary">
          <div class="tax-row"><span>Entity</span><strong>{{ data.entity_type }} ({{ data.entity_label }})</strong></div>
          <div class="tax-row"><span>YTD Net Profit</span><strong>{{ fmt(data.ytd_net_profit) }}</strong></div>
          <div class="tax-row"><span>Projected Annual Net</span><strong>{{ fmt(data.projected_annual_net) }}</strong></div>
          <div class="tax-row" v-if="data.self_employment_tax"><span>Self-Employment Tax</span><strong>{{ fmt(data.self_employment_tax.total) }}</strong></div>
          <div class="tax-row" v-if="data.federal_income_tax"><span>Federal Income Tax</span><strong>{{ fmt(data.federal_income_tax.total) }}</strong></div>
          <div class="tax-row"><span>Total Est. Tax</span><strong class="text-primary">{{ fmt(data.total_estimated_tax) }}</strong></div>
          <div class="tax-row"><span>Already Paid</span><strong>{{ fmt(data.already_paid) }}</strong></div>
          <div class="tax-row"><span>Suggested Next Payment</span><strong class="text-primary">{{ fmt(data.suggested_next_payment) }}</strong></div>
        </div>
        <p v-if="data.note" class="text-muted text-sm mt-3">{{ data.note }}</p>
        <p class="text-xs text-muted mt-2">{{ data.disclaimer }}</p>
      </div>
    </template>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import { apiGet } from '../api.js'
const loading = ref(true); const error = ref(''); const data = ref(null)
function fmt(v) { return v != null ? '$' + Number(v).toLocaleString('en-US', {minimumFractionDigits:2}) : '$0.00' }
async function load() {
  loading.value = true; error.value = ''
  try { data.value = await apiGet('/tax/estimate') }
  catch (e) { error.value = e.message }
  finally { loading.value = false }
}
onMounted(load)
</script>
<style scoped>
.tax-summary { display: flex; flex-direction: column; gap: 8px; }
.tax-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--gray-100); font-size: 0.9rem; }
.tax-row:last-child { border-bottom: none; }
</style>
