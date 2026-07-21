# SoloLedger Wiki

**Open-source accounting, invoicing, and tax tools for single-member consulting LLCs.**

**Updated:** 2026-07-21 | **Knowledge Graph:** 1,412 nodes · 4,240 edges · 36 Python files

## Quick Reference

| Aspect | Location |
|--------|----------|
| CLI Entry | `python -m app.main` (Click CLI) |
| API Server | `app/api.py` (FastAPI, 16 routes) |
| Ledger Engine | `app/ledger.py` + `ledger/` (Beancount) |
| Configuration | `config.toml` |
| Tests | `pytest` via `pyproject.toml` |
| CI | `.github/workflows/test.yml` |
| Web App | `web/index.html` (vanilla JS API client) |

## Architecture

```
CLI (llc) via Click  →  app/main.py  ←  REST API (FastAPI, app/api.py)
                            |
          ┌────────┬────────┼────────┬────────┐
          ↓        ↓        ↓        ↓        ↓
     Ledger    Invoice   Expenses   Taxes  TimeTracking
     (beancount) (Stripe) (CSV+Plaid) (1040-ES) (Toggl/Clockify)
          ↓        ↓        ↓
     Receipts  Payments  Categorizer
      (OCR)   (Stripe)  (LLM+rules)

Infrastructure: Stripe · Plaid · Toggl · Clockify · OpenAI · Anthropic
```

## Domains

| Domain | Module | Callers | Doc |
|--------|--------|---------|-----|
| [Core Ledger](features/ledger.md) | `app.ledger` | CLI/API | Beancount accounting |
| [Invoicing](features/invoicing.md) | `app.invoice` | 38 callers | PDF + Stripe |
| [Expenses](features/expenses.md) | `app.importer` | 5 callers | CSV/OCR/Plaid |
| [Taxes](features/taxes.md) | `app/taxes/` | 13 callers | Federal + state |
| [Time Tracking](features/time-tracking.md) | `app.time_tracking` | 6 callers | Toggl/Clockify |
| [Marketing](features/marketing.md) | `app.marketing` | 8 callers | LLM blog/social |

## Standards

See [_standards.md](_standards.md) for coding conventions, patterns, and enforcement.

## Glossary

See [_glossary.md](_glossary.md) for project-specific terminology.
