# SoloLedger Wiki

**Open-source accounting, invoicing, and tax tools for single-member consulting LLCs.**

## Quick Reference

| Aspect | Location |
|--------|----------|
| CLI Entry | `python -m app.main` |
| API Server | `app/api.py` (FastAPI) |
| Ledger Engine | `ledger/` (Beancount) |
| Configuration | `config.toml` |
| Tests | `pyproject.toml` |

## Architecture

```
CLI (llc)  →  Ledger (Beancount)  ←  REST API (FastAPI)
                  ↓
         Stripe / Plaid / Toggl
```

## Domains

- [Core Ledger](features/ledger.md) — accounting engine
- [Invoicing](features/invoicing.md) — invoice generation & payments
- [Expenses](features/expenses.md) — CSV import & categorization
- [Taxes](features/taxes.md) — Federal + state tax estimation
- [Time Tracking](features/time-tracking.md) — Toggl/Clockify sync

## Standards

See [_standards.md](_standards.md) for coding conventions, patterns, and enforcement.

## Glossary

See [_glossary.md](_glossary.md) for project-specific terminology.
