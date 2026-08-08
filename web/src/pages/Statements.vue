<template>
  <div class="page">
    <div class="page-header">
      <h1>📄 Statements</h1>
      <p>Upload and manage bank/credit-card PDF statements</p>
    </div>

    <!-- Upload -->
    <div class="card">
      <h2>Upload Statement</h2>
      <p class="text-muted text-sm">
        Upload a bank or credit card PDF statement. It will be classified by institution
        and filed to the canonical location.
      </p>
      <FileUpload
        accept=".pdf"
        :label="selectedFile ? selectedFile.name : 'Upload PDF statement'"
        icon="📄"
        hint="Supports PDF statements from Wells Fargo, Citi, Chase, Bank of America, Capital One, Amex, US Bank"
        @select="onFileSelect"
        @clear="clearFile"
      />
      <div v-if="selectedFile" class="mt-2">
        <button class="btn btn-primary" @click="upload" :disabled="uploading">
          {{ uploading ? '⏳ Filing...' : '📤 File Statement' }}
        </button>
      </div>
    </div>

    <div v-if="uploadResult" class="card" style="border-left: 4px solid var(--success);">
      <h3>✅ Statement Filed</h3>
      <p v-if="uploadResult.institution">Institution: <strong>{{ uploadResult.institution }}</strong></p>
      <p v-if="uploadResult.period">Period: <strong>{{ uploadResult.period }}</strong></p>
      <p v-if="uploadResult.filed_path">Filed to: <code>{{ uploadResult.filed_path }}</code></p>
      <button class="btn btn-outline btn-sm mt-2" @click="load">🔄 Refresh list</button>
    </div>

    <div v-if="uploadError" class="card error text-center" style="padding: 20px;">
      <p>⚠ {{ uploadError }}</p>
      <button class="btn btn-outline mt-2" @click="uploadError = ''">Dismiss</button>
    </div>

    <!-- Filed statements -->
    <div class="card">
      <div class="statements-head">
        <h2>Filed Statements</h2>
        <button class="btn btn-ghost btn-sm" @click="load" :disabled="loading">🔄 Refresh</button>
      </div>
      <div v-if="loading" class="text-muted text-sm">Loading...</div>
      <div v-else-if="!statements.length" class="empty-state">No statements filed yet.</div>
      <DataTable v-else
        :columns="[
          { key: 'filed_at', label: 'Filed', type: 'date' },
          { key: 'institution', label: 'Institution' },
          { key: 'filename', label: 'File' },
          { key: 'period', label: 'Period' },
          { key: 'page_count', label: 'Pages' },
        ]"
        :rows="statements"
      >
        <template #cell-institution="{ value }"><Tag :color="tagColor(value)">{{ value }}</Tag></template>
        <template #actions="{ row }">
          <a v-if="row.exists" class="btn btn-outline btn-sm" :href="statementHref(row)" target="_blank">📄 Open</a>
          <span v-else class="text-muted text-sm">file missing</span>
        </template>
      </DataTable>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiGet, apiUpload } from '../api.js'
import FileUpload from '../components/FileUpload.vue'
import DataTable from '../components/DataTable.vue'
import Tag from '../components/Tag.vue'

const selectedFile = ref(null)
const uploading = ref(false)
const uploadResult = ref(null)
const uploadError = ref('')

const statements = ref([])
const loading = ref(false)

function onFileSelect(files) {
  selectedFile.value = files && files[0] ? files[0] : files
  uploadResult.value = null
  uploadError.value = ''
}

function clearFile() {
  selectedFile.value = null
}

async function upload() {
  if (!selectedFile.value) return
  uploading.value = true
  uploadError.value = ''
  uploadResult.value = null
  try {
    const data = await apiUpload('/statements/upload', selectedFile.value)
    uploadResult.value = data
    selectedFile.value = null
    load()
  } catch (e) {
    uploadError.value = e.message || 'Upload failed'
  } finally {
    uploading.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const d = await apiGet('/statements')
    statements.value = d.statements || []
  } catch {
    statements.value = []
  } finally {
    loading.value = false
  }
}

function tagColor(institution) {
  const map = { wells_fargo: 'red', citi: 'blue', chase: 'blue', bank_of_america: 'red', capital_one: 'blue', amex: 'green', us_bank: 'yellow' }
  return map[institution] || 'gray'
}

// the filed file is served under the documents/ tree at the app mount
function statementHref(row) {
  return '/app/documents/statements/' + row.path.split('/').map(encodeURIComponent).join('/')
}

onMounted(load)
</script>

<style scoped>
.statements-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
</style>
