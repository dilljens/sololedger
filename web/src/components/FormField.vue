<template>
  <div class="form-group" :class="{ inline }">
    <label v-if="label" :for="inputId" class="form-label">{{ label }}
      <span v-if="required" class="required-mark">*</span>
    </label>
    <div class="form-control-wrap">
      <!-- Text input -->
      <input v-if="type === 'text' || type === 'email' || type === 'password' || type === 'number' || type === 'date'"
        :id="inputId" :type="type" :value="modelValue"
        @input="$emit('update:modelValue', $event.target.value)"
        :placeholder="placeholder" :required="required" :disabled="disabled"
        class="form-input" :class="{ 'input-error': error }"
        :min="min" :max="max" :step="step"
      />
      <!-- Select -->
      <select v-else-if="type === 'select'"
        :id="inputId" :value="modelValue"
        @change="$emit('update:modelValue', $event.target.value)"
        :required="required" :disabled="disabled"
        class="form-input">
        <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
        <option v-for="opt in options" :key="opt.value || opt" :value="opt.value || opt">
          {{ opt.label || opt }}
        </option>
      </select>
      <!-- Textarea -->
      <textarea v-else-if="type === 'textarea'"
        :id="inputId" :value="modelValue"
        @input="$emit('update:modelValue', $event.target.value)"
        :placeholder="placeholder" :required="required" :disabled="disabled"
        class="form-input" :rows="rows"
      ></textarea>
      <!-- Checkbox -->
      <label v-else-if="type === 'checkbox'" class="checkbox-label">
        <input type="checkbox" :checked="modelValue"
          @change="$emit('update:modelValue', $event.target.checked)"
          :disabled="disabled" /> {{ placeholder }}
      </label>
      <!-- Toggle switch -->
      <label v-else-if="type === 'toggle'" class="toggle-label">
        <span class="toggle-track" :class="{ active: modelValue }">
          <span class="toggle-thumb"></span>
        </span>
        <input type="checkbox" :checked="modelValue"
          @change="$emit('update:modelValue', $event.target.checked)"
          class="toggle-input" />
      </label>
      <span v-if="hint" class="form-hint">{{ hint }}</span>
      <span v-if="error" class="form-error">{{ error }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number, Boolean, Array], default: '' },
  type: { type: String, default: 'text' },
  label: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  required: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  inline: { type: Boolean, default: false },
  error: { type: String, default: '' },
  hint: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  rows: { type: Number, default: 3 },
  min: { type: [Number, String], default: undefined },
  max: { type: [Number, String], default: undefined },
  step: { type: String, default: undefined },
})

const emit = defineEmits(['update:modelValue'])

let idCounter = 0
const inputId = computed(() => `field-${++idCounter}`)
</script>

<style scoped>
.form-group { margin-bottom: 16px; }
.form-group.inline { display: flex; align-items: center; gap: 12px; }
.form-label { display: block; font-size: 0.85rem; font-weight: 500; color: var(--gray-700); margin-bottom: 4px; }
.required-mark { color: #dc2626; margin-left: 2px; }
.form-hint { display: block; font-size: 0.78rem; color: var(--gray-400); margin-top: 2px; }
.form-error { display: block; font-size: 0.78rem; color: #dc2626; margin-top: 2px; }
.input-error { border-color: #dc2626 !important; }

.checkbox-label { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; cursor: pointer; }

.toggle-input { display: none; }
.toggle-track {
  display: inline-block; width: 36px; height: 20px; background: var(--gray-300);
  border-radius: 10px; position: relative; cursor: pointer; transition: background 0.2s;
}
.toggle-track.active { background: var(--primary); }
.toggle-thumb {
  position: absolute; top: 2px; left: 2px; width: 16px; height: 16px;
  background: white; border-radius: 50%; transition: transform 0.2s;
}
.toggle-track.active .toggle-thumb { transform: translateX(16px); }
</style>
