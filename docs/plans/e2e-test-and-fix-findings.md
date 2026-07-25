# Findings: SoloLedger E2E Tests & Frontend Crash Fixes

## Diagnostic Results

### Tax Page Crash (Reported Bug)
**Error:** `Cannot read properties of undefined (reading 'total')`  
**File:** `web/js/pages/tax.js:40`  
**Root Cause:** When the ledger has zero net income (empty ledger / no transactions), the API endpoint `GET /api/v1/tax/estimate` returns:
```json
{"success": true, "data": {"note": "No net profit yet. No tax estimated."}}
```
This minimal response has no `self_employment_tax`, `federal_income_tax`, `fica`, or `form_1120s` keys. The frontend unconditionally accesses `tax.self_employment_tax.total` (line 40), which crashes on `undefined.total`.

The same crash happens on the production VPS because the Docker container has an empty ledger volume — no demo data loaded.

### Full Frontend Crash Audit
| # | File | Line | Expression | Severity |
|---|---|---|---|---|
| 1 | tax.js | 40 | `tax.self_employment_tax.total` | **CRASH** (reported) |
| 2 | tax.js | 42 | `tax.federal_income_tax.total` | **CRASH** |
| 3 | tax.js | 14 | `tax.fica.salary` | **CRASH** (S-Corp) |
| 4 | tax.js | 94 | `dl.deadlines.map(...)` | **CRASH** |
| 5 | dashboard.js | 93 | `d.tax.annual_total_tax` | **CRASH** |
| 6 | dashboard.js | 114 | `d.deadlines.map(...)` | **CRASH** |
| 7 | dashboard.js | 137 | `t.account.split(':')` | **CRASH** |
| 8 | payroll.js | 105 | `for (const row of data.rows)` | **CRASH** |
| 9 | reports.js | 26 | `expenses.categories.map(...)` | **CRASH** |
| 10 | reports.js | 28 | `c.category.replace(...)` | **CRASH** |
| 11 | invoices.js | 103 | `invData.invoices.map(...)` | **CRASH** |
| 12 | health.js | 39 | `data.errors.map(...)` | **CRASH** |
| 13 | settings.js | 154 | `Object.entries(plans)` | **CRASH** |
| 14 | import.js | 78 | `a.balance.toFixed(2)` | **CRASH** |
| 15 | receipts.js | 39 | `d.path.split('/').pop()` | **CRASH** |

### Existing Test Coverage
- **91 tests total**, all passing
- **5.38%** of 130 source files have tests
- Tests cover: CLI commands, config loading, ledger operations, invoice creation, payments, payroll import, and tax estimation
- **No API tests** — all existing tests are on the backend library code (not FastAPI endpoints)
- **No E2E/frontend tests** at all

### Project Structure
- **Frontend:** Vanilla JS, no build step, served by FastAPI static file mount
- **Backend:** FastAPI with uvicorn, 22 route files under `app/api/`
- **JS files:** 16 page modules in `web/js/pages/`, 2 shared modules in `web/js/`
- **Package management:** Python only (pip/venv) — no npm, no node_modules
- **Playwright:** Not installed yet — needs `pip install playwright` + `playwright install chromium`

### Pre-resolved Technical Decisions

**1. Why Playwright (not Cypress, Selenium, or just unit tests)?**
- The crash is in the JS rendering layer — we need a real browser to catch rendering errors
- Playwright has the best Python API (`from playwright.sync_api import sync_playwright`)
- No npm build step needed — Playwright can load the raw HTML served by FastAPI
- `page.on('pageerror')` listener catches all JS exceptions automatically

**2. Test server lifecycle**
- Start uvicorn on random port (`--port 0`) before tests
- Wait for `/api/v1/health` to return 200
- Use temporary test config + ledger with demo data
- For no-profit tests, use a different config pointing at an empty ledger

**3. Auth strategy for E2E tests**
- In "open mode" (no API keys set), auth is bypassed — no sign-in needed
- All tests run in open mode for simplicity
- Add separate auth-specific tests if sign-in flow needs coverage

**4. Test isolation**
- Each test file gets its own server instance (shared via module-scoped fixture)
- Ledger data is reset between test files (not between individual tests)
- Critical tests (tax, dashboard) use dedicated ledger fixtures

### Related Work
- Previous fix: `ledger.entries()` → `ledger.entries` (dashboard 500 fix, commit `f1a6d60`)
- Google auth setup completed by user
- Production VPS at `40.160.241.74`, deployed via Docker
