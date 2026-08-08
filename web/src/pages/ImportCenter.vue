<template>
  <div class="page">
    <div class="page-header">
      <h1>📥 Import Center</h1>
      <p>Import transactions from your bank, CSV files, and more</p>
    </div>
    <div class="import-tabs">
      <button v-for="tab in tabs" :key="tab.id" class="tab-btn" :class="{ active: activeTab === tab.id }" @click="onTabChange(tab.id); activeTab = tab.id">
        {{ tab.icon }} {{ tab.label }}
      </button>
    </div>

    <!-- OFX Upload -->
    <div v-if="activeTab === 'ofx'" class="card">
      <h2>📄 OFX/QFX Bank Statement</h2>
      <p class="text-muted text-sm mb-3">Upload an OFX or QFX file from your bank.</p>
      <FileUpload accept=".ofx,.qfx" label="Choose OFX/QFX File" icon="📄" @select="onOfxSelect" @clear="clearOfx" />
      <div v-if="ofxFile" class="mt-2">
        <button class="btn btn-primary" @click="previewOfx" :disabled="previewing">
          {{ previewing ? '⏳ Previewing...' : '👁️ Preview Import' }}
        </button>
        <button v-if="ofxPreview" class="btn btn-success" @click="confirmOfx" :disabled="confirming">
          {{ confirming ? '⏳ Importing...' : '✅ Confirm Import' }}
        </button>
      </div>
      <div v-if="ofxPreview" class="mt-3">
        <div class="bg-success border-success" style="padding:12px;border-radius:8px;">
          Preview: {{ ofxPreview.imported }} of {{ ofxPreview.total }} would import
          <span v-if="ofxPreview.skipped_duplicates" class="text-muted-light"> ({{ ofxPreview.skipped_duplicates }} duplicates)</span>
        </div>
      </div>
      <div v-if="ofxResult" class="mt-3">
        <div class="bg-success border-success" style="padding:12px;border-radius:8px;">
          ✅ {{ ofxResult.imported }} of {{ ofxResult.total }} imported
          <span v-if="ofxResult.skipped_duplicates" class="text-muted-light"> ({{ ofxResult.skipped_duplicates }} duplicates skipped)</span>
        </div>
      </div>
      <div v-if="ofxError" class="card error mt-3">⚠ {{ ofxError }}</div>
    </div>

    <!-- Citi CSV -->
    <div v-if="activeTab === 'citi'" class="card">
      <h2>💳 Citi Credit Card CSV</h2>
      <p class="text-muted text-sm mb-3">Upload a Citi credit-card statement CSV.</p>
      <FileUpload accept=".csv" label="Upload Citi CSV" icon="💳" @select="onCitiSelect" @clear="clearCiti" />
      <div v-if="citiFile" class="mt-2">
        <button class="btn btn-primary" @click="previewCiti" :disabled="previewingCiti">
          {{ previewingCiti ? '⏳ Previewing...' : '👁️ Preview Import' }}
        </button>
        <button v-if="citiPreview" class="btn btn-success" @click="confirmCiti" :disabled="confirmingCiti">
          {{ confirmingCiti ? '⏳ Importing...' : '✅ Confirm Import' }}
        </button>
      </div>
      <div v-if="citiPreview" class="mt-3">
        <p class="text-muted">{{ citiPreview.total }} transactions found</p>
      </div>
      <div v-if="citiResult" class="mt-3">
        <div class="bg-success border-success" style="padding:12px;border-radius:8px;">
          ✅ Import complete: {{ citiResult.imported }} transactions imported
          <span v-if="citiResult.skipped" class="text-muted-light"> ({{ citiResult.skipped }} duplicates skipped)</span>
        </div>
      </div>
      <div v-if="citiError" class="card error mt-3">⚠ {{ citiError }}</div>
    </div>

    <!-- Amazon -->
    <div v-if="activeTab === 'amazon'" class="card">
      <h2>📦 Amazon Orders</h2>
      <p class="text-muted text-sm mb-3">Import Amazon business orders.</p>
      <router-link to="/amazon" class="btn btn-primary">Open Amazon Import →</router-link>
    </div>

    <!-- Import history -->
    <div v-if="activeTab === 'history'" class="card">
      <div class="history-head">
        <h2>🕘 Import History</h2>
        <div class="history-actions">
          <label class="dup-toggle">
            <input type="checkbox" v-model="showDuplicates" @change="loadHistory" />
            <span>Show cross-source duplicates</span>
          </label>
          <button class="btn btn-ghost btn-sm" @click="loadHistory" :disabled="historyLoading">
            {{ historyLoading ? '⏳' : '🔄 Refresh' }}
          </button>
        </div>
      </div>

      <template v-if="showDuplicates">
        <p class="text-muted text-sm">
          Transactions seen from more than one import source — same fingerprint,
          different source. They were not double-posted; this is the review list.
        </p>
        <div v-if="!duplicates.length" class="empty-state">No cross-source duplicates flagged.</div>
        <DataTable v-else
          :columns="[
            { key: 'description', label: 'Description' },
            { key: 'existing_source', label: 'First Seen From' },
            { key: 'attempted_sources', label: 'Also From' },
            { key: 'attempts', label: 'Attempts' },
            { key: 'latest_date', label: 'Latest Date' },
          ]"
          :rows="duplicates.map(d => ({ ...d, attempted_sources: (d.attempted_sources || '').split(',').join(', ') }))"
        />
      </template>

      <template v-else>
        <div v-if="!batches.length" class="empty-state">No imports recorded yet.</div>
        <DataTable v-else
          :columns="[
            { key: 'id', label: '#' },
            { key: 'created_at', label: 'When' },
            { key: 'source', label: 'Source' },
            { key: 'filename', label: 'File' },
            { key: 'status', label: 'Status' },
          ]"
          :rows="batches"
        >
          <template #cell-status="{ value }"><StatusBadge :status="value" /></template>
        </DataTable>
      </template>
    </div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { apiGet, apiUpload } from '../api.js'
import FileUpload from '../components/FileUpload.vue'
import DataTable from '../components/DataTable.vue'
import StatusBadge from '../components/StatusBadge.vue'

const tabs = [
  { id: 'ofx', label: 'OFX/QFX', icon: '📄' },
  { id: 'citi', label: 'Citi CSV', icon: '💳' },
  { id: 'amazon', label: 'Amazon', icon: '📦' },
  { id: 'history', label: 'History', icon: '🕘' },
]
const activeTab = ref('ofx')
const ofxFile = ref(null)
const ofxPreview = ref(null)
const ofxResult = ref(null)
const ofxError = ref('')
const previewing = ref(false)
const confirming = ref(false)
const citiFile = ref(null)
const citiPreview = ref(null)
const citiResult = ref(null)
const citiError = ref('')
const previewingCiti = ref(false)
const confirmingCiti = ref(false)

const batches = ref([])
const duplicates = ref([])
const showDuplicates = ref(false)
const historyLoading = ref(false)

// Load history the first time the History tab is opened
let historyLoaded = false
async function onTabChange(tab) {
  if (tab === 'history' && !historyLoaded) {
    historyLoaded = true
    await loadHistory()
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    if (showDuplicates.value) {
      const d = await apiGet('/import/duplicates')
      duplicates.value = d.duplicates || []
    } else {
      const h = await apiGet('/import/history')
      batches.value = h.batches || []
    }
  } catch (e) {
    // surface quietly: keep the last data, just don't crash the page
    console.error('Failed to load import history:', e.message)
  } finally {
    historyLoading.value = false
  }
}

function firstFile(files) {
  return files && files[0] ? files[0] : files
}

function onOfxSelect(files) {
  ofxFile.value = firstFile(files)
  ofxPreview.value = null
  ofxResult.value = null
  ofxError.value = ''
}

function clearOfx() {
  ofxFile.value = null
  ofxPreview.value = null
  ofxResult.value = null
  ofxError.value = ''
}

async function previewOfx() {
  if (!ofxFile.value) return
  previewing.value = true
  ofxError.value = ''
  ofxPreview.value = null
  ofxResult.value = null
  try {
    ofxPreview.value = await apiUpload('/import/ofx', ofxFile.value, { preview: 'true' })
  } catch (e) {
    ofxError.value = e.message
  } finally {
    previewing.value = false
  }
}

async function confirmOfx() {
  if (!ofxFile.value) return
  confirming.value = true
  ofxError.value = ''
  try {
    ofxResult.value = await apiUpload('/import/ofx', ofxFile.value, { preview: 'false' })
    ofxPreview.value = null
  } catch (e) {
    ofxError.value = e.message
  } finally {
    confirming.value = false
  }
}

function onCitiSelect(files) {
  citiFile.value = firstFile(files)
  citiPreview.value = null
  citiResult.value = null
  citiError.value = ''
}

function clearCiti() {
  citiFile.value = null
  citiPreview.value = null
  citiResult.value = null
  citiError.value = ''
}

async function previewCiti() {
  if (!citiFile.value) return
  previewingCiti.value = true
  citiError.value = ''
  citiResult.value = null
  try {
    citiPreview.value = await apiUpload('/import/citi/preview', citiFile.value)
  } catch (e) {
    citiError.value = e.message
  } finally {
    previewingCiti.value = false
  }
}

async function confirmCiti() {
  if (!citiFile.value) return
  confirmingCiti.value = true
  citiError.value = ''
  try {
    citiResult.value = await apiUpload('/import/citi/import', citiFile.value, {
      account: 'citi',
      dry_run: 'false',
    })
    citiPreview.value = null
  } catch (e) {
    citiError.value = e.message
  } finally {
    confirmingCiti.value = false
  }
}
</script>
<style scoped>
.import-tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
.tab-btn { padding: 8px 16px; border-radius: 6px; border: 1px solid var(--gray-200); background: transparent; cursor: pointer; font-size: 0.85rem; font-weight: 500; }
.tab-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.tab-btn:hover:not(.active) { background: var(--gray-50); }
.history-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.history-actions { display: flex; align-items: center; gap: 12px; }
.dup-toggle { display: inline-flex; align-items: center; gap: 6px; font-size: 0.8rem; color: var(--gray-600); cursor: pointer; }
.dup-toggle input { accent-color: var(--primary); }
</style>
