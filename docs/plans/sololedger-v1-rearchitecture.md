---
status: active
kind: plan
area: architecture, frontend, features
author: AI
created: 2026-07-25
---

# Project: SoloLedger v1 — Re-architecture & Feature Expansion

**Goal:** Transform SoloLedger from a Beancount-wrapped vanilla-JS SPA into a modern Vue.js app with a SQLite metadata layer, adding the top missing features from the Accounting project — Amazon import, PDF statement processing, cross-source dedup, reconciliation locking, COA management, line-item receipt reconciliation, and improved importers — all while keeping Beancount as the core ledger engine.

---

## Requirements

- [ ] R1: SQLite added alongside Beancount for feature metadata (imports, receipts, categorization rules, vendor orders, reconciliation state)
- [ ] R2: Vue.js 3 SPA replaces vanilla JS pages incrementally (interleaved approach)
- [ ] R3: Amazon Order History import (zip/CSV) with card-based filtering and line-item categorization
- [ ] R4: PDF statement intake — extract text, classify, file to canonical layout
- [ ] R5: Cross-source duplicate detection — warn when import matches existing transaction from a different source
- [ ] R6: Reconciliation locking — soft-lock reconciled transactions to prevent accidental modification
- [ ] R7: Chart of Accounts management UI — seed, list, add, update from web
- [ ] R8: Line-item receipt reconciliation — per-line CoA assignment with personal/reimbursable flags
- [ ] R9: Enhanced importers — Citi CSV, Wave historical CSV, improved OFX
- [ ] R10: Categorization rules engine — regex/substring/eq/range matchers with UI
- [ ] R11: All existing 175 tests continue to pass; new features have ≥80% test coverage
- [ ] R12: Beancount remains the source of truth for accounting data

---

## Pre-resolved Decisions

| Decision | Rationale |
|----------|-----------|
| **Keep Beancount** as primary ledger | User chose "Keep Beancount (Recommended)". SQLite is for feature metadata only. |
| **Vue 3 + Vite** for frontend | Vue's progressive adoption lets us migrate page-by-page. Vite provides fast HMR, no complex build config. |
| **SQLite via stdlib `sqlite3`** | Zero dependencies. One file per tenant (`data/feature.db`). Simple migrations via numbered SQL files. |
| **Feature-first migration** | Each feature is built as a Vue page with its own API + SQLite tables. Old pages stay running until the Vue replacement is ready. |
| **API stays FastAPI** | No reason to change the backend framework. Add SQLite connection alongside Beancount Ledger. |
| **Design system — custom CSS** | Keep the existing design tokens, refine them into a proper design system. No Tailwind/Bootstrap dependency. |
| **CLI lives alongside API** | The `app/main.py` CLI remains functional. New feature logic lives in shared modules usable from both API and CLI. |

---

## Track A: Foundation `[x]`

**Description:** Set up SQLite infrastructure, Vue.js scaffold, and base component framework. Everything else builds on this.

- 📏 Scope: ~15-20 files, ~800-1200 lines

### Phase A1: SQLite metadata layer `[x]`
- 🏷 Priority: **critical** (prerequisite for all new features)
- 🔁 Max turns: 10
- [x] Create `app/db.py` — SQLite connection manager (one DB per tenant directory)
- [x] Create `app/db_schema/` with numbered migration SQL files
- [x] Migration 001: `feature_flags`, `import_batches`, `imported_transactions` tables
- [x] Migration 001 includes: `vendor_receipts`, `vendor_receipt_items`, `transaction_receipt_links`, `categorization_rules`, `reconciliation_marks` tables
- [x] Add `get_db()` / `get_tenant_db_path()` / `make_fingerprint()` helpers
- [x] Write tests for DB init and migrations (`tests/test_db.py`)
- 📏 Scope: ~4 files, ~300-400 lines
- ✅ Checkpoint: `pytest tests/test_db.py -v` passes
- ⚙ Fallback: Keep all metadata in JSON files (like sessions.json pattern) if SQLite overcomplicates

### Phase A2: Vue.js scaffold `[x]`
- 🏷 Priority: **critical** (prerequisite for new UI)
- 🔁 Max turns: 8
- [x] Initialize Vite + Vue 3 project in `web/` directory
- [x] Create base App.vue with sidebar + content area matching current layout
- [x] Set up vue-router with hash-based routing (match current `#/page` pattern)
- [x] Create ApiClient module (`web/src/api.js`, `web/src/main.js`)
- [x] Create base components: AuthModal, Sidebar (in App.vue), Toast (GenericPage)
- [x] Port existing `index.html` shell to Vue (sidebar HTML, auth modal HTML, theme toggle)
- [x] Port existing CSS to scoped component styles + global tokens (`web/src/assets/main.css`)
- [ ] Verify the new Vue shell renders identically to the old HTML
- 📏 Scope: ~15-20 files, ~500-700 lines
- ✅ Checkpoint: Vue dev server runs; app shell matches current sidebar + auth modal appearance
- ⚙ Fallback: Skip hot-reload; build to `web/dist/` and serve via FastAPI

### Phase A3: Component library — shared patterns `[ ]`
- 🏷 Priority: high
- 🔁 Max turns: 6
- [x] Create DataTable component (sortable, searchable, paginated)
- [x] Create FormField / FormInput components (consistent styling, validation)
- [x] Create FileUpload component (drag-and-drop, preview)
- [x] Create AuthModal component
- [ ] Create StatusBadge / Tag / Alert components
- [ ] Create ConfirmDialog component
- [ ] Create Skeleton / LoadingState components
- 📏 Scope: ~10 files, ~400-500 lines
- ✅ Checkpoint: Storybook-style component preview renders all components
- ⚙ Fallback: Build components only as needed during page migration

---

## Track B: Feature — Amazon Order Import `[x]`

**Description:** Port the Amazon Order History parser from Accounting. Import Amazon CSV/zip orders as Beancount expenses with categorized line items.

- 📏 Scope: ~6 files, ~600-800 lines

### Phase B1: Amazon import backend `[x]`
- 🏷 Priority: **high** (most impactful missing feature)
- 🔁 Max turns: 8
- [x] Create `app/importers/amazon.py` — port Amazon parser from Accounting (`vendors/amazon.py`)
  - Parse Amazon order history CSV/zip
  - Card-filter support (which card was used)
  - Vendor-side-wins merge strategy
  - Idempotent import (dedup by order ID)
- [x] Tables included in migration 001 (not separate migration): `vendor_receipts`, `vendor_receipt_items`, `transaction_receipt_links`
- [x] Create API endpoints: `POST /import/amazon/preview`, `POST /import/amazon/commit` at `app/api/amazon.py`
- [x] Create Beancount integration: convert Amazon line items to Beancount expense transactions
- [x] Write tests (`tests/test_amazon.py`)
- 📏 Scope: ~3 files, ~400-500 lines
- ✅ Checkpoint: Amazon CSV can be uploaded via API; orders appear in Beancount as expenses
- ⚙ Fallback: Support only CSV format initially; zip/HTML parsing as enhancement

### Phase B2: Amazon import Vue page `[x]`
- 🏷 Priority: high
- 🔁 Max turns: 5
- [x] Create AmazonOrders.vue page component (`web/src/pages/AmazonOrders.vue`)
- [x] File upload with preview of parsed orders
- [x] Line-item categorization UI (card-select, category per line item)
- [x] Import confirmation with dry-run mode
- [x] Order history view with search/filter
- 📏 Scope: ~2 files, ~250-350 lines
- ✅ Checkpoint: End-to-end: upload Amazon CSV → preview → confirm → see in ledger
- ⚙ Fallback: Start with simpler upload+preview page; add line-item UI in Phase B3

---

## Track C: Feature — Import Improvements `[x]`

**Description:** Enhance existing imports and add missing importers (Citi CSV, Wave CSV). Add cross-source duplicate detection.

- 📏 Scope: ~8 files, ~800-1000 lines

### Phase C1: OFX/QFX import improvements `[x]`
- 🏷 Priority: high
- 🔁 Max turns: 5
- [x] Audit current OFX importer (`app/ofx_import.py`) for gaps vs Accounting's version
- [x] Add dedup by (account, date, amount) fingerprint
- [x] Store import batch metadata in SQLite
- [x] Add transaction-source tracking (for cross-source dedup later)
- 📏 Scope: ~2 files, ~150-200 lines
- ✅ Checkpoint: OFX import records source + dedup; tests pass
- ⚙ Fallback: Keep current OFX importer; add source tracking as separate step

### Phase C2: Citi CSV import `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 5
- [x] Port `citi_csv_import.py` from Accounting to `app/importers/citi.py`
  - Multi-card support
  - Auto-archive with period-aware naming
  - Composite dedup key with card identifier
- [x] Create API: `POST /import/citi` (integrated into `app/api/imports.py`)
- [x] Create tests (`tests/test_citi.py`)
- 📏 Scope: ~3 files, ~350-450 lines
- ✅ Checkpoint: Citi CSV imports correctly with multi-card dedup
- ⚙ Fallback: Single-card support first; multi-card later

### Phase C3: Wave historical CSV import `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 5
- [x] Port Wave CSV 4-pass matcher from Accounting (`app/importers/wave.py`)
  - Exact match: (date, abs_cents, description)
  - Loose match: (date, abs_cents)
  - Split detection: 1 row vs N rows summing to match
  - Double-entry ledger insertion
- [x] Create API: `POST /import/wave` (integrated into `app/api/imports.py`)
- [x] Write tests (`tests/test_wave.py`)
- 📏 Scope: ~3 files, ~400-500 lines
- ✅ Checkpoint: Wave CSV imports with split detection; ledger balances match source
- ⚙ Fallback: Exact-match only; split detection as enhancement

### Phase C4: Cross-source duplicate detection `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 4
- [x] Implement overlap detection in import pipeline via fingerprint system
  - On import, check SQLite `imported_transactions` for same fingerprint
  - Fingerprint = SHA256(source, account, date, amount_cents, description)
  - UNIQUE constraint prevents double-import from same source
- [ ] Add dedup flagging across sources (different source, same transaction)
- [ ] Add `GET /import/duplicates` endpoint to list potential dupes
- 📏 Scope: ~3 files, ~200-300 lines
- ✅ Checkpoint: Importing same transaction from two sources generates a warning
- ⚙ Fallback: Simple duplicate check without source tracking; enhance later

---

## Track D: Feature — PDF Statement Processing `[ ]`

**Description:** Port PDF statement intake from Accounting. Extract text from bank/CC PDF statements, classify by institution, file to canonical layout.

- 📏 Scope: ~5 files, ~400-500 lines

### Phase D1: PDF statement intake backend `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 6
- [x] Port `statements_intake.py` from Accounting to `app/statements.py`
  - PDF text extraction (pdfplumber already installed)
  - Institution classification (Wells Fargo, Citi, Chase, BoA, Cap One, Amex, US Bank)
  - Canonical filing to `documents/statements/YYYY/`
- [x] Tables included in migration 001: `reconciliation_marks`, `import_batches`
- [ ] Create API: `POST /statements/upload`, `GET /statements`, `GET /statements/:id`
- [ ] Write tests for classification, filing, listing
- 📏 Scope: ~3 files, ~250-350 lines
- ✅ Checkpoint: Upload a PDF statement → classified, filed, listed
- ⚙ Fallback: No classification; just file by date range and store metadata

### Phase D2: PDF statement Vue page `[x]`
- 🏷 Priority: low
- 🔁 Max turns: 3
- [x] Create Statements.vue page with upload, list, and search
- [x] Show extracted metadata (institution, period, page count)
- [x] Link to downloaded filed PDF
- 📏 Scope: ~1 file, ~150-200 lines
- ✅ Checkpoint: Statements page renders with upload + list
- ⚙ Fallback: Add link from existing Import page instead of dedicated page

---

## Track E: Feature — Reconciliation & Locking `[ ]`

**Description:** Add reconciliation locking (soft-lock reconciled transactions) and reconciliation workflow.

- 📏 Scope: ~5 files, ~400-500 lines

### Phase E1: Reconciliation locking backend `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 5
- [x] Add SQLite migration 001 includes: `reconciliation_marks` table
- [x] Implement soft-lock via `app/reconciliation.py` (start, list, assert workflows)
- [x] API: `GET /api/v1/reconciliation`, `POST /api/v1/reconciliation/check`, `/lock`, `/unlock`
- [x] Add ledger balance verification endpoint via check endpoint
- [ ] Write dedicated tests for lock enforcement
- 📏 Scope: ~3 files, ~200-300 lines
- ✅ Checkpoint: Locked transactions cannot be modified via API
- ⚙ Fallback: Lock check in API routes only (not yet in CLI)

### Phase E2: Reconciliation Vue page `[x]`
- 🏷 Priority: low
- 🔁 Max turns: 4
- [x] Create Reconciliation.vue page
- [x] Period selection (balance date display)
- [x] Statement balance entry
- [x] Transaction list with uncleared items
- [ ] Difference calculation
- 📏 Scope: ~2 files, ~200-250 lines
- ✅ Checkpoint: Full reconciliation cycle works: enter balance → review → lock
- ⚙ Fallback: Simple lock/unlock list without period balance entry

---

## Track F: Feature — Chart of Accounts UI `[x]`

**Description:** Web UI for managing the Chart of Accounts (currently only editable in Beancount files).

- 📏 Scope: ~4 files, ~300-400 lines

### Phase F1: COA backend `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 4
- [x] API: `GET /api/v1/coa` (list all accounts from Beancount), `GET /api/v1/coa/:account`, `PUT /api/v1/coa/:account` (update metadata)
- [x] Read accounts from Beancount's `Open` directives and balance sheet
- [x] Validate against Beancount before write (no duplicate opens, valid parent)
- [x] Write tests (`tests/test_coa.py`)
- 📏 Scope: ~1 file, ~150-200 lines
- ✅ Checkpoint: COA API returns accounts from ledger; partial update works
- ⚙ Fallback: Read-only COA view initially; edits via file download+reupload

### Phase F2: COA Vue page `[x]`
- 🏷 Priority: low
- 🔁 Max turns: 3
- [x] Create ChartOfAccounts.vue with tree view
- [x] Account type icons/colors
- [x] Inline edit for account name/tag
- [x] Add account modal
- 📏 Scope: ~1 file, ~150-200 lines
- ✅ Checkpoint: COA tree renders; add/edit accounts works
- ⚙ Fallback: Flat list view without tree indentation

---

## Track G: Feature — Categorization Rules Engine `[x]`

**Description:** UI for managing categorization rules (regex/substring/eq/range matchers), replacing the current config.toml-based rules.

- 📏 Scope: ~5 files, ~400-500 lines

### Phase G1: Rules engine backend `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 5
- [x] Port rules engine from Accounting (`rules.py`) to `app/rules.py`
  - Matcher types: `regex`, `substring`, `eq`, `range`
  - Ordered evaluation (first-match-wins)
  - Active/inactive toggle
- [x] Store rules in SQLite (migration 001: `categorization_rules` table)
- [x] API: CRUD for rules at `app/api/rules.py`, test-rule endpoint
- [x] Integrate rules engine into existing Categorizer
- [x] Write tests (`tests/test_rules.py`)
- 📏 Scope: ~3 files, ~250-350 lines
- ✅ Checkpoint: Rules can be created, ordered, tested; Categorizer uses them
- ⚙ Fallback: Keep config.toml rules + SQLite rules; merge at query time

### Phase G2: Rules Vue page `[x]`
- 🏷 Priority: low
- 🔁 Max turns: 4
- [x] Create RulesPage.vue
  - Rule list with drag-to-reorder
  - Rule editor (pattern, matcher type, target account)
  - Test-rule input with match preview
  - Bulk enable/disable
- 📏 Scope: ~1 file, ~200-250 lines
- ✅ Checkpoint: Full CRUD + reorder + test works
- ⚙ Fallback: Simple list with add/edit modal; drag-reorder later

---

## Track H: Feature — Line-Item Receipt Reconciliation `[ ]`

**Description:** Per-line CoA assignment for vendor receipts (Amazon orders, uploaded receipts). Support personal/reimbursable flags.

- 📏 Scope: ~4 files, ~400-500 lines

### Phase H1: Line-item reconciliation backend `[x]`
- 🏷 Priority: low
- 🔁 Max turns: 5
- [x] Extend `vendor_receipt_items` table with `coa_account`, `is_personal`, `is_reimbursable` columns (migration 001)
- [x] API: PUT /receipts/:id/items/:item_id (update line-item assignment)
- [x] API: POST /receipts/:id/commit (convert assigned items to Beancount entries)
- [x] Beancount integration: generate split transactions per line-item category
- [ ] Write dedicated tests for assignment and commit
- 📏 Scope: ~2 files, ~200-300 lines
- ✅ Checkpoint: Receipt line items can be individually categorized; commit generates split transactions
- ⚙ Fallback: Assign all items to a single account (current behavior); per-line as enhancement

### Phase H2: Line-item reconciliation Vue component `[ ]`
- 🏷 Priority: low
- 🔁 Max turns: 4
- [ ] Create LineItemReconciler.vue component (reusable in ReceiptCapture.vue and AmazonOrders.vue)
  - Per-line category dropdown with search
  - Personal/reimbursable toggles
  - Total-allocated vs receipt-total balance indicator
  - Batch-same-category action
- 📏 Scope: ~1 file, ~200-250 lines
- ✅ Checkpoint: Line items can be individually assigned; balance indicator works
- ⚙ Fallback: Flat list without grouping; batch actions later

---

## Track I: UI Migration — Remaining Pages `[ ]`

**Description:** Migrate the remaining vanilla JS pages to Vue progressively, page by page.

- 📏 Scope: ~15 files, ~800-1000 lines

### Phase I1: Receipts page migration `[x]`
- 🏷 Priority: high (receipt page has the most interactive logic)
- 🔁 Max turns: 5
- [ ] Create ReceiptCapture.vue — file upload, scan preview, category edit
- [ ] Create ReceiptList.vue — list table with date/account/path
- [ ] Wire into vue-router
- 📏 Scope: ~2 files, ~200-300 lines
- ✅ Checkpoint: Receipt features work in Vue; old receipts.js still loads but routes redirect
- ⚙ Fallback: Keep old page; redirect to it via iframe bridge

### Phase I2: Import page migration `[x]`
- 🏷 Priority: high (import is the most complex page)
- 🔁 Max turns: 6
- [x] Create ImportCenter.vue — tabbed interface (OFX, CSV, QBO, Citi, Wave)
- [x] File upload with drag-and-drop
- [x] Preview table before confirm
- [ ] Import history toggle
- 📏 Scope: ~2 files, ~250-300 lines
- ✅ Checkpoint: All import flows work in Vue
- ⚙ Fallback: Tabbed simple version; advanced per-source options later

### Phase I3: Dashboard + remaining pages `[ ]`
- 🏷 Priority: medium
- 🔁 Max turns: 8
- [x] Dashboard.vue — stat cards, attention items, sparkline charts
- [x] Tax.vue — estimate, deadlines, schedule-C, mark-paid
- [ ] Accounts.vue — balance cards, transfer/split/reimburse forms
- [ ] Remaining pages: Invoices, Transactions, Mileage, Settings, Health, Payroll
- 📏 Scope: ~10 files, ~350-500 lines
- ✅ Checkpoint: All pages navigable via Vue; old page modules unused
- ⚙ Fallback: Migrate high-priority pages first (Dashboard, Tax, Accounts); leave Settings/Health as-is

---

## Progress

| Phase | Status | Notes |
|-------|--------|-------|
| A1: SQLite metadata layer | `[x]` | db.py + 001_init.sql + test_db.py |
| A2: Vue.js scaffold | `[x]` | App.vue, router, vite, api.js all in place |
| A3: Component library | `[ ]` | DataTable, FormField, FileUpload, AuthModal exist; missing StatusBadge, Tag, Alert, ConfirmDialog, Skeleton |
| B1: Amazon import backend | `[x]` | importers/amazon.py + api/amazon.py + test_amazon.py |
| B2: Amazon import Vue page | `[x]` | AmazonOrders.vue; Amazon importer posts to ledger now (verified v0.4) |
| C1: OFX improvements | `[x]` | ofx_import.py with fingerprint |
| C2: Citi CSV import | `[x]` | importers/citi.py + test_citi.py |
| C3: Wave CSV import | `[x]` | importers/wave.py + test_wave.py; Wave importer posts to ledger now (verified v0.4) |
| C4: Cross-source dedup | `[x]` | Fingerprint system in db.py; cross-source flagging still TODO |
| D1: PDF statement backend | `[x]` | statements.py with classify + filing |
| D2: PDF statement Vue page | `[x]` | Statements.vue with upload + router entry |
| E1: Reconciliation locking | `[x]` | reconciliation.py + api/reconciliation.py; lock is a mark with no enforcement yet (partial — see audit notes) |
| E2: Reconciliation Vue page | `[x]` | Reconciliation.vue with uncleared list + nav entry; difference calculation not implemented (partial — see audit notes) |
| F1: COA backend | `[x]` | api/coa.py + test_coa.py; read-only — GET only, no update endpoint (partial — see audit notes) |
| F2: COA Vue page | `[x]` | ChartOfAccounts.vue |
| G1: Rules engine | `[x]` | rules.py + api/rules.py + test_rules.py; integrated into Categorizer (verified v0.4) |
| G2: Rules Vue page | `[x]` | RulesPage.vue |
| H1: Line-item reconciler backend | `[x]` | Schema + API endpoints exist; no dedicated tests (partial — see audit notes) |
| H2: Line-item Vue component | `[ ]` | NOT STARTED |
| I1: Receipt page Vue migration | `[x]` | ReceiptCapture.vue + ReceiptList.vue + router update |
| I2: Import page Vue migration | `[x]` | ImportCenter.vue; import history toggle not implemented (partial — see audit notes) |
| I3: Dashboard + remaining pages | `[ ]` | Dashboard.vue + TaxPage.vue exist; 8 pages still use GenericPage |

---

## v0.4 Audit Notes (2026-08-01)

The phase checkboxes above were audited against the shipped v0.4 code. Most were accurate; the following were overclaimed or partial and are corrected here (noted inline in the Progress table as well):

| Phase | Verdict | Why |
|-------|---------|-----|
| C3: Wave CSV import | ✅ accurate | Wave importer posts to the ledger now (double-entry insertion when `ledger`+`cfg` provided, `app/importers/wave.py`). |
| B2: Amazon import Vue page | ✅ accurate | Amazon importer posts NEW orders to the ledger as credit-card expenses (`app/importers/amazon.py`), dry-run preview + commit wired through `AmazonOrders.vue`. |
| G1: Rules engine | ✅ accurate | Rules engine (first-match-wins, DB rules priority-ordered) is integrated into the Categorizer's Tier 2 (`app/categorizer.py`); CRUD + test endpoints in `app/api/rules.py`. |
| F1: COA backend | ⚠️ partial | **COA is read-only.** `app/api/coa.py` exposes only `GET` list + `GET /tree`; the planned `PUT /coa/:account` (update metadata) is not implemented. |
| E1: Reconciliation locking | ⚠️ partial | **The reconciliation lock is a mark with no enforcement yet.** `reconciliation_marks` rows are written and listed, but there is no `/lock`/`/unlock` API and nothing prevents modifying a reconciled transaction. |
| E2: Reconciliation Vue page | ⚠️ partial | Statement-balance entry + uncleared list exist in `Reconciliation.vue`; the planned difference calculation is not implemented. |
| H1: Line-item reconciler backend | ⚠️ partial | Schema columns + item-assignment endpoints exist, but no dedicated tests were written for assignment/commit. |
| I2: Import page Vue migration | ⚠️ partial | `ImportCenter.vue` tabbed import UI exists; the planned import history toggle is not implemented. |
