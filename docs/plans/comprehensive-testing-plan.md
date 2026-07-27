---
status: completed
kind: plan
area: testing, receipts, e2e
author: AI
created: 2026-07-25
---

# Project: SoloLedger — Comprehensive Testing & Receipt Verification

**Goal:** Fix the receipt "take image" feature by installing missing OCR dependency, verify the entire app works locally, and write thorough automated tests (unit, API, E2E) to prevent regressions.

## Requirements
- [ ] R1: `pytesseract` installed, image OCR works end-to-end
- [ ] R2: ReceiptScanner has unit tests covering parsing edge cases
- [ ] R3: All receipt API endpoints have FastAPI TestClient tests
- [ ] R4: E2E tests exist for all 16+ pages (smoke test: renders without JS errors)
- [ ] R5: Existing 104 tests continue to pass
- [ ] R6: Manual verification confirms receipt photo upload works

## Pre-resolved Decisions
- **Python venv**: Use `.venv/bin/python` and `.venv/bin/pip` for all commands
- **Test structure**: Unit tests in `tests/test_receipt_scanner.py`, API tests in `tests/test_receipt_api.py`, E2E in `tests/e2e/`
- **E2E marker**: Use existing `@pytest.mark.e2e` from pyproject.toml
- **OCR test image**: Generate a small PNG with known text via Pillow for automated tests
- **Manual verification**: Use a real JPEG photo from phone/camera for final check
- **pytesseract**: Install via `.venv/bin/pip install pytesseract` (system `tesseract` binary already installed at `/usr/bin/tesseract v5.5.3`)

---

## Track A: Environment & OCR Fix `[ ]`

**Description:** Install `pytesseract`, verify image OCR works end-to-end, confirm the app starts and basic receipt flow functions.

- 📏 Scope: ~2 files (pip install + 1 test script), ~1-5 lines changed in source (if any fixes needed)

### Phase A1: Install pytesseract & verify OCR `[ ]`
- 🏷 Priority: **high** (blocker for "take image")
- 🔁 Max turns: 2
- [ ] Run `.venv/bin/pip install pytesseract`
- [ ] Verify import works: `.venv/bin/python -c "import pytesseract; print(pytesseract.__version__)"`
- [ ] Verify tesseract binary is accessible: `tesseract --version` (already v5.5.3)
- [ ] Quick smoke test: create a small test image, run OCR, confirm text is extracted
- 📏 Scope: 0 source files changed (pip install only)
- ✅ Checkpoint: `.venv/bin/python -c "from PIL import Image; import pytesseract; img=Image.new('RGB',(200,50),'white'); print('pytesseract OK')"`
- ⚙ Fallback: If pip fails, try `.venv/bin/pip install pytesseract --no-deps` or install system package `tesseract-ocr` (already present)

### Phase A2: Quick manual smoke test of receipt scan `[ ]`
- 🏷 Priority: **high**
- 🔁 Max turns: 2
- [ ] Start the API server: `.venv/bin/uvicorn app.api:app --port 8100`
- [ ] Upload a test image via curl to `/api/v1/receipts/scan` and confirm non-error response
- [ ] Note any issues found
- 📏 Scope: 0 source files changed
- ✅ Checkpoint: `curl -s -X POST http://localhost:8100/api/v1/receipts/scan -F "file=@test_receipt.png" -F "preview=true" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('success'), d.get('data',{}).get('merchant',''))"` returns True + merchant name
- ⚙ Fallback: If server doesn't start, investigate import errors / missing deps

### Phase A3: Re-run existing test suite `[ ]`
- 🏷 Priority: medium (regression check)
- 🔁 Max turns: 1
- [ ] Run `.venv/bin/python -m pytest tests/ -q --tb=short`
- [ ] Confirm all 104 tests still pass
- 📏 Scope: 0 files changed
- ✅ Checkpoint: "104 passed" in output
- ⚙ Fallback: Investigate any new failures from pytesseract install (unlikely)

---

## Track B: ReceiptScanner Unit Tests `[ ]`

**Description:** Write comprehensive unit tests for `ReceiptScanner` covering parsing, edge cases, and error handling. No API needed — pure logic tests.

- 📏 Scope: ~1 new file (`tests/test_receipt_scanner.py`), ~250-350 lines

### Phase B1: Test _parse_receipt with synthetic texts `[ ]`
- 🏷 Priority: **high**
- 🔁 Max turns: 5
- [ ] Create `tests/test_receipt_scanner.py` with `ReceiptScanner` fixture
- [ ] Test: basic receipt with merchant, date, total, line items
- [ ] Test: receipt with "TOTAL" label (labeled total path)
- [ ] Test: receipt without "TOTAL" label (fallback: largest amount)
- [ ] Test: receipt with multiple line items and subtotal/tax
- [ ] Test: empty text → graceful error
- [ ] Test: garbled text → best-effort parse
- [ ] Test: various date formats (MM/DD/YYYY, YYYY-MM-DD, "Jan 15, 2026", etc.)
- [ ] Test: amounts with commas ($1,234.56)
- [ ] Test: merchant in first line vs non-trivial first line
- 📏 Scope: ~1 file, ~100-150 lines
- ✅ Checkpoint: `.venv/bin/python -m pytest tests/test_receipt_scanner.py::TestParseReceipt -v --tb=short` — all pass
- ⚙ Fallback: Test only the most common receipt formats if time is short

### Phase B2: Test _extract_image with generated test image `[ ]`
- 🏷 Priority: **high** (directly tests the failing path)
- 🔁 Max turns: 3
- [ ] Create a helper that generates a PNG with known text using Pillow
- [ ] Test: `_extract_image()` extracts the expected text from generated image
- [ ] Test: `scan()` on image returns success with correct data
- [ ] Test: `_extract_image()` returns "" when pytesseract is missing (monkeypatch)
- 📏 Scope: ~1 file, ~50-80 lines
- ✅ Checkpoint: `.venv/bin/python -m pytest tests/test_receipt_scanner.py::TestExtractImage -v --tb=short` — all pass
- ⚙ Fallback: If pytesseract OCR quality on generated image is poor, test with known-good test fixture

### Phase B3: Test _extract_pdf with generated PDF `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 3
- [ ] Create a test PDF with known text (using reportlab or simple text PDF)
- [ ] Test: `_extract_pdf()` extracts text from multi-page PDF
- [ ] Test: `scan()` on PDF returns success with correct data
- 📏 Scope: ~1 file, ~40-60 lines
- ✅ Checkpoint: `.venv/bin/python -m pytest tests/test_receipt_scanner.py::TestExtractPdf -v --tb=short` — all pass
- ⚙ Fallback: Skip PDF tests if creating test PDFs is too complex; use a pre-generated fixture

### Phase B4: Test scan() error paths `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 3
- [ ] Test: non-existent file → error
- [ ] Test: unsupported file type → error
- [ ] Test: file outside allowed directories → error
- [ ] Test: scan with valid image → full result structure
- 📏 Scope: ~1 file, ~40-60 lines
- ✅ Checkpoint: error path tests pass
- ⚙ Fallback: Test at least the non-existent and unsupported file type cases

---

## Track C: Receipt API Tests `[ ]`

**Description:** Write FastAPI TestClient tests for all receipt and category endpoints, following the existing pattern in `tests/test_api.py`.

- 📏 Scope: ~1 new file (`tests/test_receipt_api.py`), ~200-300 lines

### Phase C1: Test infrastructure & helpers `[ ]`
- 🏷 Priority: **high** (needed by all API tests)
- 🔁 Max turns: 3
- [ ] Create `tests/test_receipt_api.py` with `api_client` fixture (following test_api.py pattern)
- [ ] Create helper to generate a test image file for uploads
- [ ] Create `assert_success` / `assert_error` helpers (or import from test_api.py)
- 📏 Scope: ~1 file, ~30-50 lines
- ✅ Checkpoint: API client fixture works with health endpoint
- ⚙ Fallback: Import helpers from `test_api.py` or create a shared helper module

### Phase C2: Test POST /receipts/scan `[ ]`
- 🏷 Priority: **high** (the endpoint the user hit)
- 🔁 Max turns: 5
- [ ] Test: scan with valid image + preview=true → 200 + correct shape
- [ ] Test: scan with preview=false → 200 + appended=true
- [ ] Test: scan with PDF file → 200
- [ ] Test: scan with empty file → error
- [ ] Test: scan without auth (if auth configured) → 401
- 📏 Scope: ~1 file, ~80-100 lines
- ✅ Checkpoint: `.venv/bin/python -m pytest tests/test_receipt_api.py::TestScanReceipt -v --tb=short` — all pass
- ⚙ Fallback: Skip plan gating test if it requires complex tenant setup

### Phase C3: Test GET /receipts/list `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 3
- [ ] Test: list returns expected structure
- [ ] Test: list with year filter works
- [ ] Test: list when no documents exist → empty array
- 📏 Scope: ~1 file, ~30-50 lines
- ✅ Checkpoint: list tests pass
- ⚙ Fallback: n/a

### Phase C4: Test GET /categories/suggest & POST /categories/learn `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 3
- [ ] Test: suggest with known merchant → returns account
- [ ] Test: suggest with unknown merchant → fallback account
- [ ] Test: learn a new merchant→account mapping
- [ ] Test: correct an existing mapping
- 📏 Scope: ~1 file, ~40-60 lines
- ✅ Checkpoint: category suggest + learn tests pass
- ⚙ Fallback: If Categorizer needs config with expense rules, use sample_config fixture

### Phase C5: Test GET /receipts/match `[ ]`
- 🏷 Priority: low (supporting feature)
- 🔁 Max turns: 3
- [ ] Test: match with known amount → returns matches
- [ ] Test: match with no matches → empty array
- [ ] Test: match with zero amount → empty array
- 📏 Scope: ~1 file, ~20-40 lines
- ✅ Checkpoint: match tests pass
- ⚙ Fallback: Skip if test ledger setup is too complex

---

## Track D: E2E Tests `[ ]`

**Description:** Create the `tests/e2e/` directory and write Playwright tests that start the API server, open a browser, and verify every page renders without JS errors.

- 📏 Scope: ~3-5 new files, ~400-600 lines

### Phase D1: Create E2E test infrastructure `[ ]`
- 🏷 Priority: **high** (unblocks all E2E testing)
- 🔁 Max turns: 5
- [ ] Create `tests/e2e/__init__.py`
- [ ] Create `tests/e2e/conftest.py` with:
  - Server fixture: starts uvicorn on random port, waits for readiness, tears down
  - Browser fixture: Playwright chromium page with console error capture
  - Config fixture: points at sample ledger data
- [ ] Create `tests/e2e/config.py` with test settings
- 📏 Scope: ~3 files, ~80-120 lines
- ✅ Checkpoint: `.venv/bin/python -m pytest tests/e2e/ --headed -m e2e -v --tb=short` — server starts, health page renders
- ⚙ Fallback: If subprocess server is unreliable, use FastAPI TestClient + `page.route()` to mock API responses

### Phase D2: E2E — Dashboard & landing pages `[ ]`
- 🏷 Priority: **high**
- 🔁 Max turns: 4
- [ ] Test: Dashboard loads, shows cash/revenue/expenses
- [ ] Test: Accounts page renders balances
- [ ] Test: No JS console errors on landing pages
- 📏 Scope: ~1 file (`tests/e2e/test_dashboard.py`), ~60-80 lines
- ✅ Checkpoint: Tests pass with zero console errors
- ⚙ Fallback: Reduce assertions if dynamic data makes exact values unpredictable

### Phase D3: E2E — Receipt pages (the failing flow) `[ ]`
- 🏷 Priority: **high** (directly tests the broken feature)
- 🔁 Max turns: 5
- [ ] Test: Receipts page renders without errors
- [ ] Test: "Capture Receipt" button navigates to capture page
- [ ] Test: Upload a test image file via the file input → scan result appears (or graceful error if no auth)
- [ ] Test: No JS console errors on receipt pages
- 📏 Scope: ~1 file (`tests/e2e/test_receipts.py`), ~80-120 lines
- ✅ Checkpoint: Receipt upload test passes (either successful scan or graceful auth error)
- ⚙ Fallback: If file upload via Playwright is unreliable, test page render + button existence + navigation

### Phase D4: E2E — Tax, deadlines, reports, remaining pages `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 6
- [ ] Test: Tax estimate page renders (both profit/no-profit cases)
- [ ] Test: Deadlines page shows 5 deadlines
- [ ] Test: Reports page renders expense report
- [ ] Test: Transactions, Mileage, Settings, Health pages render
- [ ] Test: Categorize page renders suggestions
- [ ] Test: No page produces console errors
- 📏 Scope: ~2 files (`tests/e2e/test_tax.py`, `tests/e2e/test_pages.py`), ~150-200 lines
- ✅ Checkpoint: All remaining pages tested with zero console errors
- ⚙ Fallback: Group by similarity, skip edge-case-only pages if time is short

### Phase D5: E2E — Auth & plan gating `[ ]`
- 🏷 Priority: low
- 🔁 Max turns: 3
- [ ] Test: Auth modal appears when GOOGLE_CLIENT_ID is set
- [ ] Test: Receipt endpoints show plan upgrade message on free tier
- 📏 Scope: ~1 file, ~40-60 lines
- ✅ Checkpoint: Auth/plan tests pass
- ⚙ Fallback: Skip if auth env setup is too complex; document how to test manually

---

## Track E: Manual Verification `[ ]`

**Description:** Fire up the real app and manually test the receipt capture flow with actual photos/PDFs.

- 📏 Scope: operations only

### Phase E1: Start server & verify basic pages `[ ]`
- 🏷 Priority: **high**
- 🔁 Max turns: 2
- [ ] Start server: `.venv/bin/uvicorn app.api:app --reload --port 8100`
- [ ] Open `http://localhost:8100/app/` in browser
- [ ] Navigate to Dashboard, Accounts, Import, Invoices, Transactions pages
- [ ] Verify each page renders without errors
- 📏 Scope: 0 files changed (verification only)
- ✅ Checkpoint: All pages load in browser
- ⚙ Fallback: If app doesn't start, check console for import errors

### Phase E2: Test receipt capture with a real image `[ ]`
- 🏷 Priority: **high** (the original bug)
- 🔁 Max turns: 3
- [ ] Take a photo of a receipt (or download a sample receipt image)
- [ ] Navigate to Receipts → Capture Receipt → Take Photo or Upload
- [ ] Upload the image and verify scan result appears (merchant, date, total)
- [ ] Verify category suggestion appears
- [ ] Verify "Append to Ledger" works
- [ ] Verify the receipt appears in the receipt list
- 📏 Scope: 0 files changed (verification only)
- ✅ Checkpoint: Full receipt capture flow works end-to-end with a real image
- ⚙ Fallback: Use a sample receipt PDF if image OCR quality is poor

### Phase E3: Test remaining features `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 3
- [ ] Quick smoke test of remaining pages (Tax, Deadlines, Mileage, Reports, Settings, Health)
- [ ] Verify navigation works (sidebar + mobile drawer)
- [ ] Check no JS errors in browser console
- 📏 Scope: 0 files changed (verification only)
- ✅ Checkpoint: All pages render, no console errors
- ⚙ Fallback: At minimum verify the pages the user reported as broken

---

## Progress

<!-- Update after each phase completion -->

| Phase | Status | Date |
|-------|--------|------|
| A1: Install pytesseract | `[x]` | 2026-07-25 |
| A2: Manual smoke test | `[x]` | 2026-07-25 |
| A3: Re-run test suite | `[x]` | 2026-07-25 |
| B1-B4: Parse/image/pdf/error tests | `[x]` | 2026-07-25 |
| C1-C5: All receipt API tests | `[x]` | 2026-07-25 |
| D1-D5: E2E tests (18 tests) | `[x]` | 2026-07-25 |
| E1-E3: Manual verification | `[x]` | 2026-07-25 |
