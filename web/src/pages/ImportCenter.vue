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
      <FileUpload accept=".ofx,.qfx" label="Choose OFX/QFX File" icon="📄" @select="uploadOfx" />
      <div v-if="ofxResult" class="mt-3">
        <div class="bg-success border-success" style="padding:12px;border-radius:8px;">
          ✅ {{ ofxResult.imported }} of {{ ofxResult.total }} imported
          <span v-if="ofxResult.skipped_duplicates" class="text-muted-light"> ({{ ofxResult.skipped_duplicates }} duplicates skipped)</span>
        </div>
      </div>
    </div>

    <!-- Citi CSV -->
    <div v-if="activeTab === 'citi'" class="card">
      <h2>💳 Citi Credit Card CSV</h2>
      <p class="text-muted text-sm mb-3">Upload a Citi credit-card statement CSV.</p>
      <FileUpload accept=".csv" label="Upload Citi CSV" icon="💳" @select="uploadCiti" />
      <div v-if="citiPreview" class="mt-3">
        <p class="text-muted">{{ citiPreview.total }} transactions found</p>
        <button class="btn btn-primary btn-sm" @click="confirmCiti">Confirm Import</button>
      </div>
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
import { apiUpload, apiPost } from '../api.js'
import FileUpload from '../components/FileUpload.vue'

const tabs = [
  { id: 'ofx', label: 'OFX/QFX', icon: '📄' },
  { id: 'citi', label: 'Citi CSV', icon: '💳' },
  { id: 'amazon', label: 'Amazon', icon: '📦' },
]
const activeTab = ref('ofx')
const ofxResult = ref(null)
const citiPreview = ref(null)

async function uploadOfx(files) {
  if (!files?.length) return
  try {
    ofxResult.value = await apiUpload('/import/ofx', files[0], { preview: 'true' })
  } catch (e) {
    ofxResult.value = { error: e.message }
  }
}

async function uploadCiti(files) {
  if (!files?.length) return
  try {
    citiPreview.value = await apiUpload('/import/citi/preview', files[0])
  } catch (e) {
    citiPreview.value = { error: e.message }
  }
}

async function confirmCiti() {
  // Re-upload with import
}
</script>
<style scoped>
.import-tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
.tab-btn { padding: 8px 16px; border-radius: 6px; border: 1px solid var(--gray-200); background: transparent; cursor: pointer; font-size: 0.85rem; font-weight: 500; }
.tab-btn.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.tab-btn:hover:not(.active) { background: var(--gray-50); }
</style>
