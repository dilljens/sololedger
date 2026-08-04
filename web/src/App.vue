<template>
  <div class="app-shell">
    <!-- Loading bar -->
    <div class="loading-bar" :class="{ visible: isLoading }"></div>

    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="logo">Solo<span>Ledger</span></div>
      <nav aria-label="Main navigation">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="sidebar-link"
          :class="{ active: isActive(item.path) }"
          :aria-label="item.label"
        >
          <span aria-hidden="true">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <button class="icon-btn" @click="toggleTheme" :title="themeLabel">
          {{ themeIcon }}
        </button>
        <div v-if="isAuthenticated" class="sidebar-user">
          <span class="user-email">{{ userEmail }}</span>
          <button class="btn btn-ghost btn-sm" @click="handleLogout" title="Sign out">🚪</button>
        </div>
        <button v-else class="btn btn-ghost btn-sm" @click="showAuthModal">🔑 Sign In</button>
        <div class="version">v0.4.0 · MIT</div>
      </div>
    </aside>

    <!-- Main content -->
    <main class="main-content" id="page-content">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Mobile bottom nav -->
    <nav class="mobile-nav" aria-label="Mobile navigation">
      <router-link
        v-for="item in mobileNavItems"
        :key="item.path"
        :to="item.path"
        class="mobile-nav-link"
        :class="{ active: isActive(item.path) }"
      >
        <span aria-hidden="true">{{ item.icon }}</span>
        <span class="mobile-nav-label">{{ item.shortLabel }}</span>
      </router-link>
      <button class="mobile-nav-link mobile-more-btn" @click="toggleMobileDrawer">
        <span>☰</span>
        <span class="mobile-nav-label">More</span>
      </button>
    </nav>

    <!-- Mobile drawer -->
    <teleport to="body">
      <div class="mobile-drawer-overlay" :class="{ visible: mobileDrawerOpen }" @click="closeMobileDrawer">
        <div class="mobile-drawer" @click.stop>
          <div class="mobile-drawer-header">
            <span style="font-weight:600;">All Pages</span>
            <button class="icon-btn" @click="closeMobileDrawer">✕</button>
          </div>
          <div class="mobile-drawer-items">
            <router-link
              v-for="item in navItems"
              :key="item.path"
              :to="item.path"
              class="mobile-drawer-item"
              @click="closeMobileDrawer"
            >
              <span aria-hidden="true">{{ item.icon }}</span>
              {{ item.label }}
            </router-link>
          </div>
        </div>
      </div>
    </teleport>

    <!-- Auth modal -->
    <AuthModal ref="authModal" />

    <!-- Toast container -->
    <div id="toast-container" class="toast-container"></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthModal from './components/AuthModal.vue'
import { isAuthenticated, getAuthToken, clearAuth, apiGet } from './api.js'

const route = useRoute()
const router = useRouter()

// ── Nav items ──────────────────────────────────────────────────────

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: '📊' },
  { path: '/accounts', label: 'Accounts', icon: '🏦' },
  { path: '/import', label: 'Import', icon: '📥' },
  { path: '/invoices', label: 'Invoices', icon: '📄' },
  { path: '/new-invoice', label: 'New Inv.', icon: '➕' },
  { path: '/transactions', label: 'Transactions', icon: '📋' },
  { path: '/receipts', label: 'Receipts', icon: '🧾' },
  { path: '/categorize', label: 'Categorize', icon: '🏷️' },
  { path: '/tax', label: 'Tax', icon: '💰' },
  { path: '/deadlines', label: 'Deadlines', icon: '📅' },
  { path: '/mileage', label: 'Mileage', icon: '🚗' },
  { path: '/amazon', label: 'Amazon', icon: '📦' },
  { path: '/coa', label: 'Chart', icon: '📊' },
  { path: '/rules', label: 'Rules', icon: '📏' },
  { path: '/statements', label: 'Statements', icon: '📄' },
  { path: '/reconciliation', label: 'Reconcile', icon: '🔄' },
  { path: '/health', label: 'Health', icon: '🔍' },
  { path: '/reports', label: 'Reports', icon: '📊' },
  { path: '/payroll', label: 'Payroll', icon: '💰' },
  { path: '/upgrade', label: 'Upgrade', icon: '⭐' },
  { path: '/settings', label: 'Settings', icon: '⚙️' },
]

const mobileNavItems = [
  { path: '/dashboard', label: 'Dashboard', icon: '📊', shortLabel: 'Home' },
  { path: '/import', label: 'Import', icon: '📥', shortLabel: 'Import' },
  { path: '/transactions', label: 'Transactions', icon: '📋', shortLabel: 'Txns' },
  { path: '/tax', label: 'Tax', icon: '💰', shortLabel: 'Tax' },
]

// ── State ─────────────────────────────────────────────────────────

const isLoading = ref(false)
const mobileDrawerOpen = ref(false)
const userEmail = ref(localStorage.getItem('user_email') || '')

// ── Theme ─────────────────────────────────────────────────────────

const themeCycle = ['system', 'light', 'dark']
const themeIndex = ref(themeCycle.indexOf(localStorage.getItem('theme') || 'system'))

const themeLabel = computed(() => `Theme: ${themeCycle[themeIndex.value]}`)
const themeIcon = computed(() => {
  const t = themeCycle[themeIndex.value]
  return t === 'light' ? '☀️' : t === 'dark' ? '🌙' : '🖥️'
})

function toggleTheme() {
  themeIndex.value = (themeIndex.value + 1) % themeCycle.length
  const t = themeCycle[themeIndex.value]
  localStorage.setItem('theme', t)
  applyTheme(t)
}

// Resolve the effective theme. 'system' follows the OS preference via
// matchMedia (kept live with a change listener below).
function effectiveTheme() {
  const t = themeCycle[themeIndex.value] || 'system'
  if (t !== 'system') return t
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(t) {
  const html = document.documentElement
  const eff = t === 'system' ? effectiveTheme() : t
  html.setAttribute('data-theme', eff)
}

let systemMediaListener = null

// ── Auth ──────────────────────────────────────────────────────────

function handleLogout() {
  clearAuth()
  userEmail.value = ''
  router.push('/dashboard')
}

const authModal = ref(null)
function showAuthModal() {
  // emit to AuthModal component to open
  document.dispatchEvent(new CustomEvent('show-auth-modal'))
}

// ── Mobile drawer ────────────────────────────────────────────────

function toggleMobileDrawer() {
  mobileDrawerOpen.value = !mobileDrawerOpen.value
}
function closeMobileDrawer() {
  mobileDrawerOpen.value = false
}

// ── Helpers ──────────────────────────────────────────────────────

function isActive(path) {
  return route.path === path
}

// ── Lifecycle ────────────────────────────────────────────────────

onMounted(() => {
  // Restore theme
  const saved = localStorage.getItem('theme') || 'system'
  applyTheme(saved)
  themeIndex.value = themeCycle.indexOf(saved)

  // Keep 'system' mode in sync with OS theme changes
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  systemMediaListener = (e) => {
    if ((localStorage.getItem('theme') || 'system') === 'system') {
      applyTheme('system')
    }
  }
  mq.addEventListener('change', systemMediaListener)

  // Listen for loading events (can be triggered by API calls)
  window.addEventListener('api-loading-start', () => { isLoading.value = true })
  window.addEventListener('api-loading-end', () => { isLoading.value = false })
})

onUnmounted(() => {
  if (systemMediaListener) {
    window.matchMedia('(prefers-color-scheme: dark)').removeEventListener('change', systemMediaListener)
  }
})
</script>

<style scoped>
.app-shell {
  display: contents;
}

.loading-bar {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 3px;
  background: var(--primary);
  z-index: 9999;
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.3s;
}
.loading-bar.visible {
  transform: scaleX(1);
}

.sidebar-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  color: var(--gray-600);
  text-decoration: none;
  font-size: 0.875rem;
  transition: background 0.15s, color 0.15s;
}
.sidebar-link:hover {
  background: var(--gray-100);
  color: var(--gray-900);
}
.sidebar-link.active,
.sidebar-link.router-link-exact-active {
  background: var(--primary-bg, #eff6ff);
  color: var(--primary);
  font-weight: 600;
}

.sidebar-footer {
  margin-top: auto;
  padding: 12px;
  border-top: 1px solid var(--gray-200);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.user-email {
  font-size: 0.75rem;
  color: var(--gray-500);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version {
  width: 100%;
  font-size: 0.7rem;
  color: var(--gray-400);
  margin-top: 4px;
}

/* Mobile nav link active state */
.mobile-nav-link.active {
  color: var(--primary);
}
</style>
