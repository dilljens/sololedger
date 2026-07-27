<template>
  <div class="modal-overlay" :class="{ visible: isOpen }" @click="close">
    <div class="modal auth-modal" @click.stop>
      <div class="modal-header">
        <h3 id="auth-modal-title">{{ isSignUp ? 'Create Account' : 'Sign In' }}</h3>
        <button class="icon-btn" @click="close">✕</button>
      </div>
      <form @submit.prevent="submit">
        <div class="modal-body">
          <div class="form-group">
            <label for="auth-email">Email</label>
            <input
              id="auth-email"
              v-model="email"
              type="email"
              class="form-input"
              placeholder="you@example.com"
              required
              autocomplete="email"
            />
          </div>
          <div class="form-group">
            <label for="auth-password">Password</label>
            <input
              id="auth-password"
              v-model="password"
              type="password"
              class="form-input"
              placeholder="Min 8 characters"
              required
              autocomplete="current-password"
              minlength="8"
            />
          </div>
          <div v-if="error" class="alert alert-error" role="alert">{{ error }}</div>
        </div>
        <div class="modal-footer">
          <button type="submit" class="btn btn-primary" :disabled="submitting">
            {{ submitting ? '⏳' : (isSignUp ? 'Create Account' : 'Sign In') }}
          </button>
          <p class="text-sm text-muted" style="margin-top: 8px;">
            {{ isSignUp ? 'Already have an account?' : "Don't have an account?" }}
            <a href="#" @click.prevent="toggleMode">{{ isSignUp ? 'Sign In' : 'Sign Up' }}</a>
          </p>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { apiPost, setAuthToken, isAuthenticated } from '../api.js'

const isOpen = ref(false)
const isSignUp = ref(false)
const email = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)

let listener = null

onMounted(() => {
  listener = () => { isOpen.value = true; error.value = '' }
  document.addEventListener('show-auth-modal', listener)
})

onUnmounted(() => {
  if (listener) document.removeEventListener('show-auth-modal', listener)
})

function close() {
  isOpen.value = false
  error.value = ''
}

function toggleMode() {
  isSignUp.value = !isSignUp.value
  error.value = ''
}

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    const endpoint = isSignUp.value ? '/auth/signup' : '/auth/signin'
    const data = await apiPost(endpoint, { email: email.value, password: password.value })
    setAuthToken(data.token)
    localStorage.setItem('user_email', email.value)
    close()
    window.location.reload()
  } catch (err) {
    error.value = err.data?.error || err.message || 'Authentication failed'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.auth-modal {
  max-width: 420px;
}

.alert-error {
  background: #fef2f2;
  color: #dc2626;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  margin-top: 12px;
}
</style>
