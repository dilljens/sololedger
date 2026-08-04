<template>
  <div class="page">
    <div class="page-header">
      <h1>📦 Amazon Orders</h1>
      <p>Import and manage Amazon business orders</p>
    </div>

    <!-- Step 1: Upload -->
    <div class="card" v-if="step === 'upload'">
      <h2>1. Upload Amazon Order History</h2>
      <p class="text-muted text-sm">
        Download your order history from <a href="https://www.amazon.com/hz/order-history" target="_blank">Amazon Order History</a>
        (select time range, then "Download Report") and upload the CSV or ZIP file here.
      </p>

      <FileUpload
        accept=".csv,.zip"
        :label="fileSelected ? fileSelected.name : 'Upload CSV or ZIP'"
        :icon="fileSelected ? '📄' : '📦'"
        hint="Supports Amazon Order History CSV or ZIP containing Order History.csv"
        @select="onFileSelect"
        @clear="clearFile"
      />

      <div v-if="cardFilters.length" class="card-filter-section">
        <FormField
          v-model="selectedCardFilter"
          type="select"
          label="Filter by card (optional)"
          :options="[{value:'', label:'All cards'}, ...cardFilters.map(m => ({value:m, label:`Card ending in ${m}`}))]"
          hint="Only import orders paid with a specific card"
        />
      </div>

      <div v-if="fileSelected" class="mt-3">
        <button class="btn btn-primary" @click="preview" :disabled="previewing">
          {{ previewing ? '⏳ Analyzing...' : '🔍 Preview Import' }}
        </button>
      </div>
    </div>

    <!-- Step 2: Preview -->
    <div class="card" v-if="previewData && step === 'preview'">
      <h2>2. Preview Results</h2>
      <div class="preview-stats">
        <div class="stat-box">
          <span class="stat-number">{{ previewData.order_count }}</span>
          <span class="stat-label">Orders</span>
        </div>
        <div class="stat-box">
          <span class="stat-number">{{ previewData.item_count }}</span>
          <span class="stat-label">Line Items</span>
        </div>
        <div class="stat-box">
          <span class="stat-number">{{ formatCents(previewData.total_cents) }}</span>
          <span class="stat-label">Total</span>
        </div>
      </div>

      <h3 class="mt-3" v-if="previewData.sample_orders?.length">Sample Orders</h3>
      <DataTable
        v-if="previewData.sample_orders?.length"
        :columns="[
          { key: 'source_id', label: 'Order ID' },
          { key: 'date', label: 'Date', type: 'date' },
          { key: 'total_cents', label: 'Total', type: 'cents' },
          { key: 'item_count', label: 'Items' },
        ]"
        :rows="previewData.sample_orders"
      />

      <div class="mt-3 action-row">
        <button class="btn btn-outline" @click="step = 'upload'">← Back</button>
        <button class="btn btn-primary" @click="runImport" :disabled="importing">
          {{ importing ? '⏳ Importing...' : '✅ Confirm Import' }}
        </button>
        <label class="checkbox-label">
          <input type="checkbox" v-model="dryRun" /> Dry run (no changes)
        </label>
      </div>
    </div>

    <!-- Step 3: Results -->
    <div class="card" v-if="result">
      <h2>{{ result.imported > 0 ? '✅ Import Complete' : 'ℹ️ No New Orders' }}</h2>
      <div class="result-grid">
        <div class="result-item"><span class="text-muted">Imported:</span> <strong>{{ result.imported }}</strong></div>
        <div class="result-item"><span class="text-muted">Skipped:</span> <strong>{{ result.skipped }}</strong></div>
        <div class="result-item"><span class="text-muted">Cancelled:</span> <strong>{{ result.cancelled }}</strong></div>
        <div class="result-item"><span class="text-muted">Errors:</span> <strong>{{ result.errors }}</strong></div>
      </div>
      <div v-if="result.warnings?.length" class="warnings">
        <p v-for="w in result.warnings" class="text-warning">{{ w }}</p>
      </div>
      <div class="mt-3 action-row">
        <button class="btn btn-primary" @click="reset">📦 Import Another</button>
        <router-link to="/receipts" class="btn btn-outline">View Receipts</router-link>
      </div>
    </div>

    <!-- Error state -->
    <div v-if="error" class="card error">
      <p>⚠ {{ error }}</p>
      <button class="btn btn-outline btn-sm mt-2" @click="error = ''">Dismiss</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { apiUpload, apiPost } from '../api.js'
import FileUpload from '../components/FileUpload.vue'
import FormField from '../components/FormField.vue'
import DataTable from '../components/DataTable.vue'

const step = ref('upload')
const fileSelected = ref(null)
const selectedCardFilter = ref('')
const cardFilters = ref([])
const previewData = ref(null)
const previewing = ref(false)
const importing = ref(false)
const dryRun = ref(false)
const result = ref(null)
const error = ref('')

function formatCents(cents) {
  if (cents == null) return '$0.00'
  const sign = cents < 0 ? '-' : ''
  return sign + '$' + (Math.abs(cents) / 100).toLocaleString('en-US', { minimumFractionDigits: 2 })
}

function onFileSelect(files) {
  if (files?.length) {
    fileSelected.value = files[0]
    step.value = 'upload'
    previewData.value = null
    result.value = null
  }
}

function clearFile() {
  fileSelected.value = null
  previewData.value = null
  result.value = null
  step.value = 'upload'
}

async function preview() {
  if (!fileSelected.value) return
  previewing.value = true
  error.value = ''
  try {
    const data = await apiUpload('/import/amazon/preview', fileSelected.value)
    previewData.value = data
    cardFilters.value = data.payment_masks || []
    step.value = 'preview'
  } catch (err) {
    error.value = err.message || 'Preview failed'
  } finally {
    previewing.value = false
  }
}

async function runImport() {
  importing.value = true
  error.value = ''
  try {
    const formData = new FormData()
    formData.append('file', fileSelected.value)
    formData.append('card_filter', selectedCardFilter.value)
    formData.append('dry_run', dryRun.value ? 'true' : 'false')
    const data = await apiPost('/import/amazon/import', formData)
    result.value = data
    step.value = 'upload'  // results shown in their own card
  } catch (err) {
    error.value = err.message || 'Import failed'
  } finally {
    importing.value = false
  }
}

function reset() {
  fileSelected.value = null
  previewData.value = null
  result.value = null
  error.value = ''
  step.value = 'upload'
  selectedCardFilter.value = ''
  dryRun.value = false
}
</script>

<style scoped>
.preview-stats {
  display: flex; gap: 16px; margin: 16px 0;
}
.stat-box {
  display: flex; flex-direction: column; align-items: center;
  padding: 16px 24px; background: var(--gray-50); border-radius: 8px; min-width: 100px;
}
.stat-number { font-size: 1.5rem; font-weight: 700; color: var(--gray-900); }
.stat-label { font-size: 0.8rem; color: var(--gray-500); margin-top: 4px; }

.action-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }

.result-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin: 12px 0; }
.result-item { padding: 12px; background: var(--gray-50); border-radius: 6px; }

.warnings { margin-top: 12px; }
.text-warning { color: var(--warning); font-size: 0.85rem; }

.card-filter-section { margin-top: 12px; max-width: 300px; }

.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 0.85rem; cursor: pointer; }
</style>
