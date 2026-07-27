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
  { path: '/accounts', name: 'accounts', component: apiPage('/accounts', 'Accounts', 'Account balances and cards', '🏦') },
  { path: '/import', name: 'import', component: () => import('../pages/ImportCenter.vue') },
  { path: '/invoices', name: 'invoices', component: apiPage('/invoices', 'Invoices', 'Invoice list and AR summary', '📄') },
  { path: '/new-invoice', name: 'new-invoice', component: apiPage('/invoices/new', 'New Invoice', 'Create a new invoice', '➕') },
  { path: '/transactions', name: 'transactions', component: apiPage('/dashboard', 'Transactions', 'Recent transactions', '📋') },
  { path: '/receipts', name: 'receipts', component: () => import('../pages/ReceiptList.vue') },
  { path: '/capture', name: 'capture', component: () => import('../pages/ReceiptCapture.vue') },
  { path: '/categorize', name: 'categorize', component: apiPage('/categories/suggest?merchant=', 'Categorize', 'Suggest categories for transactions', '🏷️') },
  { path: '/tax', name: 'tax', component: () => import('../pages/TaxPage.vue') },
  { path: '/deadlines', name: 'deadlines', component: apiPage('/tax/deadlines', 'Deadlines', 'Tax filing deadlines', '📅') },
  { path: '/mileage', name: 'mileage', component: apiPage('/mileage/trips', 'Mileage', 'Business mileage tracking', '🚗') },
  { path: '/health', name: 'health', component: apiPage('/check', 'Health', 'Ledger validation results', '🔍') },
  { path: '/reports', name: 'reports', component: apiPage('/dashboard', 'Reports', 'Expense and P&L reports', '📊') },
  { path: '/payroll', name: 'payroll', component: apiPage('/payroll/summary', 'Payroll', 'Payroll runs and history', '💰') },
  { path: '/settings', name: 'settings', component: () => import('../pages/PlaceholderPage.vue') },
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
