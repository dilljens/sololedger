# Standards

## Rules

- Python 3.12+ required (pyproject.toml `requires-python`; CI tests 3.12/3.13)
- Beancount for double-entry accounting
- FastAPI for REST API
- Config via `config.toml`
- Auth is fail-closed. Set `SOLOLEDGER_OPEN_MODE=true` only for explicit open (demo) mode.

## Practices

- CLI commands via `python -m app.main <command>`
- Ledger files in Beancount format under `ledger/`
- CSV imports in `imports/`
- Receipt processing via Tesseract OCR

## Patterns

- Module-per-domain under `app/`
- API routes live in the `app/api/` package (one module per domain, e.g. `app/api/invoices.py`)
- Tests alongside source (pyproject.toml)
