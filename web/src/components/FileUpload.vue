<template>
  <div class="file-upload" :class="{ dragged: isDragging }"
       @dragover.prevent="isDragging = true"
       @dragleave="isDragging = false"
       @drop.prevent="handleDrop">
    <input
      type="file"
      :accept="accept"
      :multiple="multiple"
      ref="fileInput"
      class="file-input-hidden"
      @change="$emit('select', $event.target.files)"
    />
    <div class="upload-area" @click="$refs.fileInput?.click()">
      <slot name="trigger">
        <span class="upload-icon">{{ icon }}</span>
        <span class="upload-text">{{ label }}</span>
        <span v-if="hint" class="upload-hint">{{ hint }}</span>
      </slot>
    </div>
    <div v-if="preview && selectedFile" class="upload-preview">
      <span class="file-name">{{ selectedFile.name }}</span>
      <span class="file-size">({{ formatSize(selectedFile.size) }})</span>
      <button class="btn btn-ghost btn-sm" @click.stop="clear">✕</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  accept: { type: String, default: '' },
  multiple: { type: Boolean, default: false },
  label: { type: String, default: 'Choose File' },
  icon: { type: String, default: '📄' },
  hint: { type: String, default: '' },
  preview: { type: Boolean, default: true },
})

const emit = defineEmits(['select', 'clear'])

const isDragging = ref(false)
const fileInput = ref(null)
const selectedFile = ref(null)

function handleDrop(e) {
  isDragging.value = false
  const files = e.dataTransfer.files
  if (files.length) {
    selectedFile.value = files[0]
    emit('select', files)
  }
}

function clear() {
  selectedFile.value = null
  if (fileInput.value) fileInput.value.value = ''
  emit('clear')
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.file-upload { margin-bottom: 12px; }
.file-input-hidden { display: none; }
.upload-area {
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 24px; border: 2px dashed var(--gray-300); border-radius: 8px;
  cursor: pointer; transition: border-color 0.15s, background 0.15s;
}
.upload-area:hover, .dragged .upload-area { border-color: var(--primary); background: var(--primary-bg, #eff6ff); }
.upload-icon { font-size: 2rem; }
.upload-text { font-weight: 600; color: var(--gray-700); }
.upload-hint { font-size: 0.8rem; color: var(--gray-400); }
.upload-preview {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  background: var(--gray-50); border-radius: 6px; margin-top: 8px;
  font-size: 0.85rem;
}
.file-name { font-weight: 500; max-width: 300px; overflow: hidden; text-overflow: ellipsis; }
.file-size { color: var(--gray-400); }
</style>
