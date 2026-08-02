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

    <div v-if="uploadResult" class="card" style="border-left: 4px solid var(--green-500);">
      <h3>✅ Statement Filed</h3>
      <p v-if="uploadResult.institution">Institution: <strong>{{ uploadResult.institution }}</strong></p>
      <p v-if="uploadResult.period">Period: <strong>{{ uploadResult.period }}</strong></p>
      <p v-if="uploadResult.path">Filed to: <code>{{ uploadResult.path }}</code></p>
    </div>

    <div v-if="uploadError" class="card error text-center" style="padding: 20px;">
      <p>⚠ {{ uploadError }}</p>
      <button class="btn btn-outline mt-2" @click="uploadError = ''">Dismiss</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { apiUpload } from '../api.js'
import FileUpload from '../components/FileUpload.vue'

const selectedFile = ref(null)
const uploading = ref(false)
const uploadResult = ref(null)
const uploadError = ref('')

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
    const data = await apiUpload('/statement/file', selectedFile.value)
    uploadResult.value = data
    selectedFile.value = null
  } catch (e) {
    uploadError.value = e.message || 'Upload failed'
  } finally {
    uploading.value = false
  }
}
</script>
