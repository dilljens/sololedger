# SoloLedger Wiki

**Open-source accounting, invoicing, and tax tools for single-member consulting LLCs.**

**Updated:** 2026-08-01 | **Knowledge Graph:** 2,279 nodes · 9,514 edges · 61 Python files

## Quick Reference

| Aspect | Location |
|--------|----------|
| CLI Entry | `python -m app.main` (Click CLI) |
| API Server | `app/api/` package (FastAPI, 23 routers / ~85 endpoints) |
| Web App | Vue 3 SPA at `web/src/` served at `/app/`; legacy classic app at `/app/index-classic.html` |
| Auth | Fail-closed; `SOLOLEDGER_OPEN_MODE=true` opts into open (demo) mode; sessions in `sessions.json` (30-day expiry) |
| Ledger Engine | `app/ledger.py` + `ledger/` (Beancount) |
| Metadata Layer | `app/db.py` + `app/db_schema/` (SQLite — imports, receipts, rules, recon marks) |
| Configuration | `config.toml` |
| Tests | `pytest` via `pyproject.toml` (240 unit + 20 e2e-marked in `tests/`, 35 Playwright in `e2e/`) |
| CI | `.github/workflows/test.yml` |

## Architecture

```
CLI (llc) via Click  →  app/main.py  ←  REST API (FastAPI, app/api/ package)
                            |
          ┌────────┬────────┼────────┬────────┐
          ↓        ↓        ↓        ↓        ↓
     Ledger    Invoice   Expenses   Taxes  TimeTracking
     (beancount) (Stripe) (CSV+Plaid) (1040-ES) (Toggl/Clockify)
          ↓        ↓        ↓
     Receipts  Payments  Categorizer
      (OCR)   (Stripe)  (LLM+rules)

SQLite metadata layer (app/db.py + app/db_schema/): imports, receipts, rules, recon marks

Infrastructure: Stripe · Plaid · Toggl · Clockify · OpenAI · Anthropic
```

## Domains

| Domain | Module | Doc |
|--------|--------|-----|
| [Core Ledger](features/ledger.md) | `app.ledger` | Beancount accounting |
| [Invoicing](features/invoicing.md) | `app.invoice` | PDF + Stripe |
| [Expenses](features/expenses.md) | `app.importer` | CSV/OCR/Plaid |
| [Taxes](features/taxes.md) | `app/taxes/` | Federal + state |
| [Time Tracking](features/time-tracking.md) | `app.time_tracking` | Toggl/Clockify |
| [Marketing](features/marketing.md) | `app.marketing` | LLM blog/social |

## Standards

See [_standards.md](_standards.md) for coding conventions, patterns, and enforcement.

## Glossary

See [_glossary.md](_glossary.md) for project-specific terminology.
