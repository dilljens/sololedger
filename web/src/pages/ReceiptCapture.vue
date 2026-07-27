<template>
  <div class="page">
    <div class="page-header">
      <h1>📸 Capture Receipt</h1>
      <p>Take a photo or upload a receipt — it will be scanned and attached to your ledger</p>
    </div>

    <!-- Step 1: Upload -->
    <div class="card" v-if="step === 'upload'">
      <h2>1. Choose Receipt</h2>
      <FileUpload
        accept="image/*,.pdf"
        :label="selectedFile ? selectedFile.name : 'Upload receipt image or PDF'"
        :icon="selectedFile ? '🧾' : '📸'"
        hint="Supports JPG, PNG, TIFF, BMP, and PDF up to 10MB"
        @select="onFileSelect"
        @clear="clearFile"
      />
      <button
        v-if="selectedFile"
        class="btn btn-primary mt-3"
        @click="scan"
        :disabled="scanning"
      >
        {{ scanning ? '⏳ Scanning...' : '🔍 Scan Receipt' }}
      </button>
    </div>

    <!-- Scanning -->
    <div v-if="scanning" class="card text-center" style="padding: 40px;">
      <div class="spinner"></div>
      <p class="mt-2">Scanning receipt...</p>
    </div>

    <!-- Step 2: Results -->
    <div v-if="result && step === 'results'" class="card">
      <h2>2. Scan Result</h2>
      <div v-if="result.success" class="scan-success">
        <div class="result-grid">
          <div class="result-field">
            <span class="result-label">Merchant</span>
            <span class="result-value">{{ result.merchant || 'Unknown' }}</span>
          </div>
          <div class="result-field">
            <span class="result-label">Date</span>
            <span class="result-value">{{ result.date || 'Unknown' }}</span>
          </div>
          <div class="result-field">
            <span class="result-label">Total</span>
            <span class="result-value">{{ formatCents(result.total) }}</span>
          </div>
          <div v-if="result.appended" class="result-field">
            <span class="result-label">Status</span>
            <span class="tag tag-green">Appended to ledger</span>
          </div>
        </div>
        <div v-if="result.line_items?.length" class="mt-3">
          <h3>Line Items</h3>
          <DataTable
            :columns="[
              { key: 'description', label: 'Description' },
              { key: 'amount', label: 'Amount', type: 'cents' },
            ]"
            :rows="result.line_items.map(i => ({ ...i, amount: toCents(i.amount) }))"
          />
        </div>
      </div>
      <div v-else class="scan-error">
        <p>⚠ {{ result.error || 'Could not extract text from this receipt.' }}</p>
        <p class="text-muted text-sm mt-2">Try a clearer image or PDF. The receipt scanner works best with printed text.</p>
      </div>
      <div class="mt-3 action-row">
        <button class="btn btn-outline" @click="reset">← Scan Another</button>
        <a v-if="!result.appended" :href="result.path ? `/app/#receipts` : '#'" class="btn btn-primary">
          ✅ Done
        </a>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="card error text-center" style="padding: 30px;">
      <p>⚠ {{ error }}</p>
      <button class="btn btn-outline mt-3" @click="reset">← Try Again</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { apiUpload } from '../api.js'
import FileUpload from '../components/FileUpload.vue'
import DataTable from '../components/DataTable.vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const step = ref('upload')
const selectedFile = ref(null)
const scanning = ref(false)
const result = ref(null)
const error = ref('')

function onFileSelect(file) {
  selectedFile.value = file
  step.value = 'upload'
  result.value = null
  error.value = ''
}

function clearFile() {
  selectedFile.value = null
}

function toCents(amount) {
  if (amount == null) return 0
  return Math.round(Math.abs(amount) * 100)
}

function formatCents(cents) {
  if (cents == null) return '—'
  const abs = Math.abs(cents) / 100
  return (cents < 0 ? '-' : '') + '$' + abs.toFixed(2)
}

async function scan() {
  if (!selectedFile.value) return
  scanning.value = true
  error.value = ''
  try {
    const data = await apiUpload('/receipts/scan', selectedFile.value, { preview: 'true' })
    result.value = data
    step.value = 'results'
  } catch (e) {
    error.value = e.message || 'Scan failed'
  } finally {
    scanning.value = false
  }
}

function reset() {
  step.value = 'upload'
  selectedFile.value = null
  result.value = null
  error.value = ''
}
</script>

<style scoped>
.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
}
.result-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.result-label {
  font-size: 0.75rem;
  color: var(--gray-500);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.result-value {
  font-size: 1.1rem;
  font-weight: 600;
}
.scan-success { padding: 8px 0; }
.scan-error { padding: 16px; background: var(--red-50); border-radius: 8px; }
.action-row { display: flex; gap: 12px; align-items: center; }
</style>
