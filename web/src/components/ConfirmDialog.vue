<template>
  <div v-if="modelValue" class="confirm-overlay" @click.self="close">
    <div class="confirm-modal" role="dialog" aria-modal="true" :aria-label="title">
      <h3>{{ title }}</h3>
      <p>{{ message }}</p>
      <div class="confirm-actions">
        <button class="btn btn-ghost" @click="close">{{ cancelText }}</button>
        <button class="btn" :class="danger ? 'btn-danger' : 'btn-primary'"
                autofocus @click="confirm">{{ confirmText }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: 'Confirm' },
  message: { type: String, default: 'Are you sure?' },
  confirmText: { type: String, default: 'Confirm' },
  cancelText: { type: String, default: 'Cancel' },
  danger: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'confirm', 'cancel'])

function close() {
  emit('update:modelValue', false)
  emit('cancel')
}
function confirm() {
  emit('update:modelValue', false)
  emit('confirm')
}
</script>
