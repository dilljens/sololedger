---
status: completed
kind: plan
area: testing, frontend
author: AI
created: 2026-07-25
---

# Project: SoloLedger — E2E Tests & Frontend Crash Fixes

**Goal:** Create comprehensive Playwright E2E tests covering all pages, and fix the frontend crash bugs (especially the tax page `Cannot read properties of undefined` error).

## Requirements

- [ ] R1: Tax page does not crash when `/tax/estimate` returns no-profit response
- [ ] R2: All frontend pages handle partial/missing API data without crashing
- [ ] R3: Playwright E2E tests installed and configured
- [ ] R4: E2E tests cover every page (16 pages) with happy-path + edge-case scenarios
- [ ] R5: Existing backend Python tests continue to pass (regression-free)
- [ ] R6: New backend API tests cover edge cases (no data, zero income, S-Corp vs SMLLC branching)

## Pre-resolved Decisions

- **Playwright over Cypress**: Playwright is faster, has better API, and works with any framework (vanilla JS here). Installed via `pip install playwright` into the venv.
- **Test against running server**: Playwright tests will start the FastAPI/uvicorn server as a subprocess, then point at it. This tests the real API + real frontend together.
- **Test data**: Use the existing `tests/conftest.py` fixtures for backend unit tests. For E2E, run the server with a dedicated test config + ledger data.
- **No npm/node**: The web app has no build step (vanilla JS served by FastAPI). No need for npm.

## Track A: Fix Frontend Crash Bugs `[ ]`

**Description:** Fix all crash points in the JavaScript frontend pages where accessing deeply nested API response properties can throw `TypeError`. Primary focus on `tax.js` (the reported crash), then the other 7 crash points identified in audit.

- 📏 Scope: ~9 files, ~100-150 lines changed

### Phase A1: Fix tax.js no-profit crash `[ ]`
- 🏷 Priority: **high** (reported crash)
- 🔁 Max turns: 5
- [ ] Wrap `tax.self_employment_tax` access with fallback/guard in the no-profit case
- [ ] Wrap `tax.federal_income_tax` access with fallback/guard
- [ ] Wrap `tax.fica` access (S-Corp path) with fallback
- [ ] Wrap `tax.form_1120s` access (S-Corp path) with fallback
- [ ] Wrap `dl.deadlines.map()` with array guard
- 📏 Scope: ~1 file (tax.js), ~30-40 lines
- ✅ Checkpoint: `python -c "import re; code=open('web/js/pages/tax.js').read(); assert '?.' in code or '||' in code or '??' in code or 'else' in code"` (confirms guards added)
- ⚙ Fallback: If guards are too complex, use a default response object pattern like `accounts.js`

### Phase A2: Fix dashboard.js crash points `[ ]`
- 🏷 Priority: **high** (dashboard is landing page)
- 🔁 Max turns: 3
- [ ] Guard `d.tax` access with fallback
- [ ] Guard `d.deadlines` map call with array check
- [ ] Guard `t.account.split(':')` with null check
- 📏 Scope: ~1 file (dashboard.js), ~15-20 lines
- ✅ Checkpoint: Page renders without error when `tax` field is missing from `/dashboard` response
- ⚙ Fallback: Use optional chaining `?.` throughout

### Phase A3: Fix remaining crash points in other pages `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 5
- [ ] Fix `payroll.js` — guard `data.rows` iteration
- [ ] Fix `reports.js` — guard `expenses.categories.map()`
- [ ] Fix `reports.js` — guard `c.category.replace()`
- [ ] Fix `invoices.js` — guard `invData.invoices.map()`
- [ ] Fix `health.js` — guard `data.errors.map()` when success=true
- [ ] Fix `settings.js` — guard `Object.entries(plans)`
- [ ] Fix `import.js` — guard `a.balance.toFixed(2)`
- [ ] Fix `receipts.js` — guard `d.path.split('/')`
- 📏 Scope: ~7 files, ~50-70 lines
- ✅ Checkpoint: `grep -c "data\\." web/js/pages/*.js | wc -l` — shows all files modified
- ⚙ Fallback: Skip low-priority crashes (settings, mileage) if time is short

### Phase A4: Run all existing backend tests `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 2
- [ ] `git pull` latest main first
- [ ] Run `pytest tests/ -x --tb=short` — confirm all 91 pass
- 📏 Scope: 0 files changed
- ✅ Checkpoint: `pytest tests/ -q | tail -1` — shows all passing
- ⚙ Fallback: Fix any regressions if backend tests fail

## Track B: Backend API Test Fixtures & Coverage `[ ]`

**Description:** Write additional backend Python tests for API edge cases that the frontend will encounter. Also create reusable test fixtures for starting the API server.

- 📏 Scope: ~3 files, ~200-300 lines

### Phase B1: API test infrastructure `[ ]`
- 🏷 Priority: **high** (needed before Playwright tests)
- 🔁 Max turns: 5
- [ ] Create `tests/test_api.py` with FastAPI `TestClient` fixtures
- [ ] Add fixture for test Open Mode (no auth needed — for test simplicity)
- [ ] Add fixture for auth token generation in test
- [ ] Test `/api/v1/health` returns 200
- [ ] Test `/api/v1/public/status` returns expected shape
- 📏 Scope: ~1-2 files, ~80-100 lines
- ✅ Checkpoint: `pytest tests/test_api.py -v --tb=short` — tests pass
- ⚙ Fallback: Use `uvicorn` subprocess + HTTP requests instead of TestClient if dependency issues

### Phase B2: API tax endpoint corner cases `[ ]`
- 🏷 Priority: **high** (directly relates to the tax crash)
- 🔁 Max turns: 5
- [ ] Test `/api/v1/tax/estimate` with empty ledger (ytd_net = 0)
- [ ] Test `/api/v1/tax/estimate` with sample data (ytd_net > 0, SMLLC)
- [ ] Test `/api/v1/tax/estimate` with S-Corp config
- [ ] Test `/api/v1/tax/deadlines` returns expected shape
- [ ] Test `/api/v1/tax/schedule-c` returns expected shape
- 📏 Scope: ~1 file (test_api.py additions), ~60-80 lines
- ✅ Checkpoint: All tax API tests pass with proper response shape verification
- ⚙ Fallback: Focus on the no-profit case (most critical)

### Phase B3: API dashboard + other endpoints `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 5
- [ ] Test `/api/v1/dashboard` returns expected shape
- [ ] Test `/api/v1/dashboard` with empty ledger
- [ ] Test `/api/v1/status` returns expected shape
- [ ] Test `/api/v1/accounts` returns expected shape
- [ ] Test `/api/v1/invoices` endpoint
- [ ] Test `/api/v1/subscription/plans` returns free-tier data
- 📏 Scope: ~1 file, ~80-100 lines
- ✅ Checkpoint: All endpoint tests pass
- ⚙ Fallback: Skip subscription/banking tests if they need external config

## Track C: Playwright E2E Tests `[ ]`

**Description:** Install Playwright and write comprehensive E2E tests that start the API server, open a browser, and verify every page renders without JS errors.

- 📏 Scope: ~5-7 files, ~500-700 lines

### Phase C1: Install & configure Playwright `[ ]`
- 🏷 Priority: **high**
- 🔁 Max turns: 5
- [ ] Install Playwright: `pip install playwright`
- [ ] Install browser: `playwright install chromium`
- [ ] Create `tests/e2e/` directory
- [ ] Create `tests/e2e/conftest.py` with server startup/shutdown fixture
- [ ] Create `tests/e2e/config.py` with test configuration
- 📏 Scope: ~3 files, ~50-80 lines
- ✅ Checkpoint: `python -c "from playwright.sync_api import sync_playwright; print('ok')"` works
- ⚙ Fallback: If Playwright can't install chromium, use `pytest-playwright` with system browser

### Phase C2: Server lifecycle fixture `[ ]`
- 🏷 Priority: **high**
- 🔁 Max turns: 3
- [ ] Create fixture that starts uvicorn on a random port
- [ ] Create fixture that creates a temp ledger with sample data
- [ ] Create fixture that waits for server to be ready
- [ ] Create fixture that cleans up after tests
- 📏 Scope: ~1 file (conftest.py), ~60-80 lines
- ✅ Checkpoint: Can start server, hit health endpoint, then shut down in a test
- ⚙ Fallback: If subprocess approach is fragile, use FastAPI TestClient for API tests and only start real server for JS rendering tests

### Phase C3: E2E — Auth & Dashboard pages `[ ]`
- 🏷 Priority: **high** (landing page + auth gate)
- 🔁 Max turns: 5
- [ ] Test: Public status endpoint works, page loads
- [ ] Test: Dashboard renders without JS errors
- [ ] Test: Dashboard shows correct cash, revenue, expenses numbers
- [ ] Test: Attention items render if present
- [ ] Test: Sign-in modal opens and works
- [ ] Test: Auth-required pages redirect properly when not logged in
- 📏 Scope: ~2 files, ~80-120 lines
- ✅ Checkpoint: Tests pass, no console error messages
- ⚙ Fallback: If Google auth button can't render, test email/password path only

### Phase C4: E2E — Tax & Deadlines pages `[ ]`
- 🏷 Priority: **high** (the reported crash)
- 🔁 Max turns: 5
- [ ] Test: Tax estimate page renders without crashing when profit > 0
- [ ] Test: Tax estimate page renders gracefully when profit = 0
- [ ] Test: All tax fields displayed (SE tax, federal, total, already paid)
- [ ] Test: Deadlines page renders all 5 deadlines
- [ ] Test: Mark as Paid button works
- [ ] Test: No console errors on any tax page variant
- 📏 Scope: ~1 file, ~60-100 lines
- ✅ Checkpoint: Both profit and no-profit cases render without console errors
- ⚙ Fallback: Handle no-profit case as a separate test with empty ledger

### Phase C5: E2E — Remaining pages `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 8
- [ ] Test: Accounts page renders balances + cards
- [ ] Test: Import page renders bank status + file upload forms
- [ ] Test: Invoices page lists invoices + AR summary
- [ ] Test: Transactions page renders recent transactions
- [ ] Test: Receipts page renders (even if no receipts yet)
- [ ] Test: Categorize page renders suggestions
- [ ] Test: Mileage page renders trip list + report
- [ ] Test: Health page renders check results
- [ ] Test: Reports page renders expense report + P&L
- [ ] Test: Payroll page renders summary (or note if not S-Corp)
- [ ] Test: Settings page renders LLM config + subscription info
- [ ] Test: No page produces console errors (check with page.on('pageerror'))
- 📏 Scope: ~2-3 files, ~200-300 lines
- ✅ Checkpoint: All 16 pages tested, zero console errors across all pages
- ⚙ Fallback: Group pages by similar patterns to reduce test boilerplate

## Track D: Documentation & Final Verification `[ ]`

**Description:** Commit everything, verify on production, document test coverage.

- 📏 Scope: ~2 files, ~30-50 lines

### Phase D1: Git commit & push `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 3
- [ ] Commit frontend fixes
- [ ] Commit backend API tests
- [ ] Commit E2E tests
- [ ] Push to main → trigger deploy
- 📏 Scope: git operations only
- ✅ Checkpoint: `git push origin main` succeeds
- ⚙ Fallback: If deploy fails, manually SSH and fix (as before)

### Phase D2: Verify on production `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 3
- [ ] SSH into VPS, pull + rebuild
- [ ] Verify no JS console errors on tax page
- [ ] Verify dashboard loads without 500
- [ ] Run `pytest tests/ -q` on VPS
- 📏 Scope: operations
- ✅ Checkpoint: curl to production dashboard + tax endpoints returns 200
- ⚙ Fallback: n/a

### Phase D3: Update test documentation `[ ]`
- 🏷 Priority: low
- 🔁 Max turns: 2
- [ ] Add README section about running E2E tests
- [ ] Document test config requirements
- 📏 Scope: ~1 file (README.md or TESTING.md), ~15-25 lines
- ✅ Checkpoint: README has clear instructions for running all tests
- ⚙ Fallback: Skip if README already has adequate instructions
