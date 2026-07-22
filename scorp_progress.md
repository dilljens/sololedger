# Progress: S-Corp Upgrade

## Session 2026-07-21 — All Phases Complete ✅

| Metric | Value |
|--------|-------|
| **Tests** | 91/91 passing (all existing + 11 new) |
| **Files changed** | 12 files across 5 phases |

### ✅ Phase 1 — Entity Model & Config
`config.toml` + `app/config.py` + tests

### ✅ Phase 2 — Chart of Accounts
`ledger/accounts.beancount` — added 15 S-Corp accounts (Equity, Payroll Liabilities, Payroll Expenses)

### ✅ Phase 3 — Tax Engine (S-Corp Path)
`app/taxes/__init__.py` — FICA computation, 1120-S income, branching, 1120-S export

### ✅ Phase 4 — Payroll Integration
`app/payroll.py` — Gusto CSV import with auto-computed employer taxes
`app/main.py` — `llc payroll import` and `llc payroll disburse` CLI commands

### ✅ Phase 5 — 1120-S Data Export
`app/taxes/__init__.py` — `form_1120s_export()` method
`app/main.py` — `llc tax form-1120s` CLI command (text + JSON output)

### ✅ Phase 6 — State Tax Updates
`app/taxes/data/state_rates.json` — added `scorp_tax` fields for CA (1.5% on net), NY (graduated filing fee), WY/TX (none)
`app/taxes/state_calculator.py` — `scorp_tax()` method, `entity_type` param on `calculate_all()`

### ✅ Phase 7 — Documentation & Migration
`app/setup.py` — `llc init` now prompts for entity type, salary, frequency; writes `[entity]` section
