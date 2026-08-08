import { createRouter, createWebHashHistory } from 'vue-router'
import { h } from 'vue'
import GenericPage from '../pages/GenericPage.vue'

// Helper to create a GenericPage with props
function apiPage(apiEndpoint, title, description, icon = '📄') {
  return {
    render() {
      return h(GenericPage, {
        apiEndpoint,
        title,
        description,
        icon,
      })
    },
  }
}

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: () => import('../pages/Dashboard.vue') },
  { path: '/accounts', name: 'accounts', component: () => import('../pages/AccountsPage.vue') },
  { path: '/import', name: 'import', component: () => import('../pages/ImportCenter.vue') },
  { path: '/invoices', name: 'invoices', component: () => import('../pages/InvoicesPage.vue') },
  { path: '/new-invoice', name: 'new-invoice', component: () => import('../pages/NewInvoice.vue') },
  { path: '/transactions', name: 'transactions', component: () => import('../pages/TransactionsPage.vue') },
  { path: '/receipts', name: 'receipts', component: () => import('../pages/ReceiptList.vue') },
  { path: '/capture', name: 'capture', component: () => import('../pages/ReceiptCapture.vue') },
  { path: '/categorize', name: 'categorize', component: () => import('../pages/CategorizePage.vue') },
  { path: '/tax', name: 'tax', component: () => import('../pages/TaxPage.vue') },
  { path: '/deadlines', name: 'deadlines', component: apiPage('/tax/deadlines', 'Deadlines', 'Tax filing deadlines', '📅') },
  { path: '/mileage', name: 'mileage', component: () => import('../pages/MileagePage.vue') },
  { path: '/health', name: 'health', component: () => import('../pages/HealthPage.vue') },
  { path: '/reports', name: 'reports', component: apiPage('/reports/profit-loss', 'Reports', 'Expense and P&L reports', '📊') },
  { path: '/payroll', name: 'payroll', component: () => import('../pages/PayrollPage.vue') },
  { path: '/settings', name: 'settings', component: () => import('../pages/SettingsPage.vue') },
  { path: '/upgrade', name: 'upgrade', component: () => import('../pages/Upgrade.vue') },
  { path: '/verify-email', name: 'verify-email', component: () => import('../pages/VerifyEmail.vue') },
  { path: '/reset-password', name: 'reset-password', component: () => import('../pages/ResetPassword.vue') },
  // Feature pages
  { path: '/amazon', name: 'amazon', component: () => import('../pages/AmazonOrders.vue') },
  { path: '/coa', name: 'chart-of-accounts', component: () => import('../pages/ChartOfAccounts.vue') },
  { path: '/rules', name: 'rules', component: () => import('../pages/RulesPage.vue') },
  { path: '/reconciliation', name: 'reconciliation', component: () => import('../pages/Reconciliation.vue') },
  { path: '/statements', name: 'statements', component: () => import('../pages/Statements.vue') },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
