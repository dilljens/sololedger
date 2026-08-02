<template>
  <div class="page">
    <div class="page-header">
      <h1>📥 Import Center</h1>
      <p>Import transactions from your bank, CSV files, and more</p>
    </div>
    <div class="import-tabs">
      <button v-for="tab in tabs" :key="tab.id" class="tab-btn" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">
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
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { apiUpload } from '../api.js'
import FileUpload from '../components/FileUpload.vue'

const tabs = [
  { id: 'ofx', label: 'OFX/QFX', icon: '📄' },
  { id: 'citi', label: 'Citi CSV', icon: '💳' },
  { id: 'amazon', label: 'Amazon', icon: '📦' },
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
</style>
